"""Fixed JSON bridge for the local app. No arbitrary command or path API."""

import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from .grader import grade_run
from .package import export
from .runner import run
from .sources import ROOT, PACK, load_case, now, records, sha
from .store import Store


def worker(run_id):
    store = Store()
    head = json.loads((ROOT / "outputs/nw003/jobs" / (run_id + ".json")).read_text())
    store.job_pid(run_id, os.getpid())
    try:
        case = load_case(head["source_case"], head["pack"] or PACK)
        changes = head.get("source_changes", [])
        if not changes and head["pack"] and (Path(head["pack"]) / "source-changes.json").exists():
            changes = json.loads((Path(head["pack"]) / "source-changes.json").read_text())
        elif not changes and head["source_case"] != "F00":
            old = load_case("F00")
            changes = [{"change_id": "SRC-" + head["source_case"], "source_id": "versioned-case-snapshot",
                "before_hash": old["manifest"]["input_sha256"], "after_hash": case["manifest"]["input_sha256"],
                "measurement_date": case["bundle"]["review_as_of"], "received_at": now(),
                "affected_checks": ["asset_allocation", "issuer_concentration", "digital_exposure", "foreign_currency_gross", "cash_funding", "restricted_sector", "source_quality"],
                "authority": "Explicit synthetic replacement scenario; no trade was executed"}]
        record = run(head["source_case"], run_id=run_id, case=case, source_changes=changes)
        directory = ROOT / "outputs/nw003/runs" / run_id
        grade_run(directory, case)
        store.register(directory, activate=True, revision=head["revision"])
        store.job_end(run_id, record["status"], record.get("error"))
    except Exception as error:
        store.job_end(run_id, "failed", str(error))
        raise


def dispatch(request):
    store = Store()
    operation = request.get("operation")
    if operation == "state":
        state = store.state(request.get("run_id"))
        running = next((j for j in state["jobs"] if j["state"] == "running"), None)
        if running:
            file = ROOT / "outputs/nw003/runs" / running["id"] / "record.json"
            if file.exists():
                try:
                    state["running_record"] = json.loads(file.read_text())
                except json.JSONDecodeError:
                    pass
        comparison = ROOT / "outputs/nw003/experiment-v2/summary.json"
        state["comparison"] = json.loads(comparison.read_text()) if comparison.exists() else None
        return state
    if operation == "start":
        comparison = ROOT / "outputs/nw003/experiment-v2"
        if (comparison / "runs").exists():
            summary_file = comparison / "summary.json"
            summary = json.loads(summary_file.read_text()) if summary_file.exists() else {}
            if summary.get("observed_trials", 0) < 42:
                raise ValueError("The frozen local comparison is running. Fresh interactive reviews resume after all 42 slots finish.")
        run_id = "live-" + uuid.uuid4().hex[:12]
        head = store.job_start(run_id)
        job_dir = ROOT / "outputs/nw003/jobs"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / (run_id + ".json")).write_text(json.dumps(head))
        log_dir = ROOT / "outputs/nw003/logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            with (log_dir / (run_id + ".log")).open("w") as log:
                process = subprocess.Popen([sys.executable, "-m", "finance_runtime.cli", "worker", run_id],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            store.job_pid(run_id, process.pid)
        except Exception as error:
            store.job_end(run_id, "failed", str(error))
            raise
        return {"run_id": run_id, "pid": process.pid, "status": "starting"}
    if operation == "decide":
        return store.decide(request["payload"])
    if operation == "handoff":
        return store.accept_handoff(request["payload"])
    if operation == "source_update":
        load_case(request["payload"]["replacement_case_id"])
        return store.source_update(request["payload"])
    if operation == "correct_quote":
        return store.correct_quote(request["payload"])
    if operation == "export":
        state = store.state(request.get("run_id"))
        if not state["package"]:
            raise ValueError("No review package available")
        version = sha({"package": state["package"], "revision": state["head"]["revision"]})[:20]
        directory = ROOT / "outputs/nw003/exports" / version
        export(state["package"], directory)
        format_ = request.get("format", "pdf")
        if format_ not in ("json", "md", "pdf"):
            raise ValueError("Unknown export format")
        return {"path": str(directory / ("review." + format_)), "filename": "aurora-review." + format_}
    if operation == "source":
        state = store.state(request.get("run_id"))
        if not state["record"]:
            raise ValueError("No selected run")
        pack = Path(state["directory"]) / "inputs"
        case = load_case(state["record"]["case_id"], pack if pack.exists() else PACK)
        filename, record_id = request.get("file"), request.get("record_id")
        if filename not in case["files"]:
            raise ValueError("Source outside this run")
        row = records(case, filename).get(record_id)
        if row is None:
            raise ValueError("No such evidence record")
        return {"file": filename, "file_sha256": sha(case["files"][filename]), "record": row, "input_sha256": case["manifest"]["input_sha256"]}
    raise ValueError("Unsupported local operation")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker(sys.argv[2])
        return
    try:
        result = dispatch(json.load(sys.stdin))
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error), "error_type": type(error).__name__}))
        sys.exit(1)


if __name__ == "__main__":
    main()
