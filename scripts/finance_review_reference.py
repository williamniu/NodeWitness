"""Fixture reference checks, not an agent, production risk engine or approval service."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json


def number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a financial number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid financial number") from error
    if not result.is_finite():
        raise ValueError("Non-finite financial number")
    return result


def money(value):
    return format(value, ".2f")


def unique(rows, key):
    index = {}
    for row in rows:
        if row[key] in index:
            raise ValueError(f"Duplicate {key}: {row[key]}")
        index[row[key]] = row
    return index


def validate_bundle(bundle):
    if bundle.get("schema_version") != "nw-finance-data@1" or bundle.get("synthetic") is not True:
        raise ValueError("Expected the synthetic NW-002 input schema")
    today = date.fromisoformat(bundle["review_as_of"])
    accounts = unique(bundle["accounts"], "account_id")
    positions = unique(bundle["positions"], "position_id")
    prices = unique(bundle["prices"], "price_id")
    fx = unique(bundle["fx"], "currency")
    policies = unique(bundle["policies"], "policy_id")
    sources = unique(bundle["source_catalog"], "source_id")
    unique(bundle["cash_flows"], "flow_id")
    unique(bundle["lookthrough"], "row_id")
    unique(bundle["exceptions"], "exception_id")
    unique(bundle["capital_accounts"], "position_id")
    unique(bundle["custodian_totals"], "account_id")
    if bundle["base_currency"] != "USD" or number(fx["USD"]["usd_per_unit"]) != 1:
        raise ValueError("USD-per-unit FX and USD base currency required")
    if bundle["active_policy_id"] not in policies:
        raise ValueError("Unknown active policy")
    policy = policies[bundle["active_policy_id"]]
    if set(policy["scope_accounts"]) != {k for k, a in accounts.items() if a["included"]}:
        raise ValueError("Policy/account scope mismatch")
    start = date.fromisoformat(policy["effective_from"])
    end = date.fromisoformat(policy["effective_until"]) if policy["effective_until"] else date.max
    if not start <= today <= end:
        raise ValueError("Active policy is not effective on review date")
    for rows in [bundle["positions"], bundle["prices"], bundle["fx"], bundle["lookthrough"], bundle["cash_flows"], bundle["capital_accounts"], bundle["exceptions"], bundle["custodian_totals"], bundle["manager_notes"]]:
        if any(row["source_id"] not in sources for row in rows):
            raise ValueError("Unknown evidence source")
    for p in positions.values():
        if p["account_id"] not in accounts or not accounts[p["account_id"]]["included"]:
            raise ValueError("Unknown or excluded account")
        if p["currency"] not in fx or p["price_id"] not in prices:
            raise ValueError("Missing price or FX identity")
        if type(p["settled"]) is not bool or type(p["restricted"]) is not bool:
            raise ValueError("Cash restriction/settlement must be boolean")
        if p["asset_class"] not in set(policy["rules"]["allocation_bands_pct"]) | {"Mixed"} or (p["asset_class"] == "Mixed" and p["instrument_type"] != "fund"):
            raise ValueError("Unsupported asset classification")
        if p["instrument_type"] not in {"share", "fund", "bond", "cash", "token"}:
            raise ValueError("Unsupported instrument type")
        for field in ["quantity", "reported_market_value_local", "reported_market_value_usd", "cost_basis_local"]:
            if number(p[field]) < 0:
                raise ValueError("Long-only fixture cannot contain negative holdings")
    for quote in prices.values():
        if type(quote["quote_divisor"]) is not int or quote["quote_divisor"] not in [1, 100] or number(quote["price"]) < 0 or number(quote["accrued_per_100"]) < 0:
            raise ValueError("Invalid quote units or price")
    for row in fx.values():
        if number(row["usd_per_unit"]) <= 0:
            raise ValueError("FX rate must be positive")
    weights = defaultdict(Decimal)
    for row in bundle["lookthrough"]:
        if row["position_id"] not in positions or positions[row["position_id"]]["instrument_type"] != "fund":
            raise ValueError("Look-through must reference a fund holding")
        weight = number(row["weight"])
        if not 0 <= weight <= 1:
            raise ValueError("Invalid look-through weight")
        if row["asset_class"] not in policy["rules"]["allocation_bands_pct"] or row["exposure_currency"] not in fx:
            raise ValueError("Unsupported underlying class or currency")
        weights[row["position_id"]] += weight
    if any(weight > 1 for weight in weights.values()):
        raise ValueError("Look-through coverage exceeds 100 percent")
    for flow in bundle["cash_flows"]:
        if type(flow["confirmed"]) is not bool or flow["direction"] not in {"in", "out"}:
            raise ValueError("Invalid cash-flow state")
        if number(flow["amount"]) < 0 or flow["currency"] not in fx:
            raise ValueError("Invalid cash-flow amount or currency")
        if flow["fund_position_id"] and flow["fund_position_id"] not in positions:
            raise ValueError("Unknown capital-call holding")
        if flow["settlement_status"] not in ({"unpaid", "paid"} if flow["direction"] == "out" else {"unreceived", "received"}):
            raise ValueError("Cash-flow settlement status does not match direction")
        date.fromisoformat(flow["due_date"])
    if sum(number(p["reported_market_value_usd"]) for p in positions.values()) <= 0:
        raise ValueError("Positive reported NAV required")
    return policy, positions, prices, fx


def reference_review(bundle):
    policy, positions, prices, fx = validate_bundle(bundle)
    rules = policy["rules"]
    today = date.fromisoformat(bundle["review_as_of"])
    nav = sum(number(p["reported_market_value_usd"]) for p in positions.values())
    issues, nav_blockers, fx_blockers, cash_blockers = [], [], [], []
    incomplete, parts = [], []
    evidence = {}

    def cite(source_id, filename, record_id, fields):
        item = {"source_id": source_id, "file": filename, "record_id": record_id, "fields": fields}
        key = (filename, record_id)
        evidence[key] = item
        return item

    def issue(code, record_id, source_id, file, fields, blocks_nav=False, blocks_fx=False, evidence_id=None):
        finding = {"code": code, "record_id": record_id, "evidence": cite(source_id, file, evidence_id or record_id, fields)}
        issues.append(finding)
        if blocks_nav:
            nav_blockers.append(code + ":" + record_id)
        if blocks_fx:
            fx_blockers.append(code + ":" + record_id)
        if blocks_nav and ((record_id in positions and positions[record_id]["asset_class"] == "Cash") or code.startswith("account_total")):
            cash_blockers.append(code + ":" + record_id)

    for currency, rate in fx.items():
        age = (today - date.fromisoformat(rate["as_of"])).days
        if age < 0 or age > rules["fx_max_days"]:
            issue("fx_date_unusable", currency, rate["source_id"], "fx.csv", ["as_of", "usd_per_unit"], True, True)
        cite(rate["source_id"], "fx.csv", currency, ["usd_per_unit", "as_of"])
    lookthrough = defaultdict(list)
    for row in bundle["lookthrough"]:
        lookthrough[row["position_id"]].append(row)
    for pid, position in positions.items():
        value = number(position["reported_market_value_usd"])
        quote = prices[position["price_id"]]
        cite(position["source_id"], "positions.csv", pid, ["account_id", "reported_market_value_usd", "asset_class", "issuer_group", "currency", "settled", "restricted", "quantity", "valuation_as_of"])
        cite(quote["source_id"], "prices.csv", quote["price_id"], ["price", "accrued_per_100", "quote_divisor", "valuation_as_of"])
        if quote["security_id"] != position["security_id"] or quote["currency"] != position["currency"]:
            issue("price_identity_conflict", pid, quote["source_id"], "prices.csv", ["security_id", "currency"], True, evidence_id=quote["price_id"])
        local = number(position["quantity"]) * (number(quote["price"]) + number(quote["accrued_per_100"])) / quote["quote_divisor"]
        computed = local * number(fx[position["currency"]]["usd_per_unit"])
        if abs(computed - value) > Decimal("0.01") or abs(local - number(position["reported_market_value_local"])) > Decimal("0.01"):
            issue("valuation_source_conflict", pid, quote["source_id"], "prices.csv", ["price", "accrued_per_100"], True, evidence_id=quote["price_id"])
        private = position["valuation_method"] == "administrator_nav"
        max_age = rules["private_valuation_max_days"] if private else rules["listed_valuation_max_days"]
        for value_date, source_id, filename, record_id in [(position["valuation_as_of"], position["source_id"], "positions.csv", pid), (quote["valuation_as_of"], quote["source_id"], "prices.csv", quote["price_id"])]:
            age = (today - date.fromisoformat(value_date)).days
            if age < 0 or age > max_age:
                issue("valuation_date_unusable", record_id, source_id, filename, ["valuation_as_of", "received_at"], True)
                if position["asset_class"] == "Cash":
                    cash_blockers.append("valuation_date_unusable:" + pid)
        if position["instrument_type"] != "fund":
            parts.append({**position, "value": value, "parent_id": pid})
            continue
        coverage = Decimal(0)
        for row in lookthrough[pid]:
            cite(row["source_id"], "lookthrough.csv", row["row_id"], ["weight", "as_of", "issuer_group", "asset_class", "exposure_currency"])
            age = (today - date.fromisoformat(row["as_of"])).days
            if age < 0 or age > rules["lookthrough_max_days"]:
                issue("lookthrough_date_unusable", row["row_id"], row["source_id"], "lookthrough.csv", ["as_of"])
                continue
            coverage += number(row["weight"])
            parts.append({**row, "value": value * number(row["weight"]), "parent_id": pid})
        if coverage < 1:
            incomplete.append(pid)
            parts.append({"asset_class": "Unknown", "value": value * (1 - coverage), "parent_id": pid, "issuer_group": "Unknown", "issuer_type": "unknown", "exposure_currency": "Unknown", "sector": "Unknown"})
            issue("lookthrough_incomplete", pid, position["source_id"], "positions.csv", ["reported_market_value_usd"])
    by_account = defaultdict(Decimal)
    for p in positions.values():
        by_account[p["account_id"]] += number(p["reported_market_value_usd"])
    if {t["account_id"] for t in bundle["custodian_totals"]} != set(by_account):
        issue("account_total_coverage", "__all__", "SRC-TOTAL", "custodian_totals.csv", ["account_id"], True)
    for total in bundle["custodian_totals"]:
        cite(total["source_id"], "custodian_totals.csv", total["account_id"], ["reported_total_usd", "as_of"])
        if number(total["reported_total_usd"]) != by_account[total["account_id"]] or total["as_of"] != bundle["review_as_of"]:
            issue("account_total_conflict", total["account_id"], total["source_id"], "custodian_totals.csv", ["reported_total_usd", "as_of"], True)
    expected_capital = {p["position_id"] for p in positions.values() if p["asset_class"] == "Private equity"}
    if {cap["position_id"] for cap in bundle["capital_accounts"]} != expected_capital:
        issue("capital_account_coverage", "__all__", "SRC-CAP", "capital_accounts.csv", ["position_id"], True)
    for cap in bundle["capital_accounts"]:
        cite(cap["source_id"], "capital_accounts.csv", cap["position_id"], list(cap))
        bridge = number(cap["opening_nav"]) + number(cap["contributions_qtd"]) - number(cap["distributions_qtd"]) - number(cap["management_fees_qtd"]) - number(cap["other_expenses_qtd"]) + number(cap["investment_income_qtd"]) + number(cap["realized_gain_qtd"]) + number(cap["unrealized_gain_qtd"])
        if bridge != number(cap["ending_nav"]) or number(cap["ending_nav"]) != number(positions[cap["position_id"]]["reported_market_value_usd"]):
            issue("capital_nav_bridge_conflict", cap["position_id"], cap["source_id"], "capital_accounts.csv", ["opening_nav", "ending_nav"], True)
        if number(cap["commitment"]) - number(cap["contributed_itd"]) != number(cap["unfunded_commitment"]):
            issue("unfunded_bridge_conflict", cap["position_id"], cap["source_id"], "capital_accounts.csv", ["commitment", "contributed_itd", "unfunded_commitment"])
    allocation, issuer = defaultdict(Decimal), defaultdict(Decimal)
    for part in parts:
        allocation[part["asset_class"]] += part["value"]
        if part["issuer_type"] == "corporate" and part["asset_class"] in {"Equity", "Fixed income"}:
            issuer[part["issuer_group"]] += part["value"]
    percentages = {key: value / nav * 100 for key, value in allocation.items()}
    allocation_breaches = [key for key, (low, high) in rules["allocation_bands_pct"].items() if not number(low) <= percentages.get(key, Decimal(0)) <= number(high)]
    top_issuer, top_value = max(issuer.items(), key=lambda item: item[1], default=("None", Decimal(0)))
    digital = sum(p["value"] for p in parts if p["asset_class"] == "Digital assets") if rules["digital_scope"] == "direct_and_lookthrough" else sum(number(p["reported_market_value_usd"]) for p in positions.values() if p["asset_class"] == "Digital assets" and p["instrument_type"] != "fund")
    foreign = sum(p["value"] for p in parts if p["exposure_currency"] not in {"USD", "Unknown"})
    cash = sum(number(p["reported_market_value_usd"]) for p in positions.values() if p["asset_class"] == "Cash" and p["settled"] and not p["restricted"])
    last_day = today + timedelta(days=rules["cash_horizon_days"])
    incoming = outgoing = Decimal(0)
    for flow in bundle["cash_flows"]:
        cite(flow["source_id"], "cash_flows.csv", flow["flow_id"], ["amount", "currency", "direction", "confirmed", "due_date", "settlement_status"])
        due = date.fromisoformat(flow["due_date"])
        if flow["direction"] == "out":
            eligible = due <= last_day and flow["settlement_status"] == "unpaid"
        else:
            eligible = today <= due <= last_day and flow["settlement_status"] == "unreceived"
        if flow["confirmed"] and eligible:
            value = number(flow["amount"]) * number(fx[flow["currency"]]["usd_per_unit"])
            if flow["direction"] == "in":
                incoming += value
            else:
                outgoing += value
    ratio = (cash + incoming) / outgoing if outgoing else None
    restrictions = []
    applicable_exceptions = []
    for part in parts:
        if part["sector"] not in rules["restricted_sectors"]:
            continue
        parent = positions[part["parent_id"]]
        matching = [ex for ex in bundle["exceptions"] if ex["position_id"] == parent["position_id"] and ex["account_id"] == parent["account_id"] and ex["policy_id"] == policy["policy_id"] and ex["rule_id"] == "restricted_sector" and ex["approved_role"] == policy["governance"]["exception_authority"] and date.fromisoformat(ex["approved_on"]) <= today <= date.fromisoformat(ex["valid_until"])]
        if matching:
            applicable_exceptions.extend(ex["exception_id"] for ex in matching)
        else:
            restrictions.append(parent["position_id"])
    for ex in bundle["exceptions"]:
        cite(ex["source_id"], "exceptions.csv", ex["exception_id"], list(ex))
    policy_evidence = cite(policy["source_id"], f"policy-{policy['version']}.json", policy["policy_id"], ["rules", "definitions", "effective_from", "governance", "pdf_pages"])
    all_evidence = list(evidence.values())

    def finding(rule_id, breach, observed, blockers, sources, action):
        raw = "review_required" if breach else "within_policy"
        status = "needs_source" if blockers else raw
        return {"rule_id": rule_id, "status": status, "as_reported_status": raw, "observed": observed,
                "limitations": sorted(set(blockers)), "evidence": [policy_evidence, *sources],
                "next_action": None if status == "within_policy" else {"description": action, "owner_role": "Compliance Lead" if status == "review_required" else "Investment Operations", "due": "Before final sign-off", "state": "proposed_not_executed", "requires_human_decision": True}}

    input_refs = [e for e in all_evidence if e["file"] in {"positions.csv", "prices.csv", "fx.csv", "lookthrough.csv", "custodian_totals.csv", "capital_accounts.csv"}]
    partial = ["uncovered_fund:" + pid for pid in incomplete]
    findings = [
        finding("asset_allocation", bool(allocation_breaches), {"usd": {k: money(v) for k, v in sorted(allocation.items())}, "pct": {k: money(v) for k, v in sorted(percentages.items())}, "out_of_band": allocation_breaches}, nav_blockers + partial, input_refs, "Obtain missing data or review allocation drift; any rebalancing proposal needs separate approval."),
        finding("issuer_concentration", top_value / nav * 100 > number(rules["issuer_max_pct"]), {"issuer_group": top_issuer, "usd": money(top_value), "pct": money(top_value / nav * 100), "limit_pct": rules["issuer_max_pct"]}, nav_blockers + ([] if top_value / nav * 100 > number(rules["issuer_max_pct"]) else partial), input_refs, "Verify cross-account and fund exposure; submit a concentration-review or exception proposal."),
        finding("digital_exposure", digital / nav * 100 > number(rules["digital_max_pct"]), {"usd": money(digital), "pct": money(digital / nav * 100), "scope": rules["digital_scope"], "limit_pct": rules["digital_max_pct"]}, nav_blockers + (partial if rules["digital_scope"] == "direct_and_lookthrough" else []), input_refs, "Request complete fund exposure and review the policy limit before proposing any change."),
        finding("foreign_currency_gross", foreign / nav * 100 > number(rules["foreign_currency_gross_max_pct"]), {"usd": money(foreign), "pct": money(foreign / nav * 100), "limit_pct": rules["foreign_currency_gross_max_pct"], "basis": "gross exposure; no hedge offsets"}, nav_blockers + partial, input_refs, "Confirm exposure currencies and request a human review; do not infer unreported hedges."),
        finding("cash_funding", ratio is not None and ratio < number(rules["cash_funding_min_ratio"]), {"settled_unrestricted_cash_usd": money(cash), "confirmed_incoming_usd": money(incoming), "confirmed_outgoing_usd": money(outgoing), "coverage_ratio": format(ratio, ".4f") if ratio is not None else None, "minimum_ratio": rules["cash_funding_min_ratio"], "shortfall_to_policy_usd": money(max(Decimal(0), outgoing * number(rules["cash_funding_min_ratio"]) - cash - incoming)), "horizon_end": last_day.isoformat()}, fx_blockers + cash_blockers, [e for e in all_evidence if e["file"] in {"positions.csv", "fx.csv", "cash_flows.csv"}], "Ask Treasury to propose funding for dated obligations; do not assume sale proceeds or unconfirmed distributions."),
        finding("restricted_sector", bool(restrictions), {"unwaived_positions": sorted(set(restrictions)), "valid_exception_ids": sorted(set(applicable_exceptions))}, partial, [e for e in all_evidence if e["file"] in {"positions.csv", "lookthrough.csv", "exceptions.csv"}], "Verify the exact exception scope and expiry; request Committee review if no valid waiver exists."),
        finding("source_quality", bool(issues), {"issues": issues}, [i["code"] + ":" + i["record_id"] for i in issues], [i["evidence"] for i in issues], "Reconcile conflicting totals, request dated source evidence and rerun affected checks."),
    ]
    status = "NEEDS_SOURCE" if any(f["status"] == "needs_source" for f in findings) else "REVIEW_REQUIRED" if any(f["status"] == "review_required" for f in findings) else "READY_FOR_HUMAN_REVIEW"
    return {"schema_version": "nw-finance-reference@1", "case_id": bundle["case_id"], "synthetic": True,
            "reference_only": True, "not_a_model_trial": True, "not_human_approved": True,
            "display_note": "Display values are rounded; comparisons use unrounded Decimal values and the stated USD numerator/denominator.",
            "active_policy_id": policy["policy_id"], "as_reported_nav_usd": money(nav), "status": status,
            "findings": findings, "human_signoff": "pending", "external_actions_executed": False}


def content_hash(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()).hexdigest()


def approval_binding_errors(package, current_input_hash, current_policy_id):
    """Check declared bindings only. This does NOT authenticate a human or authorize an effect."""
    approval = package.get("approval", {})
    errors = []
    if approval.get("status") != "approved":
        errors.append("no_declared_approval")
    if approval.get("role") != "Review Principal" or not approval.get("reviewer") or not approval.get("decided_at") or not approval.get("rationale"):
        errors.append("incomplete_reviewer_declaration")
    if package.get("input_sha256") != current_input_hash or approval.get("bound_input_sha256") != current_input_hash:
        errors.append("input_binding_changed")
    if package.get("active_policy_id") != current_policy_id or approval.get("bound_policy_id") != current_policy_id:
        errors.append("policy_binding_changed")
    if approval.get("bound_actions_sha256") != content_hash(package.get("suggested_actions", [])):
        errors.append("action_binding_changed")
    content = {k: v for k, v in package.items() if k not in {"approval", "handoff"}}
    if approval.get("bound_package_content_sha256") != content_hash(content):
        errors.append("package_binding_changed")
    return errors
