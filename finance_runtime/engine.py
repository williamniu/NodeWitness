"""Runtime arithmetic over source records. Evaluator/oracle files are never imported."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from .sources import KEYS, citation

CONTROLS = ("asset_allocation", "issuer_concentration", "digital_exposure",
            "foreign_currency_gross", "cash_funding", "restricted_sector", "source_quality")


def dec(value):
    if isinstance(value, bool):
        raise ValueError("A boolean is not an amount")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Nonfinite amount")
    return result


def compute(case):
    b = case["bundle"]
    tables = {}
    for table, key in KEYS.items():
        tables[table] = {row[key]: row for row in b[table]}
        if len(tables[table]) != len(b[table]):
            raise ValueError("Duplicate record: " + table)
    policy = next(p for p in b["policies"] if p["policy_id"] == b["active_policy_id"])
    today = date.fromisoformat(b["review_as_of"])
    if not date.fromisoformat(policy["effective_from"]) <= today <= date.fromisoformat(policy["effective_until"] or "9999-12-31"):
        raise ValueError("Policy not effective")
    accounts = {a["account_id"] for a in b["accounts"] if a["included"]}
    if accounts != set(policy["scope_accounts"]) or b["base_currency"] != "USD":
        raise ValueError("Policy scope/units mismatch")
    rules, issues, exposures, incomplete = policy["rules"], [], [], []
    nav_blocks, cash_blocks, fx_blocks = [], [], []
    evidence = {}

    def cite(file, row, fields=None):
        table = file.rsplit(".", 1)[0]
        key = KEYS.get(table, "policy_id")
        item = citation(case, file, row[key], fields or list(row))
        evidence[(file, row[key])] = item
        return item

    def problem(code, identifier, file, row, fields, nav=False, cash=False, fx=False):
        item = {"code": code, "record_id": identifier, "evidence": cite(file, row, fields)}
        issues.append(item)
        tag = code + ":" + identifier
        if nav:
            nav_blocks.append(tag)
        if cash:
            cash_blocks.append(tag)
        if fx:
            fx_blocks.append(tag)

    def stale(value, days):
        age = (today - date.fromisoformat(value)).days
        return age < 0 or age > days

    rates = {r["currency"]: dec(r["usd_per_unit"]) for r in b["fx"]}
    if rates.get("USD") != 1 or any(r <= 0 for r in rates.values()):
        raise ValueError("Invalid USD-per-local FX")
    for row in b["fx"]:
        cite("fx.csv", row)
        if stale(row["as_of"], rules["fx_max_days"]):
            problem("fx_date_unusable", row["currency"], "fx.csv", row, ["as_of", "usd_per_unit"], True, False, True)
    account_values = defaultdict(Decimal)
    nav = Decimal(0)
    for p in b["positions"]:
        if p["account_id"] not in accounts or dec(p["quantity"]) < 0 or dec(p["reported_market_value_usd"]) < 0:
            raise ValueError("Invalid included long-only holding")
        if type(p["settled"]) is not bool or type(p["restricted"]) is not bool:
            raise ValueError("Invalid cash eligibility flags")
        cite("positions.csv", p)
        q = tables["prices"][p["price_id"]]
        cite("prices.csv", q)
        value = dec(p["reported_market_value_usd"])
        nav += value
        account_values[p["account_id"]] += value
        cash_position = p["asset_class"] == "Cash"
        if q["quote_divisor"] not in (1, 100) or dec(q["price"]) < 0 or dec(q["accrued_per_100"]) < 0:
            raise ValueError("Invalid quote units")
        if (q["security_id"], q["currency"]) != (p["security_id"], p["currency"]):
            problem("price_identity_conflict", p["position_id"], "prices.csv", q, ["security_id", "currency"], True, cash_position)
        local = dec(p["quantity"]) / dec(q["quote_divisor"]) * (dec(q["price"]) + dec(q["accrued_per_100"]))
        if max(abs(local - dec(p["reported_market_value_local"])), abs(local * rates[p["currency"]] - value)) > dec("0.01"):
            problem("valuation_source_conflict", p["position_id"], "prices.csv", q, ["price", "accrued_per_100"], True, cash_position)
        max_days = rules["private_valuation_max_days"] if p["valuation_method"] == "administrator_nav" else rules["listed_valuation_max_days"]
        for file, row, identifier in (("positions.csv", p, p["position_id"]), ("prices.csv", q, q["price_id"])):
            if stale(row["valuation_as_of"], max_days):
                problem("valuation_date_unusable", identifier, file, row, ["valuation_as_of", "received_at"], True, cash_position)
        if p["instrument_type"] != "fund":
            exposures.append(dict(p, value=value, parent_id=p["position_id"]))
            continue
        covered = Decimal(0)
        for row in b["lookthrough"]:
            if row["position_id"] != p["position_id"]:
                continue
            cite("lookthrough.csv", row)
            weight = dec(row["weight"])
            if not 0 <= weight <= 1:
                raise ValueError("Invalid fund weight")
            if stale(row["as_of"], rules["lookthrough_max_days"]):
                problem("lookthrough_date_unusable", row["row_id"], "lookthrough.csv", row, ["as_of"])
                continue
            covered += weight
            exposures.append(dict(row, value=value * weight, parent_id=p["position_id"]))
        if covered > 1:
            raise ValueError("Fund weights exceed 100 percent")
        if covered < 1:
            incomplete.append(p["position_id"])
            exposures.append({"parent_id": p["position_id"], "asset_class": "Unknown", "value": value * (1 - covered),
                              "exposure_currency": "Unknown", "issuer_type": "unknown", "sector": "Unknown"})
            problem("lookthrough_incomplete", p["position_id"], "positions.csv", p, ["reported_market_value_usd"])
    if nav <= 0 or set(account_values) != set(tables["custodian_totals"]):
        raise ValueError("Missing account/NAV coverage")
    for t in b["custodian_totals"]:
        cite("custodian_totals.csv", t)
        if account_values[t["account_id"]] != dec(t["reported_total_usd"]) or t["as_of"] != b["review_as_of"]:
            problem("account_total_conflict", t["account_id"], "custodian_totals.csv", t, ["reported_total_usd", "as_of"], True, True)
    if set(tables["capital_accounts"]) != {p["position_id"] for p in b["positions"] if p["asset_class"] == "Private equity"}:
        raise ValueError("Missing capital account coverage")
    for c in b["capital_accounts"]:
        cite("capital_accounts.csv", c)
        bridge = sum(dec(c[k]) * sign for k, sign in (("opening_nav", 1), ("contributions_qtd", 1),
            ("distributions_qtd", -1), ("management_fees_qtd", -1), ("other_expenses_qtd", -1),
            ("investment_income_qtd", 1), ("realized_gain_qtd", 1), ("unrealized_gain_qtd", 1)))
        if bridge != dec(c["ending_nav"]) or dec(c["ending_nav"]) != dec(tables["positions"][c["position_id"]]["reported_market_value_usd"]):
            problem("capital_nav_bridge_conflict", c["position_id"], "capital_accounts.csv", c, ["opening_nav", "ending_nav"], True)
        if dec(c["commitment"]) - dec(c["contributed_itd"]) != dec(c["unfunded_commitment"]):
            problem("unfunded_bridge_conflict", c["position_id"], "capital_accounts.csv", c, ["commitment", "contributed_itd", "unfunded_commitment"])
    allocation, issuers = defaultdict(Decimal), defaultdict(Decimal)
    for e in exposures:
        allocation[e["asset_class"]] += e["value"]
        if e["issuer_type"] == "corporate" and e["asset_class"] in ("Equity", "Fixed income"):
            issuers[e["issuer_group"]] += e["value"]
    pct = {key: value * 100 / nav for key, value in allocation.items()}
    out = [key for key, (lo, hi) in rules["allocation_bands_pct"].items() if not dec(lo) <= pct.get(key, 0) <= dec(hi)]
    top = max(issuers, key=issuers.get, default="None")
    top_value = issuers.get(top, Decimal(0))
    digital = allocation["Digital assets"] if rules["digital_scope"] == "direct_and_lookthrough" else sum(dec(p["reported_market_value_usd"]) for p in b["positions"] if p["asset_class"] == "Digital assets" and p["instrument_type"] != "fund")
    foreign = sum(e["value"] for e in exposures if e["exposure_currency"] not in ("USD", "Unknown"))
    cash = sum(dec(p["reported_market_value_usd"]) for p in b["positions"] if p["asset_class"] == "Cash" and p["settled"] and not p["restricted"])
    horizon = today + timedelta(days=rules["cash_horizon_days"])
    flows = {"in": Decimal(0), "out": Decimal(0)}
    for row in b["cash_flows"]:
        cite("cash_flows.csv", row)
        due = date.fromisoformat(row["due_date"])
        if type(row["confirmed"]) is not bool or dec(row["amount"]) < 0:
            raise ValueError("Invalid cash flow")
        eligible = (due <= horizon and row["settlement_status"] == "unpaid") if row["direction"] == "out" else (today <= due <= horizon and row["settlement_status"] == "unreceived")
        if row["confirmed"] and eligible:
            flows[row["direction"]] += dec(row["amount"]) * rates[row["currency"]]
    ratio = (cash + flows["in"]) / flows["out"] if flows["out"] else None
    unwaived, waivers = set(), set()
    for ex in b["exceptions"]:
        cite("exceptions.csv", ex)
    for e in exposures:
        if e["sector"] not in rules["restricted_sectors"]:
            continue
        p = tables["positions"][e["parent_id"]]
        valid = [ex for ex in b["exceptions"] if (ex["position_id"], ex["account_id"], ex["policy_id"], ex["rule_id"], ex["approved_role"]) ==
                 (p["position_id"], p["account_id"], policy["policy_id"], "restricted_sector", policy["governance"]["exception_authority"])
                 and date.fromisoformat(ex["approved_on"]) <= today <= date.fromisoformat(ex["valid_until"])]
        if valid:
            waivers.update(ex["exception_id"] for ex in valid)
        else:
            unwaived.add(p["position_id"])
    policy_ref = cite(f"policy-{policy['version']}.json", policy)
    partial = ["uncovered_fund:" + pid for pid in incomplete]
    fmt = lambda v: format(v, ".2f")
    observations = [
        {"usd": {k: fmt(v) for k, v in sorted(allocation.items())}, "pct": {k: fmt(v) for k, v in sorted(pct.items())}, "out_of_band": out},
        {"issuer_group": top, "usd": fmt(top_value), "pct": fmt(top_value * 100 / nav), "limit_pct": rules["issuer_max_pct"]},
        {"usd": fmt(digital), "pct": fmt(digital * 100 / nav), "scope": rules["digital_scope"], "limit_pct": rules["digital_max_pct"]},
        {"usd": fmt(foreign), "pct": fmt(foreign * 100 / nav), "limit_pct": rules["foreign_currency_gross_max_pct"], "basis": "gross exposure; no hedge offsets"},
        {"settled_unrestricted_cash_usd": fmt(cash), "confirmed_incoming_usd": fmt(flows["in"]), "confirmed_outgoing_usd": fmt(flows["out"]),
         "coverage_ratio": format(ratio, ".4f") if ratio is not None else None, "minimum_ratio": rules["cash_funding_min_ratio"],
         "shortfall_to_policy_usd": fmt(max(Decimal(0), flows["out"] * dec(rules["cash_funding_min_ratio"]) - cash - flows["in"])), "horizon_end": horizon.isoformat()},
        {"unwaived_positions": sorted(unwaived), "valid_exception_ids": sorted(waivers)},
        {"issues": issues}]
    breaches = [bool(out), top_value * 100 / nav > dec(rules["issuer_max_pct"]), digital * 100 / nav > dec(rules["digital_max_pct"]),
                foreign * 100 / nav > dec(rules["foreign_currency_gross_max_pct"]), ratio is not None and ratio < dec(rules["cash_funding_min_ratio"]), bool(unwaived), bool(issues)]
    blockers = [nav_blocks + partial, nav_blocks + ([] if breaches[1] else partial),
                nav_blocks + (partial if rules["digital_scope"] == "direct_and_lookthrough" else []),
                nav_blocks + partial, fx_blocks + cash_blocks, partial, [i["code"] + ":" + i["record_id"] for i in issues]]
    findings = []
    for rule, observed, breach, limits in zip(CONTROLS, observations, breaches, blockers):
        refs = list(evidence.values())
        if rule == "cash_funding":
            refs = [r for r in refs if r["file"] in ("positions.csv", "fx.csv", "cash_flows.csv")]
        elif rule == "restricted_sector":
            refs = [r for r in refs if r["file"] in ("positions.csv", "lookthrough.csv", "exceptions.csv")]
        elif rule == "source_quality":
            refs = [i["evidence"] for i in issues]
        else:
            refs = [r for r in refs if r["file"].endswith(".csv") and r["file"] not in ("cash_flows.csv", "exceptions.csv")]
        refs = [dict(policy_ref, policy_page=policy["pdf_pages"][rule]), *refs]
        findings.append({"rule_id": rule, "business_state": "needs_source" if limits else "review_required" if breach else "within_policy",
                         "as_reported_status": "review_required" if breach else "within_policy", "observed": observed,
                         "limitations": sorted(set(limits)), "evidence": refs})
    status = "NEEDS_SOURCE" if any(blockers) else "REVIEW_REQUIRED" if any(breaches) else "READY_FOR_HUMAN_REVIEW"
    return {"case_id": b["case_id"], "active_policy_id": policy["policy_id"], "as_reported_nav_usd": fmt(nav),
            "status": status, "findings": findings, "input_sha256": case["manifest"]["input_sha256"],
            "calculation": {"engine": "independent-decimal@1", "positions": len(b["positions"]),
                            "lookthrough_rows": len(b["lookthrough"]), "nav_basis": "reported values once; underlying replaces fund",
                            "unfunded_commitments_usd": fmt(sum(dec(c["unfunded_commitment"]) for c in b["capital_accounts"]))}}
