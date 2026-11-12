"""Transactional single-operator state. The model has no access to this module or DB."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .package import package_hash
from .engine import CONTROLS
from .sources import ROOT, PACK, load_case, now, sha

DB = ROOT / "outputs/nw003/review.sqlite3"


class Store:
    def __init__(self, path=DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, body TEXT NOT NULL, directory TEXT NOT NULL, package TEXT, verified INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS head(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, source_case TEXT NOT NULL, pack TEXT, run_id TEXT);
                INSERT OR IGNORE INTO head VALUES(1,1,'F00',NULL,NULL);
                CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL, pid INTEGER, error TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_running_job ON jobs(state) WHERE state='running';
            """)

    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def event(self, db, kind, body):
        db.execute("INSERT INTO events(at,kind,body) VALUES(?,?,?)", (now(), kind, json.dumps(body)))

    def request(self, db, request_id, payload):
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
            raise ValueError("A bounded request ID is required")
        prior = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if prior:
            if prior["fingerprint"] != sha(payload):
                raise ValueError("Request ID reused with different content")
            return json.loads(prior["result"])
        return None

    def receipt(self, db, request_id, payload, result):
        db.execute("INSERT INTO requests VALUES(?,?,?)", (request_id, sha(payload), json.dumps(result)))
        return result

    def invalidate(self, db, reason):
        for row in db.execute("SELECT id,body FROM decisions").fetchall():
            body = json.loads(row["body"])
            if body["status"] in ("approved", "rejected"):
                body.update({"status": "invalidated", "prior_status": body["status"], "invalidation_reason": reason, "invalidated_at": now()})
                db.execute("UPDATE decisions SET body=? WHERE id=?", (json.dumps(body), row["id"]))
        self.event(db, "decision.invalidated", {"reason": reason})

    def register(self, directory, activate=False, revision=None):
        directory = Path(directory).resolve()
        record = json.loads((directory / "record.json").read_text())
        package = json.loads((directory / "review.json").read_text()) if (directory / "review.json").exists() else None
        grade = json.loads((directory / "grade.json").read_text()) if (directory / "grade.json").exists() else {}
        with self.transaction() as db:
            prior = db.execute("SELECT * FROM runs WHERE id=?", (record["run_id"],)).fetchone()
            body = json.dumps(record)
            if prior:
                if prior["body"] != body:
                    raise ValueError("Run IDs are immutable")
                return
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (record["run_id"], body, str(directory), json.dumps(package) if package else None, int(grade.get("released_correct", False))))
            head = db.execute("SELECT * FROM head").fetchone()
            if activate:
                if revision is not None and head["revision"] != revision:
                    self.event(db, "run.stale", {"run_id": record["run_id"], "revision": revision})
                else:
                    self.invalidate(db, "New package superseded previous run")
                    db.execute("UPDATE head SET revision=revision+1,run_id=?", (record["run_id"],))
            self.event(db, "run.registered", {"run_id": record["run_id"], "verified": grade.get("released_correct", False)})

    def state(self, run_id=None):
        with self.connect() as db:
            head = dict(db.execute("SELECT * FROM head").fetchone())
            selected = run_id or head["run_id"]
            row = db.execute("SELECT * FROM runs WHERE id=?", (selected,)).fetchone() if selected else None
            package, record, directory, verified = None, None, None, False
            if row:
                package = json.loads(row["package"]) if row["package"] else None
                record, directory, verified = json.loads(row["body"]), row["directory"], bool(row["verified"])
                decision = db.execute("SELECT id,body FROM decisions WHERE run_id=? ORDER BY id DESC LIMIT 1", (selected,)).fetchone()
                if package and decision:
                    approval = json.loads(decision["body"])
                    if approval["status"] in ("approved", "rejected") and (approval["bound_package_content_sha256"] != package_hash(package) or head["run_id"] != selected):
                        approval.update({"prior_status": approval["status"], "status": "invalidated", "invalidated_at": now(), "invalidation_reason": "Current package/head no longer matches decision"})
                        db.execute("UPDATE decisions SET body=? WHERE id=?", (json.dumps(approval), decision["id"]))
                        self.event(db, "decision.binding_changed", {"run_id": selected, "decision_id": decision["id"]})
                    package["approval"] = approval
                    accepted = db.execute("SELECT body FROM events WHERE kind='handoff.accepted' ORDER BY id DESC").fetchall()
                    for event in accepted:
                        receipt = json.loads(event["body"])
                        if receipt["run_id"] == selected and receipt["package_sha256"] == package_hash(package) and receipt.get("decision_sha256") == sha(approval) and approval["status"] == "approved":
                            package["handoff"].update({"accepted_at": receipt["accepted_at"], "acceptance_receipt": receipt, "remaining_obligations": receipt["remaining_obligations"]})
                            break
            runs = [{"run_id": r["id"], "case_id": json.loads(r["body"])["case_id"], "status": json.loads(r["body"])["status"], "verified": bool(r["verified"])}
                    for r in db.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT 60")]
            return {"head": head, "package": package, "record": record, "directory": directory,
                    "verified": verified, "package_sha256": package_hash(package) if package else None,
                    "runs": runs, "jobs": [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY rowid DESC LIMIT 5")],
                    "audit": [{"id": r["id"], "at": r["at"], "kind": r["kind"], "body": json.loads(r["body"])} for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")]}

    def decide(self, payload):
        if set(payload) != {"request_id", "run_id", "revision", "package_sha256", "status", "reviewer", "rationale"}:
            raise ValueError("Decision fields outside contract")
        if payload["status"] not in ("approved", "rejected") or not all(isinstance(payload[k], str) and 2 <= len(payload[k].strip()) <= 2000 for k in ("reviewer", "rationale")):
            raise ValueError("Explicit reviewer, rationale and decision required")
        with self.transaction() as db:
            prior = self.request(db, payload["request_id"], payload)
            if prior:
                return prior
            head = db.execute("SELECT * FROM head").fetchone()
            if head["revision"] != payload["revision"] or head["run_id"] != payload["run_id"]:
                raise ValueError("Stale view; reload the current source/package")
            row = db.execute("SELECT * FROM runs WHERE id=?", (head["run_id"],)).fetchone()
            package = json.loads(row["package"]) if row and row["package"] else None
            if not package or package_hash(package) != payload["package_sha256"]:
                raise ValueError("Package changed or unavailable")
            if payload["status"] == "approved" and (not row["verified"] or package["status"] == "NEEDS_SOURCE"):
                raise ValueError("Cannot sign off an invalid or needs-source package")
            approval = {"status": payload["status"], "reviewer": payload["reviewer"].strip(), "role": "Review Principal",
                "rationale": payload["rationale"].strip(), "decided_at": now(), "bound_input_sha256": package["input_sha256"],
                "bound_policy_id": package["active_policy_id"], "bound_actions_sha256": sha(package["suggested_actions"]),
                "bound_package_content_sha256": package_hash(package), "local_identity_declaration": True}
            db.execute("INSERT INTO decisions(run_id,body) VALUES(?,?)", (payload["run_id"], json.dumps(approval)))
            self.event(db, "review." + payload["status"], {"run_id": payload["run_id"], "approval": approval})
            return self.receipt(db, payload["request_id"], payload, approval)

    def source_update(self, payload):
        if set(payload) != {"request_id", "revision", "replacement_case_id", "reason"} or payload["replacement_case_id"] not in {f"F{i:02}" for i in range(7)} or len(payload["reason"].strip()) < 10:
            raise ValueError("Confirmed finite source snapshot and reason required")
        with self.transaction() as db:
            prior = self.request(db, payload["request_id"], payload)
            if prior:
                return prior
            head = db.execute("SELECT * FROM head").fetchone()
            if head["revision"] != payload["revision"]:
                raise ValueError("Stale source revision")
            before = load_case(head["source_case"], head["pack"] or PACK)
            after = load_case(payload["replacement_case_id"])
            self.invalidate(db, "Source version changed: " + payload["reason"])
            db.execute("UPDATE head SET revision=revision+1, source_case=?,pack=NULL,run_id=NULL", (payload["replacement_case_id"],))
            result = {"revision": head["revision"] + 1, "source_case": payload["replacement_case_id"], "previous_run_id": head["run_id"], "reason": payload["reason"], "at": now()}
            result["changes"] = [{"change_id": "SRC-V" + str(result["revision"]), "source_id": "versioned-case-snapshot",
                "before_hash": before["manifest"]["input_sha256"], "after_hash": after["manifest"]["input_sha256"],
                "measurement_date": after["bundle"]["review_as_of"], "received_at": result["at"], "affected_checks": list(CONTROLS),
                "authority": "Local operator confirms a synthetic replacement scenario; no trade executed", "reason": payload["reason"]}]
            self.event(db, "source.replaced", result)
            return self.receipt(db, payload["request_id"], payload, result)

    def accept_handoff(self, payload):
        if set(payload) != {"request_id", "run_id", "revision", "package_sha256"}:
            raise ValueError("Handoff fields outside contract")
        with self.transaction() as db:
            prior = self.request(db, payload["request_id"], payload)
            if prior:
                return prior
            head = db.execute("SELECT * FROM head").fetchone()
            if head["run_id"] != payload["run_id"] or head["revision"] != payload["revision"]:
                raise ValueError("Stale handoff")
            row = db.execute("SELECT package FROM runs WHERE id=?", (payload["run_id"],)).fetchone()
            p = json.loads(row["package"])
            decision = db.execute("SELECT body FROM decisions WHERE run_id=? ORDER BY id DESC LIMIT 1", (payload["run_id"],)).fetchone()
            d = json.loads(decision["body"]) if decision else {}
            if d.get("status") != "approved" or d.get("bound_package_content_sha256") != package_hash(p) or payload["package_sha256"] != package_hash(p):
                raise ValueError("Current approved package required for handoff")
            result = {"run_id": payload["run_id"], "package_sha256": package_hash(p), "receiving_role": "Review Principal",
                "decision_sha256": sha(d),
                "accepted_at": now(), "reviewer": d["reviewer"], "remaining_obligations":
                    [a["owner_role"] + ": " + a["description"] for a in p["suggested_actions"] if a["decision"] == "pending"] +
                    [r["owner_role"] + ": " + r["requested_confirmation"] for r in p["sources_to_recheck"] if r["state"] == "pending"],
                "external_actions_executed": False}
            self.event(db, "handoff.accepted", result)
            return self.receipt(db, payload["request_id"], payload, result)

    def correct_quote(self, payload):
        from .corrections import correct_quote
        if set(payload) != {"request_id", "revision", "position_id", "source_evidence", "reason"}:
            raise ValueError("Correction fields outside contract")
        if not payload["request_id"].isalnum() or not 8 <= len(payload["request_id"]) <= 100 or len(payload["reason"].strip()) < 10:
            raise ValueError("Bounded correction ID and evidence-backed reason required")
        with self.transaction() as db:
            prior = self.request(db, payload["request_id"], payload)
            if prior:
                return prior
            head = db.execute("SELECT * FROM head").fetchone()
            if payload["revision"] != head["revision"]:
                raise ValueError("Stale extraction correction")
            # A rolled-back/crashed attempt may leave source files; keep them and use a fresh path.
            directory = self.path.parent / "snapshots" / (payload["request_id"] + "-" + uuid.uuid4().hex[:12])
            corrected, changes = correct_quote(load_case(head["source_case"], head["pack"] or PACK), payload["position_id"], payload["source_evidence"], directory)
            self.invalidate(db, "Evidence-backed source correction: " + payload["reason"])
            db.execute("UPDATE head SET revision=revision+1,pack=?,run_id=NULL", (str(directory),))
            result = {"revision": head["revision"] + 1, "source_case": head["source_case"], "changes": changes,
                "input_sha256": corrected["manifest"]["input_sha256"], "at": now()}
            self.event(db, "source.corrected", result)
            return self.receipt(db, payload["request_id"], payload, result)

    def job_start(self, run_id):
        with self.transaction() as db:
            for job in db.execute("SELECT * FROM jobs WHERE state='running'").fetchall():
                alive = False
                if job["pid"]:
                    try:
                        os.kill(job["pid"], 0)
                        alive = True
                    except ProcessLookupError:
                        pass
                if alive:
                    raise ValueError("A local review is already running")
                db.execute("UPDATE jobs SET state='interrupted',error='Worker not alive after restart' WHERE id=?", (job["id"],))
                self.event(db, "run.interrupted", {"run_id": job["id"]})
            head = dict(db.execute("SELECT * FROM head").fetchone())
            latest_source = db.execute("SELECT body FROM events WHERE kind IN ('source.replaced','source.corrected') ORDER BY id DESC LIMIT 1").fetchone()
            if latest_source:
                source_event = json.loads(latest_source["body"])
                if source_event["revision"] == head["revision"]:
                    head["source_changes"] = source_event.get("changes", [])
            db.execute("INSERT INTO jobs VALUES(?,?,'running',?,NULL)", (run_id, head["revision"], os.getpid()))
            return head

    def job_end(self, run_id, state, error=None):
        with self.transaction() as db:
            db.execute("UPDATE jobs SET state=?,error=? WHERE id=?", (state, error, run_id))
            self.event(db, "job." + state, {"run_id": run_id, "error": error})

    def job_pid(self, run_id, pid):
        with self.transaction() as db:
            db.execute("UPDATE jobs SET pid=? WHERE id=? AND state='running'", (pid, run_id))
