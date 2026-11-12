"""A bounded, evidence-backed price extraction correction; original sources stay intact."""

import copy
import csv
from decimal import Decimal
import io
from pathlib import Path

from .sources import canonical, load_case, now, sha


def correct_quote(case, position_id, source_evidence, destination):
    if source_evidence != "positions.csv:" + position_id:
        raise ValueError("Correction requires the exact custodian position evidence")
    b = copy.deepcopy(case["bundle"])
    position = next((p for p in b["positions"] if p["position_id"] == position_id), None)
    if not position or position["instrument_type"] in ("cash", "fund"):
        raise ValueError("Only a listed quote extraction can be corrected here")
    quote = next(q for q in b["prices"] if q["price_id"] == position["price_id"])
    corrected = Decimal(position["reported_market_value_local"]) / Decimal(position["quantity"]) * quote["quote_divisor"] - Decimal(quote["accrued_per_100"])
    if corrected == Decimal(quote["price"]) or corrected < 0:
        raise ValueError("No supported quote discrepancy to correct")
    before = quote["price"]
    quote["price"] = format(corrected, "f")
    directory = Path(destination)
    case_dir = directory / "cases" / b["case_id"]
    case_dir.mkdir(parents=True, exist_ok=False)
    manifest = copy.deepcopy(case["manifest"])
    for name, raw in case["files"].items():
        target = case_dir / name if name in manifest["files"] else directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (case_dir / "bundle.json").write_bytes(canonical(b))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(b["prices"][0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(b["prices"])
    (case_dir / "prices.csv").write_text(stream.getvalue())
    for name in manifest["files"]:
        manifest["files"][name] = sha((case_dir / name).read_bytes())
    manifest["input_sha256"] = sha({k: manifest[k] for k in ("files", "shared_files")})
    (case_dir / "manifest.json").write_bytes(canonical(manifest))
    updated = load_case(b["case_id"], directory)
    changes = [{"change_id": "COR-" + position_id, "source_id": quote["source_id"],
        "before_hash": case["manifest"]["files"]["prices.csv"], "after_hash": manifest["files"]["prices.csv"],
        "measurement_date": quote["valuation_as_of"], "received_at": now(),
        "affected_checks": ["asset_allocation", "issuer_concentration", "digital_exposure", "foreign_currency_gross", "source_quality"],
        "evidence": source_evidence, "field": quote["price_id"] + ".price", "before": before, "after": quote["price"],
        "authority": "Local operator extraction correction supported by custodian quantity and local market value; not an external source confirmation"}]
    (directory / "source-changes.json").write_bytes(canonical(changes))
    return updated, changes
