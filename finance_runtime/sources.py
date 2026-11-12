"""Trusted ingestion and record-addressable evidence for the fixed NW-002 pack."""

import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "public/demo/finance-review/v1"
KEYS = {"accounts": "account_id", "positions": "position_id", "prices": "price_id",
        "fx": "currency", "lookthrough": "row_id", "cash_flows": "flow_id",
        "capital_accounts": "position_id", "custodian_totals": "account_id",
        "exceptions": "exception_id", "manager_notes": "note_id"}


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode()


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def load_case(case_id, pack=PACK):
    if case_id not in {f"F{i:02}" for i in range(7)}:
        raise ValueError("Unknown case")
    directory = Path(pack) / "cases" / case_id
    manifest = json.loads((directory / "manifest.json").read_text())
    if sha({k: manifest[k] for k in ("files", "shared_files")}) != manifest["input_sha256"]:
        raise ValueError("Manifest binding mismatch")
    files = {}
    for names, base in ((manifest["files"], directory), (manifest["shared_files"], Path(pack))):
        for name, expected in names.items():
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("Unsafe manifest path")
            raw = (base / name).read_bytes()
            if sha(raw) != expected:
                raise ValueError("Source hash mismatch: " + name)
            files[name] = raw
    bundle = json.loads(files["bundle.json"])
    if bundle["case_id"] != case_id or bundle.get("synthetic") is not True:
        raise ValueError("Case identity mismatch")
    schema = json.loads(files["schema.json"])
    for table, columns in schema["tables"].items():
        rows = list(csv.DictReader(io.StringIO(files[table + ".csv"].decode())))
        parsed = []
        for row in rows:
            if set(row) != set(columns):
                raise ValueError("CSV columns differ from schema")
            result = {}
            for key, field in columns.items():
                value = row[key]
                if value == "" and field["nullable"]:
                    result[key] = None
                elif field["type"] == "boolean":
                    if value not in {"true", "false"}:
                        raise ValueError("Invalid boolean")
                    result[key] = value == "true"
                elif field["type"] == "integer":
                    result[key] = int(value)
                else:
                    if field["type"] == "decimal_string" and not Decimal(value).is_finite():
                        raise ValueError("Nonfinite financial value")
                    result[key] = value
            parsed.append(result)
        if parsed != bundle[table]:
            raise ValueError("CSV/JSON disagreement: " + table)
    for policy in bundle["policies"]:
        if json.loads(files[f"policy-{policy['version']}.json"]) != policy:
            raise ValueError("Policy companion disagreement")
    if json.loads(files["manager_notes.json"]) != bundle["manager_notes"]:
        raise ValueError("Note companion disagreement")
    if json.loads(files["source-catalog.json"]) != bundle["source_catalog"]:
        raise ValueError("Source catalog disagreement")
    return {"bundle": bundle, "manifest": manifest, "files": files}


def pdf_pages(case):
    from pypdf import PdfReader
    return {name: [page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages]
            for name, raw in case["files"].items() if name.endswith(".pdf")}


def records(case, filename):
    if filename == "source-catalog.json":
        return {row["source_id"]: row for row in case["bundle"]["source_catalog"]}
    table = filename.removesuffix(".csv").removesuffix(".json")
    if table in KEYS:
        return {str(row[KEYS[table]]): row for row in case["bundle"][table]}
    if filename.startswith("policy-"):
        return {p["policy_id"]: p for p in case["bundle"]["policies"]
                if filename == f"policy-{p['version']}.json"}
    return {}


def citation(case, filename, record_id, fields, policy_page=None):
    record = records(case, filename).get(record_id)
    if record is None or not fields or not set(fields) <= set(record):
        raise ValueError("Unresolvable citation")
    policy = next(p for p in case["bundle"]["policies"]
                  if p["policy_id"] == case["bundle"]["active_policy_id"])
    return {"source_id": record.get("source_id", "FILE:" + filename), "file": filename, "record_id": record_id,
            "fields": fields, "source_date": next((record[k] for k in
                ("valuation_as_of", "as_of", "period_end", "approved_on", "effective_from") if k in record), None),
            "file_sha256": sha(case["files"][filename]), "policy_id": policy["policy_id"],
            "policy_page": policy_page}
