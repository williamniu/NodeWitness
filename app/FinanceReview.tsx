"use client";

import Link from "next/link";
import { Background, Controls, Handle, Position, ReactFlow, ReactFlowProvider, type NodeProps, type Node } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import styles from "./finance.module.css";

type Evidence = { source_id: string; file: string; record_id: string; fields: string[]; file_sha256: string; source_date: string | null; policy_page: number | null };
type Finding = { finding_id: string; rule_id: string; business_state: string; explanation: string; observed: Record<string, unknown>; limitations: string[]; evidence: Evidence[]; model_citations: string[] };
type Review = { run_id: string; case_id: string; status: string; summary: string; input_sha256: string; active_policy_id: string; review_as_of: string; as_reported_nav_usd: string; findings: Finding[]; approval: { status: string; reviewer?: string; rationale?: string; invalidation_reason?: string }; handoff: { accepted_at: string | null }; source_inventory: { source_id: string; file: string; sha256: string; quality_state: string }[]; suggested_actions: { action_id: string; description: string; owner_role: string; due: string }[]; sources_to_recheck: { request_id: string; requested_confirmation: string; owner_role: string }[]; source_changes: unknown[]; policy_changes: { rule_id: string; before: unknown; after: unknown }[] };
type Event = { id: string; at: string; type: string; node: string; depends_on: string[]; data: unknown };
type RecordRun = { run_id: string; status: string; case_id: string; arm: string; events: Event[]; tool_calls: number; elapsed_seconds?: number; error?: string; model_identity?: { model: string; digest: string } };
type Comparison = { experiment_id: string; expected_trials: number; observed_trials: number; missing_trials: number; arms: Record<string, { trials: number; released_correct: number; first_candidate_correct: number; failures: number; citations_valid: number; forbidden_attempts: number; forbidden_effects: number; mean_seconds: number }> };
type State = { csrf: string; head: { revision: number; source_case: string; run_id: string | null }; package: Review | null; package_sha256: string | null; record: RecordRun | null; running_record?: RecordRun; verified: boolean; runs: { run_id: string; case_id: string; status: string; verified: boolean }[]; jobs: { id: string; state: string }[]; audit: { id: number; at: string; kind: string; body: unknown }[]; comparison: Comparison | null };
type FlowData = { label: string; detail: string; state: string; number: string };
type FlowNode = Node<FlowData, "review">;

function ReviewNode({ data, selected }: NodeProps<FlowNode>) {
  const label = data.state === "pass" ? "Step completed" : data.state === "attention" ? "Needs human review" : data.state === "review" ? "Step failed" : data.state;
  return <div className={`agent-node status-${data.state} ${selected ? "is-selected" : ""}`}><Handle type="target" position={Position.Left} /><div className="node-kicker"><span>{data.number} / OBSERVED NODE</span><i className="node-health" /></div><strong>{data.label}</strong><p>{data.detail}</p><div className="node-footer"><span className="node-status">{label}</span><span className="node-run">{data.state === "idle" ? "Awaiting execution" : "Trace recorded"}</span></div><Handle type="source" position={Position.Right} /></div>;
}
const nodeTypes = { review: ReviewNode };
const STEPS = [
  ["ingestion", "Source integrity", "Case files, units & hashes"],
  ["inspect_sources", "Mandate investigation", "IPS pages & manager notes"],
  ["compute_review", "Seven financial controls", "Money arithmetic & source limits"],
  ["qwen", "Agent review", "Explanations & bounded proposals"],
  ["submission", "Submission gate", "Claims, citations & completeness"],
  ["handoff", "Principal review package", "Version-bound human decision"],
];
const money = (value: string | undefined) => value ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(Number(value)) : "—";
const title = (value: string) => value.replaceAll("_", " ");
const metricLabels: Record<string, string> = {
  issuer_group: "Issuer group", usd: "Gross exposure", pct: "Share of NAV", limit_pct: "Policy maximum",
  settled_unrestricted_cash_usd: "Eligible cash", confirmed_incoming_usd: "Confirmed receipts", confirmed_outgoing_usd: "Dated obligations",
  coverage_ratio: "Funding coverage", minimum_ratio: "Required coverage", shortfall_to_policy_usd: "Funding shortfall",
  horizon_end: "Funding horizon", scope: "Exposure scope", basis: "Calculation basis", unwaived_positions: "Holdings requiring a waiver", valid_exception_ids: "Valid exceptions",
};
const policyLabels: Record<string, string> = {
  allocation_bands_pct: "Allocation bands", cash_funding_min_ratio: "Minimum funding coverage",
  digital_max_pct: "Digital exposure maximum", digital_scope: "Digital exposure scope",
  foreign_currency_gross_max_pct: "Foreign currency maximum", issuer_max_pct: "Issuer group maximum",
};
const policyValue = (value: unknown): string => typeof value === "string" ? value.replaceAll("_", " ") : JSON.stringify(value);

function Observations({ finding }: { finding: Finding }) {
  const value = finding.observed;
  if (finding.rule_id === "asset_allocation") {
    const dollars = value.usd as Record<string, string>;
    const percentages = value.pct as Record<string, string>;
    return <table className={styles.observations}><thead><tr><th>Asset class</th><th>Reported exposure</th><th>Share of NAV</th></tr></thead><tbody>{Object.entries(dollars).map(([key, amount]) => <tr key={key}><td>{key}</td><td>{money(amount)}</td><td>{percentages[key]}%</td></tr>)}</tbody></table>;
  }
  if (finding.rule_id === "source_quality") {
    const issues = value.issues as { code: string; record_id: string }[];
    return issues.length ? <ul>{issues.map((issue, i) => <li key={i}>{title(issue.code)} · {issue.record_id}</li>)}</ul> : <p>No source-quality issue identified within the checks performed.</p>;
  }
  return <dl className={styles.observationGrid}>{Object.entries(value).map(([key, amount]) => {
    const display = Array.isArray(amount) ? amount.join(", ") || "None" : key.endsWith("_usd") || key === "usd" ? money(String(amount)) : key === "pct" || key === "limit_pct" ? `${amount}%` : amount === null ? "Not applicable" : String(amount).replaceAll("_", " ");
    return <div key={key}><dt>{metricLabels[key] || title(key)}</dt><dd>{display}</dd></div>;
  })}</dl>;
}

function Workbench() {
  const [state, setState] = useState<State | null>(null);
  const [selectedRun, setSelectedRun] = useState("");
  const [selected, setSelected] = useState("compute_review");
  const [tab, setTab] = useState("findings");
  const [findingId, setFindingId] = useState("issuer_concentration");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewer, setReviewer] = useState("");
  const [rationale, setRationale] = useState("");
  const [replacement, setReplacement] = useState("F01");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [evidenceRecord, setEvidenceRecord] = useState<unknown>(null);
  const refresh = useCallback(async () => {
    const response = await fetch(`/api/finance${selectedRun ? `?run_id=${encodeURIComponent(selectedRun)}` : ""}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    setState(result);
  }, [selectedRun]);
  useEffect(() => {
    let alive = true;
    const load = () => refresh().catch((error) => { if (alive) setNotice(String(error.message)); });
    void load();
    const interval = setInterval(load, 2500);
    return () => { alive = false; clearInterval(interval); };
  }, [refresh]);
  const act = async (operation: string, payload?: object) => {
    if (!state) return;
    setBusy(true); setNotice("");
    try {
      const response = await fetch("/api/finance", { method: "POST", headers: { "Content-Type": "application/json", "x-nw-local-token": state.csrf }, body: JSON.stringify({ operation, payload }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      setNotice(operation === "start" ? "Qwen review started. Progress below comes from observed execution records." : "Operator action recorded. Source and package bindings have been checked.");
      if (operation === "start" || operation === "source_update" || operation === "correct_quote") setSelectedRun("");
      await refresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Request failed"); }
    finally { setBusy(false); }
  };
  const p = state?.package;
  const evidenceRun = p?.run_id;
  useEffect(() => {
    if (!evidence || !evidenceRun) return;
    let active = true;
    fetch(`/api/finance?source=${encodeURIComponent(evidence.file)}&record_id=${encodeURIComponent(evidence.record_id)}&run_id=${evidenceRun}`)
      .then((response) => response.json()).then((result) => { if (active) setEvidenceRecord(result); });
    return () => { active = false; };
  }, [evidence, evidenceRun]);
  const running = state?.jobs.some((j) => j.state === "running");
  const comparisonRunning = !!state?.comparison && state.comparison.observed_trials < state.comparison.expected_trials;
  const record = running && !selectedRun ? state?.running_record || state?.record : state?.record;
  const events = record?.events || [];
  const finding = p?.findings.find((f) => f.rule_id === findingId) || p?.findings[0];
  const isCurrent = !!p && state?.head.run_id === p.run_id;
  const nodes = useMemo<FlowNode[]>(() => STEPS.map(([id, label, detail], i) => {
    const matching = (record?.events || []).filter((e) => e.node === id);
    const last = matching.at(-1);
    let status = !last ? "idle" : last.type.includes("failed") ? "review" : last.type.includes("started") ? "running" : "pass";
    if (id === "handoff" && p && !running) status = p.approval.status === "approved" ? "pass" : "attention";
    return { id, type: "review", position: { x: (i % 3) * 280 + 25, y: Math.floor(i / 3) * 220 + 60 }, data: { label, detail, state: status, number: String(i + 1).padStart(2, "0") }, selected: selected === id };
  }), [record, selected, p, running]);
  const edges = STEPS.slice(1).map(([id], i) => ({ id: "edge-" + id, source: STEPS[i][0], target: id, type: "smoothstep", animated: !!running }));
  const decision = (status: string) => act("decide", { request_id: crypto.randomUUID(), run_id: p?.run_id, revision: state?.head.revision, package_sha256: state?.package_sha256, status, reviewer, rationale });

  return <main className={styles.shell}>
    <header className="topbar"><div className="brand-lockup"><div className="brand-mark"><span /></div><div><strong>NodeWitness</strong><small>Human-governed agent review</small></div></div><div className="workspace-title"><small>Aurora Family Office · synthetic</small><strong>Investment governance / Principal review</strong></div><nav className="top-actions"><Link href="/legacy" className="quiet-button">Legacy sample</Link><Link href="/environments" className="quiet-button">Engineering evidence ↗</Link><span className="runtime-badge"><i />Local Qwen</span></nav></header>
    <div className={styles.scope}>SYNTHETIC WORKSPACE <span>Review date 31 Oct 2026 · One local operator · Sign-off acknowledges this package; proposed actions require a separate decision.</span><b>{running && !selectedRun ? "RUNNING NOW" : selectedRun ? "HISTORICAL RUN" : "RECORDED EXECUTION"}</b></div>
    <section className={styles.workbench}>
      <aside className={`left-panel panel-scroll ${styles.left}`}><div className="panel-heading"><span>NW</span><div><small>MANDATE → EVIDENCE → REVIEW</small><h2>A review you can inspect</h2></div></div><p className={styles.description}>Track which sources changed, what was calculated, and what the principal must review next.</p>
        <label className="field-label" htmlFor="run-select">Recorded run</label><select id="run-select" className={styles.select} value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)}><option value="">Current workspace</option>{state?.runs.map((r) => <option key={r.run_id} value={r.run_id}>{r.case_id} · {r.run_id} · {r.status}</option>)}</select>
        <button className="primary-button" disabled={busy || running || comparisonRunning} onClick={() => void act("start")}><span>{running ? "Review in progress…" : comparisonRunning ? "Comparison in progress…" : "Run a fresh Qwen review"}</span><span>↗</span></button>
        <p className={styles.help}>Uses the installed local model. Each step and failure is retained. No demo fallback.</p>
        <div className="section-rule"><span>AUTHORITATIVE INPUTS</span><em>Workspace v{state?.head.revision || 1}</em></div>
        <a className="source-card" href="/demo/finance-review/v1/documents/ips-v2.pdf" target="_blank" rel="noreferrer"><span className="source-icon">IPS</span><div><strong>IPS v2 · Effective mandate</strong><small>Concentration, funding, exposure & evidence</small></div><span>↗</span></a>
        <a className="source-card" href="/demo/finance-review/v1/documents/ips-v1.pdf" target="_blank" rel="noreferrer"><span className="source-icon">PDF</span><div><strong>IPS v1 · Historical</strong><small>Policy changes retained for review</small></div><span>↗</span></a>
        <div className="source-card active"><span className="source-icon">DATA</span><div><strong>{state?.head.source_case || "F00"} · 30 holdings / 4 accounts</strong><small>File hashes checked on each run</small></div><span className="source-state">HASH</span></div>
        <details className={styles.update}><summary>Replace source / correct extraction</summary><p className={styles.help}>An explicit synthetic snapshot creates a new version and invalidates the old decision. F01 reallocates reported holdings in a source scenario; no trade is executed.</p><label className="field-label" htmlFor="replacement">Replacement snapshot</label><select id="replacement" className={styles.select} value={replacement} onChange={(e) => setReplacement(e.target.value)}>{["F00 · Original", "F01 · Corrected holdings", "F02 · Missing fund coverage", "F03 · Stale valuation", "F04 · Expired exception", "F05 · Conflicting quote", "F06 · Hostile manager note"].map((s) => <option key={s} value={s.slice(0, 3)}>{s}</option>)}</select><button className="correction-button" disabled={busy || running} onClick={() => void act("source_update", { request_id: crypto.randomUUID(), revision: state?.head.revision, replacement_case_id: replacement, reason: "Local operator confirms this synthetic replacement source snapshot for a new review." })}>Confirm replacement source</button><button className="correction-button" disabled={busy || running || state?.head.source_case !== "F05"} onClick={() => void act("correct_quote", { request_id: crypto.randomUUID().replaceAll("-", ""), revision: state?.head.revision, position_id: "P02", source_evidence: "positions.csv:P02", reason: "Correct P02 quote extraction against custodian quantity and local market value." })}>Correct P02 quote from custodian evidence</button><p className={styles.help}>After replacement or correction, run a fresh review. Free text cannot overwrite calculated values.</p></details>
        <div className="section-rule"><span>RUN BINDING</span></div><p className={styles.hash}>{p?.input_sha256 || "No current package. Start a review."}</p><p className={styles.help}>{record?.model_identity?.model}<br />{record?.model_identity?.digest.slice(0, 20)}…</p>
      </aside>
      <section className={styles.center}><div className={styles.graphBar}><div><small>OBSERVED WORKFLOW</small><h1>{p ? title(p.status) : "From sources to principal review"}</h1></div><span>{record?.run_id || "Awaiting execution"}{p && !isCurrent && <small className={styles.historyNote}>Historical package · workspace source is {state?.head.source_case} / revision {state?.head.revision}</small>}</span></div><div className={styles.graph}><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={(_, node) => setSelected(node.id)} nodesDraggable={false} fitView fitViewOptions={{ padding: .18 }} minZoom={.35} maxZoom={1.2}><Background color="#1b3b49" gap={24} size={1} /><Controls showInteractive={false} /></ReactFlow></div><div className={styles.metrics}><div><small>REPORTED NAV</small><strong>{money(p?.as_reported_nav_usd)}</strong></div><div><small>CONTROL ISSUES</small><strong>{p?.findings.filter((f) => f.business_state !== "within_policy").length ?? "—"}<em> / 7</em></strong></div><div><small>NUMBERS & SOURCE LINKS</small><strong>{p ? state?.verified ? "Verified" : "Failed / incomplete" : "Pending"}</strong></div><div><small>HUMAN DECISION</small><strong className={styles.amber}>{p?.approval.status || "pending"}</strong></div></div>{notice && <p className={styles.notice} role="status">{notice}</p>}{record?.error && <p className={styles.notice}>{record.error}</p>}</section>
      <aside className={`right-panel panel-scroll ${styles.inspector}`}><div className="inspector-topline"><span>EXECUTION INSPECTOR</span><code>{selected}</code></div><div className="inspector-title"><div className="inspector-icon">TRACE</div><div><h2>{STEPS.find((s) => s[0] === selected)?.[1]}</h2><span className="status-pill">{record?.status || "pending"}</span></div></div><p className="inspector-summary">Every event below is recorded by the runtime. Source hashes and dependencies remain attached.</p>
        <div className={styles.nodeEvents}>{events.filter((e) => e.node === selected).map((e) => <details key={e.id}><summary>{e.id} · {e.type} <time>{new Date(e.at).toLocaleTimeString()}</time></summary><pre>{JSON.stringify({ dependencies: e.depends_on, ...typeof e.data === "object" ? e.data as object : { data: e.data } }, null, 2)}</pre></details>)}{!events.some((e) => e.node === selected) && <p className={styles.help}>No observed event for this node yet.</p>}</div>
        <div className="section-rule"><span>PRINCIPAL SIGN-OFF</span></div><p className={styles.help}>Local identity declaration only. Approving acknowledges the exact review and proposals; it cannot execute a trade or message.</p><label className="field-label" htmlFor="reviewer">Reviewer name</label><input id="reviewer" className={styles.input} value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Review Principal" /><label className="field-label" htmlFor="rationale">Decision rationale</label><textarea id="rationale" className={styles.input} value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="What did you review, and what remains to be resolved?" /><div className={styles.decisionButtons}><button disabled={busy || !isCurrent || !state?.verified || p?.status === "NEEDS_SOURCE" || reviewer.trim().length < 2 || rationale.trim().length < 2} onClick={() => void decision("approved")}>Acknowledge package</button><button disabled={busy || !isCurrent || reviewer.trim().length < 2 || rationale.trim().length < 2} onClick={() => void decision("rejected")}>Return for revision</button></div><button className="correction-button" disabled={busy || !isCurrent || p?.approval.status !== "approved"} onClick={() => void act("handoff", { request_id: crypto.randomUUID(), run_id: p?.run_id, revision: state?.head.revision, package_sha256: state?.package_sha256 })}>Accept principal handoff</button>{p?.approval.reviewer && <p className={styles.help}>{p.approval.status} · {p.approval.reviewer}<br />{p.approval.rationale}<br />{p.approval.invalidation_reason}</p>}{p?.handoff.accepted_at && <p className={styles.help}>Handoff accepted: {p.handoff.accepted_at}</p>}
      </aside>
    </section>
    <section className={styles.drawer}><nav>{["findings", "actions", "sources", "package", "audit", "comparison"].map((s) => <button key={s} className={tab === s ? styles.active : ""} onClick={() => setTab(s)}>{title(s)}</button>)}</nav><div className={styles.drawerBody}>
      {tab === "findings" && <div className={styles.findings}><div className={styles.findingNav}>{p?.findings.map((f) => <button key={f.rule_id} onClick={() => setFindingId(f.rule_id)} className={finding?.rule_id === f.rule_id ? styles.active : ""}><i data-state={f.business_state} /><span>{title(f.rule_id)}</span><small>{title(f.business_state)}</small></button>)}</div>{finding && <article className={styles.findingDetail}><small>{title(finding.business_state).toUpperCase()}</small><h2>{title(finding.rule_id)}</h2><p>{finding.explanation}</p><Observations finding={finding} />{finding.limitations.length > 0 && <p className={styles.amber}>{finding.limitations.join(" · ")}</p>}<div className={styles.citations}>{finding.model_citations.map((id) => { const ref = finding.evidence.find((e) => `${e.file}:${e.record_id}` === id); return <button key={id} onClick={() => ref && setEvidence(ref)}>{id} ↗</button>; })}</div></article>}</div>}
      {tab === "actions" && <div className={styles.cards}>{p?.suggested_actions.map((a) => <article key={a.action_id}><small>PROPOSED / NO EXECUTION</small><h3>{title(a.action_id.replace("ACT-", ""))}</h3><p>{a.description}</p><span>{a.owner_role} · {a.due}</span></article>)}{p?.sources_to_recheck.map((r) => <article key={r.request_id}><small>SOURCE CONFIRMATION REQUIRED</small><p>{r.requested_confirmation}</p><span>{r.owner_role}</span></article>)}{!p?.suggested_actions.length && <p className={styles.help}>No remediation proposed for the current scope. Human review is still required.</p>}</div>}
      {tab === "sources" && <div className={styles.cards}>{p?.source_inventory.map((s) => <article key={`${s.source_id}:${s.file}`}><small>{s.source_id} · {s.quality_state}</small><h3>{s.file}</h3><p className={styles.hash}>{s.sha256}</p><a href={`/demo/finance-review/v1/cases/${p.case_id}/${s.file}`} target="_blank" rel="noreferrer">Original approved source ↗</a></article>)}</div>}
      {tab === "package" && <div className={styles.package}><div><small>ACTUAL QWEN DRAFT / {p?.approval.status || "PENDING"}</small><h2>Principal review package</h2><p>{p?.summary || "Run a review to create a completed draft."}</p><div className={styles.downloads}>{p && ["pdf", "md", "json"].map((format) => <a key={format} href={`/api/finance?download=${format}&run_id=${p.run_id}`}>Download {format.toUpperCase()} ↗</a>)}</div></div><div><h3>Mandate changes</h3>{p?.policy_changes.map((c) => <p key={c.rule_id}><b>{policyLabels[c.rule_id] || title(c.rule_id)}</b> · {policyValue(c.before)} → {policyValue(c.after)}</p>)}<p>{p?.source_changes.length || 0} source revision records · exact evidence and hashes in JSON.</p></div></div>}
      {tab === "audit" && <div className={styles.audit}>{state?.audit.map((a) => <details key={a.id}><summary>{a.at} · {a.kind}</summary><pre>{JSON.stringify(a.body, null, 2)}</pre></details>)}</div>}
      {tab === "comparison" && <div className={styles.comparison}><h2>Same sources, same Qwen, same numerical tools</h2><p>Both modes use the same calculator. The governed mode checks a draft before release. Versioned approvals are tested separately; reviewer time savings are unmeasured.</p>{state?.comparison ? <><small>{state.comparison.experiment_id} · {state.comparison.observed_trials}/{state.comparison.expected_trials} trials · {state.comparison.missing_trials} missing</small><table><thead><tr><th>Mode</th><th>First candidate correct</th><th>Released & correct</th><th>Failures</th><th>Forbidden effects</th><th>Mean time</th></tr></thead><tbody>{Object.entries(state.comparison.arms).map(([arm, a]) => <tr key={arm}><td>{arm}</td><td>{a.first_candidate_correct}/{a.trials}</td><td>{a.released_correct}/{a.trials}</td><td>{a.failures}</td><td>{a.forbidden_effects}</td><td>{a.mean_seconds.toFixed(1)} s</td></tr>)}</tbody></table></> : <p>Frozen comparison has not completed. Development runs are excluded.</p>}</div>}
    </div></section>
    {evidence && <div className="evidence-modal" role="dialog" aria-modal="true" aria-label="Source evidence"><div className={`evidence-modal-card ${styles.evidenceCard}`}><header><div><small>RECORD / FIELD / HASH</small><strong>{evidence.file}:{evidence.record_id}</strong></div><button onClick={() => setEvidence(null)} aria-label="Close source evidence">×</button></header><div className={styles.evidenceBody}><p>Source: {evidence.source_id} · Measurement: {evidence.source_date || "See source record"}</p><p>Fields: {evidence.fields.join(", ")}</p><pre className={styles.recordPreview}>{JSON.stringify(evidenceRecord, null, 2)}</pre><p className={styles.hash}>SHA256: {evidence.file_sha256}</p>{evidence.policy_page ? <iframe title="IPS policy evidence" src={`/demo/finance-review/v1/documents/ips-v2.pdf#page=${evidence.policy_page}`} /> : <p>Full source record and calculation receipts are preserved in the run. Download the JSON package for exact field-level references.</p>}<a href={`/demo/finance-review/v1/cases/${p?.case_id}/${evidence.file}`} target="_blank" rel="noreferrer">Open original approved source ↗</a></div></div></div>}
  </main>;
}

export default function FinanceReview() { return <ReactFlowProvider><Workbench /></ReactFlowProvider>; }
