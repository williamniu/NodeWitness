"use client";

import Link from "next/link";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import {
  ACTION_PROPOSALS,
  GRAPH_EDGES,
  POLICIES,
  affectedNodesForSourceChange,
  applyAffectedWorkflow,
  buildWorkflow,
  canExecuteLocalAction,
  createAuditEvent,
  diffPolicy,
  downstreamNodes,
  isNormalizedRuntimeResult,
  nextSourceUpdatePhase,
  searchWorkflowNodes,
  type AuditEvent,
  type GovernanceDecisionStatus,
  type NodeStatus,
  type NormalizedRuntimeResult,
  type PolicyVersion,
  type SourceUpdatePhase,
  type WorkflowNode,
} from "@/lib/workflow";
import { Fragment, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

type AgentData = WorkflowNode["data"];
type AgentFlowNode = Node<AgentData, "agent">;
type Decision = { status: GovernanceDecisionStatus; original: string; edited?: string };
type Artifact = { id: string; title: string; filename: string; content: string };
type RemediationCase = {
  id: string;
  title: string;
  severity: "High";
  status: "Open";
  client: string;
  sourceVersions: string;
  violatedRule: string;
  observedExposure: string;
  threshold: string;
  evidence: string;
  approvedDescription: string;
  owner: string;
  dueDateSuggestion: string;
  auditReferences: string[];
};

const SOURCE_UPDATE_NODES = affectedNodesForSourceChange("source.version.changed");
const DEFAULT_WORKFLOW_BRIEF = "Monitor the Aurora Family Office investment policy and portfolio. Extract mandate rules, detect source changes, re-run only affected checks, and propose reviewable remediation when a limit is breached. Never act without approval.";
const LIVE_REQUEST_TIMEOUT_MS = 23_000;
const MONITORING_CHECK = {
  baseline: "18 Jul 2026 · 09:30:04 ET",
  revision: "18 Jul 2026 · 10:14:22 ET",
};
const UPDATE_PROGRESS: Record<SourceUpdatePhase, { label: string; value: number }> = {
  idle: { label: "No change detected", value: 0 },
  detected: { label: "Change detected", value: 15 },
  queued: { label: "Affected nodes queued", value: 38 },
  running: { label: "Re-evaluating crypto branch", value: 74 },
  complete: { label: "Re-run complete", value: 100 },
};

const baseAudit: AuditEvent[] = [
  { id: "a5", time: "09:30:07", type: "compliance.conclusion", detail: "IPS v1 crypto rule: Pass (2.0% direct vs 10.0% maximum)", actor: "Compliance evaluation" },
  { id: "a4", time: "09:30:07", type: "node.completed", detail: "Crypto branch completed - run-aurora-001", actor: "Runtime" },
  { id: "a3", time: "09:30:06", type: "rule.extracted", detail: "Direct cryptocurrency exposure <= 10%", actor: "Policy extraction" },
  { id: "a2", time: "09:30:05", type: "source.uploaded", detail: "aurora-ips-v1.pdf registered as baseline", actor: "Source monitor" },
  { id: "a1", time: "09:30:05", type: "node.started", detail: "Initial workspace generation", actor: "Runtime" },
];

const initialDecisions = () =>
  Object.fromEntries(ACTION_PROPOSALS.map((action) => [action.id, { status: "pending", original: action.summary }])) as Record<string, Decision>;

function statusLabel(status: NodeStatus) {
  return status === "review" ? "Review required" : status[0].toUpperCase() + status.slice(1);
}

function AgentNodeCard({ data, selected }: NodeProps<AgentFlowNode>) {
  return (
    <div className={`agent-node status-${data.status} ${selected ? "is-selected" : ""}`} aria-label={`${data.label}: ${statusLabel(data.status)}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-kicker">
        <span>{data.kind}</span>
        <i className="node-health" aria-hidden="true" />
      </div>
      <strong>{data.label}</strong>
      <p>{data.description}</p>
      <div className="node-footer">
        <span className="node-status">{statusLabel(data.status)}</span>
        <span className="node-run">{data.runId.match(/run-aurora-(\d+)/)?.[1] ?? "---"}</span>
      </div>
      {data.humanModified && <div className="human-flag">Human modified</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { agent: AgentNodeCard };

function Highlight({ text, query }: { text: string; query: string }) {
  const clean = query.trim();
  if (!clean) return text;
  const parts = text.split(new RegExp(`(${clean.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig"));
  return parts.map((part, index) =>
    part.toLowerCase() === clean.toLowerCase() ? <mark key={index}>{part}</mark> : <Fragment key={index}>{part}</Fragment>,
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="inspector-section" open>
      <summary><h3>{title}</h3></summary>
      <div className="inspector-section-body">{children}</div>
    </details>
  );
}

function downloadText(filename: string, content: string, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function Workspace() {
  const [version, setVersion] = useState<PolicyVersion>(1);
  const [nodesData, setNodesData] = useState(() => buildWorkflow(1));
  const [selectedId, setSelectedId] = useState("compliance_evaluation");
  const [globalSearch, setGlobalSearch] = useState("");
  const [nodeSearch, setNodeSearch] = useState("");
  const [workflowBrief, setWorkflowBrief] = useState(DEFAULT_WORKFLOW_BRIEF);
  const [runningIds, setRunningIds] = useState<string[]>([]);
  const [updatePhase, setUpdatePhase] = useState<SourceUpdatePhase>("idle");
  const [lastMonitoringCheck, setLastMonitoringCheck] = useState(MONITORING_CHECK.baseline);
  const [runtime, setRuntime] = useState<"demo" | "live">("demo");
  const [runtimeChecking, setRuntimeChecking] = useState(true);
  const [notice, setNotice] = useState("Preparing local runtime check…");
  const [decisions, setDecisions] = useState(initialDecisions);
  const [editingAction, setEditingAction] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [audit, setAudit] = useState<AuditEvent[]>(baseAudit);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [caseRecord, setCaseRecord] = useState<RemediationCase | null>(null);
  const [correction, setCorrection] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null);
  const [bottomTab, setBottomTab] = useState<"findings" | "actions" | "artifacts" | "audit">("findings");
  const [flow, setFlow] = useState<ReactFlowInstance<AgentFlowNode, Edge> | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);
  const demoTimers = useRef<number[]>([]);
  const liveRequests = useRef<AbortController[]>([]);

  const addAudit = useCallback((type: string, detail: string, actor = "Human operator") => {
    const event = createAuditEvent({ id: crypto.randomUUID(), time: new Date().toLocaleTimeString("en-US", { hour12: false }), type, detail, actor });
    setAudit((current) => [event, ...current]);
    return event;
  }, []);

  const probeCodex = useCallback(async () => {
    setRuntimeChecking(true);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 3500);
    try {
      const response = await fetch("/api/codex/health", { cache: "no-store", signal: controller.signal });
      const health = await response.json() as { ok?: boolean; tools?: string[] };
      if (!response.ok || !health.ok || !health.tools?.includes("codex")) throw new Error("Codex preflight failed");
      setRuntime("live");
      setNotice("Live Codex connected. Deterministic fixtures remain ready as fallback.");
      addAudit("runtime-mode.changed", "Demo Mode -> Live Codex", "Runtime preflight");
    } catch {
      setRuntime("demo");
      setNotice("Codex is unavailable; continuing safely in Demo Mode.");
    } finally {
      window.clearTimeout(timer);
      setRuntimeChecking(false);
    }
  }, [addAudit]);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      const saved = localStorage.getItem("nodewitness.demo");
      if (saved) {
        try {
          const state = JSON.parse(saved) as {
            version: PolicyVersion;
            nodesData: WorkflowNode[];
            decisions: Record<string, Partial<Decision>>;
            audit: AuditEvent[];
            artifacts: Artifact[];
            caseRecord: RemediationCase | string | null;
          };
          setVersion(state.version);
          setNodesData(state.nodesData);
          setUpdatePhase(state.version === 2 ? "complete" : "idle");
          setLastMonitoringCheck(state.version === 2 ? MONITORING_CHECK.revision : MONITORING_CHECK.baseline);
          setDecisions(Object.fromEntries(ACTION_PROPOSALS.map((action) => {
            const savedDecision = state.decisions?.[action.id];
            const status = savedDecision?.edited && savedDecision.status === "pending" ? "edited" : savedDecision?.status ?? "pending";
            return [action.id, { original: action.summary, ...savedDecision, status }];
          })) as Record<string, Decision>);
          setAudit(state.audit);
          setArtifacts(state.artifacts);
          setCaseRecord(state.caseRecord && typeof state.caseRecord === "object" ? state.caseRecord : null);
        } catch {
          localStorage.removeItem("nodewitness.demo");
        }
      }
      setHydrated(true);
    });

    return () => {
      active = false;
      demoTimers.current.forEach(window.clearTimeout);
      liveRequests.current.forEach((controller) => controller.abort());
    };
  }, [addAudit]);

  useEffect(() => {
    if (hydrated) queueMicrotask(() => void probeCodex());
  }, [hydrated, probeCodex]);

  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem("nodewitness.demo", JSON.stringify({ version, nodesData, decisions, audit, artifacts, caseRecord }));
  }, [version, nodesData, decisions, audit, artifacts, caseRecord, hydrated]);

  useEffect(() => {
    const transition = nextSourceUpdatePhase(updatePhase);
    if (!transition) return;

    const timer = window.setTimeout(() => {
      const next = transition.next;
      if (next === "queued") {
        const delta = diffPolicy(1, 2);
        setSelectedId("version_diff");
        setNotice(`${SOURCE_UPDATE_NODES.length} affected nodes queued. Unaffected checks remain unchanged.`);
        addAudit("rule.diffed", `${delta.thresholdChange}; ${delta.scopeChange}; IPS v2 p.${delta.page}`, "Version diff");
        addAudit("impact.calculated", `${SOURCE_UPDATE_NODES.length} affected nodes; concentration and liquidity excluded`, "Runtime");
        addAudit("nodes.queued", SOURCE_UPDATE_NODES.join(", "), "Runtime");
      }
      if (next === "running") {
        setRunningIds(SOURCE_UPDATE_NODES);
        setNotice("Affected crypto nodes are running. Unaffected run IDs and statuses are locked.");
        addAudit("nodes.running", SOURCE_UPDATE_NODES.join(", "), "Runtime");
      }
      if (next === "complete") {
        setNodesData((current) => applyAffectedWorkflow(current, 2, SOURCE_UPDATE_NODES));
        setVersion(2);
        setRunningIds([]);
        setNotice("Incremental re-evaluation complete in Demo Mode. Review Required; 5 proposals are ready.");
        addAudit("rule.extracted", POLICIES[2].rule, "Policy extraction");
        addAudit("compliance.conclusion", "Review Required: 8.2% total vs 5.0% maximum", "Compliance evaluation");
        addAudit("recommendation.created", "Primary remediation case proposal plus 4 parallel recommendations created", "Recommendation generation");
        addAudit("rerun.completed", "Affected crypto branch completed; unaffected run IDs and statuses preserved", "Runtime");
      }
      setUpdatePhase(next);
    }, transition.delayMs);

    return () => window.clearTimeout(timer);
  }, [addAudit, updatePhase]);

  const selectedNode = nodesData.find((node) => node.id === selectedId) ?? nodesData[0];
  const selectedStatus: NodeStatus = updatePhase === "queued" && SOURCE_UPDATE_NODES.includes(selectedNode.id)
    ? "queued"
    : runningIds.includes(selectedNode.id) ? "running" : selectedNode.data.status;
  const matches = useMemo(() => searchWorkflowNodes(nodesData, globalSearch), [globalSearch, nodesData]);
  const matchingIds = useMemo(() => new Set(matches.map((node) => node.id)), [matches]);

  const graphNodes: AgentFlowNode[] = useMemo(
    () =>
      nodesData.map((node) => ({
        id: node.id,
        type: "agent",
        position: node.position,
        data: {
          ...node.data,
          status: updatePhase === "queued" && SOURCE_UPDATE_NODES.includes(node.id)
            ? "queued"
            : runningIds.includes(node.id) ? "running" : node.data.status,
        },
        className: matchingIds.has(node.id) ? "node-search-match" : "",
      })),
    [nodesData, runningIds, matchingIds, updatePhase],
  );

  const graphEdges: Edge[] = useMemo(
    () =>
      GRAPH_EDGES.map((edge) => {
        const affected = runningIds.includes(edge.source) && runningIds.includes(edge.target);
        return {
          ...edge,
          animated: affected,
          className: affected ? "edge-affected" : "",
          style: { stroke: affected ? "#26d9e8" : "#2a4354", strokeWidth: affected ? 2.2 : 1.4 },
        };
      }),
    [runningIds],
  );

  const focusNode = (node: WorkflowNode) => {
    setSelectedId(node.id);
    setNodeSearch("");
    flow?.setCenter(node.position.x + 110, node.position.y + 75, { zoom: 0.86, duration: 600 });
  };

  const activateV2 = (source = "Bundled IPS v2") => {
    if (version === 2 || updatePhase !== "idle") {
      setNotice(version === 2 ? "IPS v2 is already active." : "The IPS v2 update is already in progress.");
      return;
    }
    setUpdatePhase("detected");
    setLastMonitoringCheck(MONITORING_CHECK.revision);
    setSelectedId("version_diff");
    setBottomTab("findings");
    setNotice("Source change detected. IPS v2 was added beside v1; impact analysis is starting.");
    addAudit("monitoring.checked", `Monitoring check completed at ${MONITORING_CHECK.revision}`, "Source monitor");
    addAudit("source.uploaded", `${source} accepted for the bundled parser`, "Compliance operator");
    addAudit("source.version.changed", "IPS v1 -> IPS v2; emitted internal source.version.changed", "Source monitor");
    addAudit("source.version.added", "IPS v2 retained alongside immutable IPS v1", "Source versioning");
  };

  const generateAgent = async () => {
    const ids = nodesData.map((node) => node.id).filter((id) => !id.includes("memo") && !id.includes("notification") && id !== "remediation_case");
    setRunningIds(ids);
    setNotice(runtime === "live" ? "Codex is validating the normalized workflow…" : "Generating from deterministic fixtures…");
    addAudit("node.started", `Generate Agent requested in ${runtime === "live" ? "Live Codex" : "Demo Mode"}`, "Compliance operator");
    if (runtime === "live") {
      const controller = new AbortController();
      liveRequests.current.push(controller);
      const timeout = window.setTimeout(() => controller.abort(), LIVE_REQUEST_TIMEOUT_MS);
      try {
        const response = await fetch("/api/codex/analyze", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ operation: "workflow", version, description: workflowBrief }),
          signal: controller.signal,
        });
        const result = await response.json() as NormalizedRuntimeResult & { ok?: boolean; threadId?: string; workflow?: WorkflowNode[] };
        if (!response.ok || !result.ok || !isNormalizedRuntimeResult(result, "workflow") || !Array.isArray(result.workflow)) throw new Error("Invalid live response");
        setNodesData(result.workflow);
        setNotice("Live Codex converted the instruction into the validated NodeWitness graph schema.");
        addAudit("runtime.workflow.generated", `Live Codex · ${result.threadId ?? "thread unavailable"}`, "Codex MCP");
      } catch {
        setRuntime("demo");
        setNotice("Live validation paused; current state was retained in Demo Mode.");
        addAudit("runtime-mode.changed", "Live Codex -> Demo Mode after bounded request failure", "Runtime fallback");
      } finally {
        window.clearTimeout(timeout);
      }
    }
    demoTimers.current.push(window.setTimeout(() => {
      setRunningIds([]);
      addAudit("node.completed", `Workspace graph generated for IPS v${version}`, "Runtime");
    }, 1000));
  };

  const decide = (id: string, status: "approved" | "rejected") => {
    const action = ACTION_PROPOSALS.find((item) => item.id === id)!;
    const approvedDescription = decisions[id]?.edited ?? decisions[id]?.original ?? action.summary;
    setDecisions((current) => ({ ...current, [id]: { ...current[id], status } }));
    const decisionEvent = addAudit(status === "approved" ? "proposal.approved" : "proposal.rejected", `${action.title}${status === "approved" ? ` · ${approvedDescription}` : ""}`, "Compliance operator");
    if (status === "rejected") return;
    if (!canExecuteLocalAction(id, status)) {
      addAudit("execution.skipped", `${action.title}: decision recorded; no local executable side effect is permitted`, "Governance gate");
      return;
    }

    if (id === "case") {
      const creationEvent = addAudit("artifact.created", "Local remediation case NW-2026-0718", "Safe local executor");
      setCaseRecord({
        id: "NW-2026-0718",
        title: "Aurora cryptocurrency exposure remediation",
        severity: "High",
        status: "Open",
        client: "Aurora Family Office",
        sourceVersions: "IPS v1 → IPS v2 (both retained)",
        violatedRule: POLICIES[2].rule,
        observedExposure: "8.2% total cryptocurrency exposure",
        threshold: "5.0% maximum",
        evidence: "IPS v2 page 2; portfolio snapshot page 3",
        approvedDescription,
        owner: "Unassigned — compliance owner required",
        dueDateSuggestion: "21 July 2026",
        auditReferences: [`${creationEvent.id} · ${creationEvent.type}`, `${decisionEvent.id} · ${decisionEvent.type}`, ...audit.map((event) => `${event.id} · ${event.type}`)],
      });
      setNodesData((current) => current.map((node) => node.id === "remediation_case" ? { ...node, data: { ...node.data, status: "ready", outputs: ["Case NW-2026-0718 created locally"] } } : node));
    }
    if (id === "memo") {
      const content = `# Aurora Family Office - Compliance Memo\n\n**Date:** 18 July 2026  \n**Run:** run-aurora-002-compliance_evaluation  \n**Approval audit reference:** ${decisionEvent.id}\n\n## Conclusion\nReview Required. Total cryptocurrency exposure is 8.2%, exceeding the IPS v2 maximum of 5.0% by 3.2 percentage points.\n\n## Approved recommendation\n${approvedDescription}\n\n## Evidence\n- IPS v2, page 2: total exposure includes direct and look-through holdings.\n- Direct exposure: 2.0%\n- Look-through exposure: 6.2%\n- Total exposure: 8.2%\n\n## Human control\nThis memo was generated only after proposal-specific approval in NodeWitness. No trade was placed and no external system was changed.\n`;
      setArtifacts((current) => [...current.filter((item) => item.id !== "memo"), { id: "memo", title: "Compliance memo", filename: "aurora-compliance-memo.md", content }]);
      setNodesData((current) => current.map((node) => node.id === "compliance_memo" ? { ...node, data: { ...node.data, status: "ready", outputs: ["aurora-compliance-memo.md"] } } : node));
      addAudit("artifact.created", "aurora-compliance-memo.md", "Safe local executor");
    }
    if (id === "notification") {
      const content = `# Adviser notification draft\n\nSubject: Aurora Family Office - cryptocurrency exposure review required\n\nThe revised Investment Policy Statement sets a 5.0% maximum for total cryptocurrency exposure, including look-through holdings. Current measured exposure is 8.2%. Please review the attached evidence and proposed remediation case.\n\nApproved drafting instruction: ${approvedDescription}\n\nThis is a draft only. NodeWitness did not send an email.\nApproval audit reference: ${decisionEvent.id}\n`;
      setArtifacts((current) => [...current.filter((item) => item.id !== "notification"), { id: "notification", title: "Adviser notification draft", filename: "aurora-adviser-notification.md", content }]);
      setNodesData((current) => current.map((node) => node.id === "adviser_notification" ? { ...node, data: { ...node.data, status: "ready", outputs: ["aurora-adviser-notification.md"] } } : node));
      addAudit("artifact.created", "aurora-adviser-notification.md (draft only)", "Safe local executor");
    }
  };

  const startEdit = (id: string) => {
    const action = ACTION_PROPOSALS.find((item) => item.id === id)!;
    setEditingAction(id);
    setEditDraft(decisions[id]?.edited ?? action.summary);
  };

  const saveEdit = (id: string) => {
    const value = editDraft.trim();
    if (!value) return;
    setDecisions((current) => ({ ...current, [id]: { ...current[id], status: "edited", edited: value } }));
    setEditingAction(null);
    addAudit("proposal.edited", `${ACTION_PROPOSALS.find((item) => item.id === id)!.title}: original retained; edited text stored`, "Compliance operator");
    setNotice("Recommendation edited. The original is preserved and the revised item can now be approved.");
  };

  const submitCorrection = () => {
    const value = correction.trim();
    if (!value) return;
    const downstream = downstreamNodes(selectedNode.id);
    const originalOutput = selectedNode.data.outputs.join(" | ");
    const revisedOutput = `Revised output: ${value}`;
    if (runtime === "live") {
      const controller = new AbortController();
      liveRequests.current.push(controller);
      const timeout = window.setTimeout(() => controller.abort(), LIVE_REQUEST_TIMEOUT_MS);
      fetch("/api/codex/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ operation: "correction", version, nodeId: selectedNode.id, originalOutputs: selectedNode.data.outputs, instruction: value }),
        signal: controller.signal,
      })
        .then(async (response) => {
          const result = await response.json() as NormalizedRuntimeResult & { ok?: boolean; threadId?: string };
          if (!response.ok || !result.ok || !isNormalizedRuntimeResult(result, "correction") || result.output.nodeId !== selectedNode.id) throw new Error("Invalid live correction");
          setNodesData((current) => current.map((node) => node.id === selectedNode.id ? { ...node, data: { ...node.data, outputs: node.data.outputs.map((output) => output === revisedOutput ? result.output.revisedOutput! : output), runtimeMode: "Live Codex MCP", threadId: result.threadId ?? null } } : node));
          addAudit("runtime.correction.validated", `Live Codex · ${result.threadId ?? "thread unavailable"}`, "Codex MCP");
        })
        .catch(() => {
          setRuntime("demo");
          setNotice("Live correction validation was unavailable; the deterministic revision was retained.");
          addAudit("runtime-mode.changed", "Live Codex -> Demo Mode; deterministic correction retained", "Runtime fallback");
        })
        .finally(() => window.clearTimeout(timeout));
    }
    setRunningIds(downstream);
    setNodesData((current) => current.map((node) => node.id === selectedNode.id ? {
      ...node,
      data: {
        ...node.data,
        status: "modified",
        humanModified: true,
        outputs: [...node.data.outputs, revisedOutput],
        decisionBasis: `${node.data.decisionBasis} Human correction recorded: ${value}`,
        history: [`Human correction - ${new Date().toLocaleTimeString("en-US", { hour12: false })}`, ...node.data.history],
      },
    } : node));
    setNotice(`Human correction recorded. Re-running ${downstream.length} downstream nodes only.`);
    addAudit("correction.submitted", selectedNode.data.label, "Compliance operator");
    addAudit("node.output.preserved", `${selectedNode.id}: ${originalOutput}`, "Governance gate");
    addAudit("human.instruction.recorded", `${selectedNode.id}: ${value}`, "Compliance operator");
    addAudit("downstream.identified", downstream.join(", ") || "No downstream nodes", "Runtime");
    addAudit("nodes.running", downstream.join(", ") || "No downstream nodes", "Runtime");
    setCorrection("");
    demoTimers.current.push(window.setTimeout(() => {
      setRunningIds([]);
      setNodesData((current) => current.map((node) => downstream.includes(node.id) ? { ...node, data: { ...node.data, history: [`Re-run after human correction to ${selectedNode.id}`, ...node.data.history] } } : node));
      addAudit("revised.output.created", `${selectedNode.id}: ${revisedOutput}`, "Runtime");
      addAudit("rerun.completed", `Only ${downstream.length} downstream nodes re-ran from ${selectedNode.id}`, "Runtime");
      setNotice("Human-governed downstream re-run complete. Revised output is ready for review.");
    }, 1200));
  };

  const resetDemo = () => {
    demoTimers.current.forEach(window.clearTimeout);
    demoTimers.current = [];
    liveRequests.current.forEach((controller) => controller.abort());
    liveRequests.current = [];
    localStorage.removeItem("nodewitness.demo");
    setVersion(1);
    setNodesData(buildWorkflow(1));
    setSelectedId("compliance_evaluation");
    setDecisions(initialDecisions());
    setAudit(baseAudit);
    setArtifacts([]);
    setCaseRecord(null);
    setRunningIds([]);
    setUpdatePhase("idle");
    setLastMonitoringCheck(MONITORING_CHECK.baseline);
    setGlobalSearch("");
    setNodeSearch("");
    setWorkflowBrief(DEFAULT_WORKFLOW_BRIEF);
    setCorrection("");
    setEvidenceUrl(null);
    setEditingAction(null);
    setEditDraft("");
    setBottomTab("findings");
    if (uploadRef.current) uploadRef.current.value = "";
    setNotice("Demo reset to the IPS v1 passing baseline.");
    flow?.fitView({ padding: 0.12, duration: 500 });
  };

  const showRevision = version === 2 || updatePhase !== "idle";
  const updateProgress = UPDATE_PROGRESS[updatePhase];
  const updateBusy = updatePhase === "detected" || updatePhase === "queued" || updatePhase === "running";
  const updateLocked = updateBusy || version === 2;
  const graphRunLabel = updatePhase === "idle"
    ? "baseline"
    : updatePhase === "complete" ? "revision_run_002" : `revision_${updatePhase}`;
  const toggleRuntime = () => {
    if (runtime === "live") {
      setRuntime("demo");
      setRuntimeChecking(false);
      setNotice("Demo Mode selected manually. All deterministic features remain available.");
      addAudit("runtime-mode.changed", "Live Codex -> Demo Mode by presenter", "Compliance operator");
    } else {
      void probeCodex();
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true"><span /></div>
          <div><strong>NodeWitness</strong><small className="brand-tagline">Build AI agents anyone can understand, review, and control.</small><Link className="brand-tagline" href="/environments">Agent environments →</Link></div>
        </div>
        <div className="workspace-title"><small>DEMO WORKSPACE</small><strong>Aurora Family Office — Client Mandate Compliance</strong></div>
        <div className="top-actions">
          <span className={`runtime-badge ${runtime}`} role="status"><i />{runtimeChecking ? "Checking runtime" : runtime === "live" ? "Live Codex" : "Demo Mode"}</span>
          <button className="runtime-toggle" disabled={runtimeChecking} onClick={toggleRuntime}>{runtime === "live" ? "Use Demo" : "Retry Live"}</button>
          <span className="monitor-badge" role="status"><i />Monitoring Active</span>
          <button className="quiet-button" onClick={resetDemo}>Reset Demo</button>
          <button className="quiet-button" onClick={() => downloadText("nodewitness-audit.json", JSON.stringify(audit, null, 2), "application/json")}>Export Audit</button>
        </div>
      </header>

      <div className="runtime-notice" role="status" aria-live="polite"><span>{notice}</span><button onClick={() => setNotice("")} aria-label="Dismiss notification">×</button></div>

      <div className="workbench">
        <aside className="left-panel panel-scroll">
          <div className="panel-heading"><span>01</span><div><small>WORKFLOW BRIEF</small><h2>Describe the mandate</h2></div></div>
          <label className="field-label" htmlFor="workflow-brief">Natural-language instruction</label>
          <textarea id="workflow-brief" className="workflow-brief" value={workflowBrief} onChange={(event) => setWorkflowBrief(event.target.value)} />
          <button className="primary-button" disabled={updateBusy} onClick={generateAgent}><span>{updateBusy ? "Incremental run in progress…" : "Generate agent"}</span><kbd>⌘ ↵</kbd></button>

          <div className="section-rule"><span>SOURCES</span><em>{showRevision ? "2 versions retained" : "1 active · update ready"}</em></div>
          <article className={`source-card ${version === 1 ? "active" : ""}`}>
            <div className="source-icon">PDF</div>
            <div><strong>Aurora IPS</strong><small>aurora-ips-v1.pdf · 3 pages</small><span className="source-state">{version === 1 ? "ACTIVE SOURCE" : "SUPERSEDED"}</span></div>
            <a href="/demo/aurora-ips-v1.pdf#page=2" target="_blank" rel="noreferrer" aria-label="Open Aurora IPS v1 page 2">↗</a>
          </article>
          {showRevision && (
            <article className={`source-card ${version === 2 ? "active" : ""}`}>
              <div className="source-icon">PDF</div>
              <div><strong>Aurora IPS revision</strong><small>aurora-ips-v2.pdf · 3 pages</small><span className="source-state">{version === 2 ? "ACTIVE SOURCE" : "VERSION ADDED"}</span></div>
              <a href="/demo/aurora-ips-v2.pdf#page=2" target="_blank" rel="noreferrer" aria-label="Open Aurora IPS v2 page 2">↗</a>
            </article>
          )}

          <div className="version-block">
            {showRevision && <div className="version-row"><span>v2</span><div><strong>18 Jul 2026</strong><small>5% · total look-through scope</small></div><i className={version === 2 ? "active" : "pending"} /></div>}
            <div className="version-row"><span>v1</span><div><strong>14 Jul 2026</strong><small>10% · direct-only scope</small></div><i className={version === 1 ? "active" : ""} /></div>
          </div>

          <div className={`monitoring-state phase-${updatePhase}`} role="status" aria-live="polite">
            <div className="monitoring-status"><i /><span><strong>{updatePhase === "idle" ? "NO CHANGE DETECTED" : "CHANGE DETECTED"}</strong><small>{updateProgress.label}</small></span></div>
            <div className="monitoring-check"><span>Last monitoring check</span><time>{lastMonitoringCheck}</time></div>
            <label htmlFor="rerun-progress">Re-run progress <b>{updateProgress.value}%</b></label>
            <progress id="rerun-progress" max="100" value={updateProgress.value}>{updateProgress.value}%</progress>
          </div>

          <input ref={uploadRef} className="sr-only" type="file" accept="application/pdf" onChange={(event) => { const file = event.target.files?.[0]; if (file) activateV2(file.name); event.currentTarget.value = ""; }} />
          <div className="source-buttons">
            <button disabled={updateLocked} onClick={() => activateV2()}>{version === 2 ? "IPS v2 active" : updatePhase !== "idle" ? "Update in progress…" : "Trigger IPS v2 event"}</button>
            <button disabled={updateLocked} onClick={() => uploadRef.current?.click()}>Upload bundled-format PDF</button>
          </div>
          {showRevision && (
            <div className="change-summary">
              <small>SEMANTIC CHANGE DETECTED</small>
              <strong>10% <span>→</span> 5%</strong>
              <p><mark>Direct-only</mark> <span>→</span> <mark>total look-through exposure</mark></p>
              <div className="rule-comparison">
                <article><small>OLD · IPS v1 · PAGE 2</small><p>Direct cryptocurrency exposure may not exceed <mark>10%</mark> of portfolio market value.</p></article>
                <article><small>NEW · IPS v2 · PAGE 2</small><p>Total cryptocurrency exposure may not exceed <mark>5%</mark>. Total exposure includes direct holdings and <mark>look-through exposure</mark> through funds, ETFs, and derivatives.</p></article>
              </div>
              <a href="/demo/aurora-ips-v2.pdf#page=2" target="_blank" rel="noreferrer">Open exact evidence · IPS v2 page 2 ↗</a>
            </div>
          )}
        </aside>

        <section className="graph-panel">
          <div className="graph-toolbar">
            <div className="search-wrap">
              <span aria-hidden="true">⌕</span>
              <input value={globalSearch} onChange={(event) => setGlobalSearch(event.target.value)} placeholder="Search graph, rules, evidence…" aria-label="Global graph search" />
              {globalSearch && <b>{matches.length} result{matches.length === 1 ? "" : "s"}</b>}
            </div>
            <div className="graph-legend">
              <span><i className="pass" />Pass</span><span><i className="attention" />Attention</span><span><i className="review" />Review required</span><span><i className="modified" />Human modified</span>
            </div>
          </div>
          {globalSearch && (
            <div className="search-results">
              {matches.length ? matches.map((node) => <button key={node.id} onClick={() => focusNode(node)}><small>{node.data.kind}</small><strong>{node.data.label}</strong><span>{node.id}</span></button>) : <p>No matching nodes. Try “crypto”, “look-through”, or “liquidity”.</p>}
            </div>
          )}
          <div className="graph-canvas">
            <div className="graph-context"><span>AGENT GRAPH</span><strong>mandate_monitor / {graphRunLabel}</strong></div>
            <ReactFlow<AgentFlowNode, Edge>
              nodes={graphNodes}
              edges={graphEdges}
              nodeTypes={nodeTypes}
              onInit={setFlow}
              onNodeClick={(_, node) => { setSelectedId(node.id); setNodeSearch(""); }}
              nodesDraggable={false}
              fitView
              fitViewOptions={{ padding: 0.12 }}
              minZoom={0.25}
              maxZoom={1.6}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#173244" gap={22} size={1} />
              <Controls position="bottom-left" showInteractive={false} />
              <MiniMap position="bottom-right" pannable zoomable nodeColor={(node) => node.data.status === "review" ? "#ff6b6b" : node.data.status === "attention" ? "#f5b942" : "#26d9e8"} maskColor="rgba(5, 14, 22, .82)" />
            </ReactFlow>
          </div>
        </section>

        <aside className="right-panel panel-scroll">
          <div className="inspector-topline"><span>NODE INSPECTOR</span><code>{selectedNode.id}</code></div>
          <div className="inspector-title"><div className={`inspector-icon status-${selectedStatus}`}>{selectedNode.data.kind.slice(0, 2)}</div><div><h2>{selectedNode.data.label}</h2><span className={`status-pill ${selectedStatus}`}>{statusLabel(selectedStatus)}</span></div></div>
          <p className="inspector-summary">{selectedNode.data.description}</p>
          <div className="node-search"><span>⌕</span><input value={nodeSearch} onChange={(event) => setNodeSearch(event.target.value)} placeholder="Search this node…" aria-label="Search selected node" /></div>

          <Section title="Decision Basis"><p className="decision-basis"><Highlight text={selectedNode.data.decisionBasis} query={nodeSearch} /></p></Section>
          <Section title="Inputs">{selectedNode.data.inputs.map((item) => <div className="value-row" key={item}><i>IN</i><span><Highlight text={item} query={nodeSearch} /></span></div>)}</Section>
          <Section title="Outputs">{selectedNode.data.outputs.map((item) => <div className="value-row" key={item}><i>OUT</i><span><Highlight text={item} query={nodeSearch} /></span></div>)}</Section>
          <Section title="Evidence citations">
            {selectedNode.data.evidence.map((item) => (
              <a className="evidence-card" href={item.href} target="_blank" rel="noreferrer" key={`${item.label}-${item.page}`}>
                <span><b>{item.sourceVersion}</b> · page {item.page}</span>
                <p><Highlight text={item.excerpt} query={nodeSearch} /></p>
                <em>Open cited page ↗</em>
              </a>
            ))}
          </Section>
          <Section title="Technical trace">
            <dl className="trace-grid">
              <div><dt>Source</dt><dd><Highlight text={selectedNode.data.sourceVersion} query={nodeSearch} /></dd></div><div><dt>Run ID</dt><dd><Highlight text={selectedNode.data.runId} query={nodeSearch} /></dd></div>
              <div><dt>Prompt</dt><dd><Highlight text={selectedNode.data.promptVersion} query={nodeSearch} /></dd></div><div><dt>Schema</dt><dd><Highlight text={selectedNode.data.schemaVersion} query={nodeSearch} /></dd></div>
              <div><dt>Runtime</dt><dd><Highlight text={selectedNode.data.runtimeMode} query={nodeSearch} /></dd></div><div><dt>Duration</dt><dd><Highlight text={selectedNode.data.duration} query={nodeSearch} /></dd></div>
              <div><dt>Timestamp</dt><dd><Highlight text={selectedNode.data.timestamp} query={nodeSearch} /></dd></div><div><dt>Thread ID</dt><dd><Highlight text={selectedNode.data.threadId ?? "Not available in Demo Mode"} query={nodeSearch} /></dd></div>
            </dl>
          </Section>
          <Section title="Run history">{selectedNode.data.history.map((item) => <div className="history-row" key={item}><i /><span>{item}</span></div>)}</Section>
          <Section title="Suggest a correction">
            <p className="correction-help">The original remains immutable. Only downstream nodes will re-run.</p>
            <textarea value={correction} onChange={(event) => setCorrection(event.target.value)} placeholder="Add a concise, reviewable correction…" />
            <button className="correction-button" disabled={!correction.trim()} onClick={submitCorrection}>Record correction & re-run downstream</button>
          </Section>
        </aside>
      </div>

      <section className="decision-drawer">
        <div className="drawer-nav">
          <div className="drawer-title"><span>03</span><div><small>CONTROL ROOM</small><strong>{version === 1 ? "No mandate breach" : "Review required"}</strong></div></div>
          <nav aria-label="Control room sections" role="tablist">
            {(["findings", "actions", "artifacts", "audit"] as const).map((tab) => <button id={`drawer-tab-${tab}`} role="tab" aria-selected={bottomTab === tab} aria-controls="drawer-panel" className={bottomTab === tab ? "active" : ""} onClick={() => setBottomTab(tab)} key={tab}>{tab}<b>{tab === "actions" ? (version === 2 ? 5 : 0) : tab === "artifacts" ? artifacts.length + (caseRecord ? 1 : 0) : tab === "audit" ? audit.length : version === 2 ? 2 : 1}</b></button>)}
          </nav>
        </div>

        <div id="drawer-panel" role="tabpanel" aria-labelledby={`drawer-tab-${bottomTab}`} tabIndex={0} className="drawer-content">
          {bottomTab === "findings" && (
            <div className="findings-layout">
              <article className={`hero-finding ${version === 1 ? "pass" : "review"}`}>
                <div className="finding-status"><i />{version === 1 ? "PASS" : "REVIEW REQUIRED"}</div>
                <h3>{version === 1 ? "Direct crypto exposure is within mandate" : "Total crypto exposure exceeds the revised mandate"}</h3>
                <div className="metric-line"><strong>{version === 1 ? "2.0%" : "8.2%"}</strong><span>{version === 1 ? "of 10.0% maximum" : "of 5.0% maximum"}</span><em>{version === 1 ? "8.0 pts headroom" : "+3.2 pts excess"}</em></div>
                <button onClick={() => focusNode(nodesData.find((node) => node.id === "compliance_evaluation")!)}>Open decision node →</button>
              </article>
              <article className="secondary-finding"><span>NEAR-LIMIT ATTENTION</span><h3>Issuer concentration</h3><div><strong>18.7%</strong><small>20.0% maximum · 1.3 pts headroom</small></div><button onClick={() => focusNode(nodesData.find((node) => node.id === "concentration_check")!)}>Inspect check →</button></article>
              <article className="secondary-finding pass"><span>PARALLEL CHECK</span><h3>Liquidity minimum</h3><div><strong>6.4%</strong><small>5.0% minimum · 1.4 pts headroom</small></div><button onClick={() => focusNode(nodesData.find((node) => node.id === "liquidity_check")!)}>Inspect check →</button></article>
              {version === 2 && <button className="review-actions-cta" onClick={() => setBottomTab("actions")}><small>5 proposals awaiting decision</small><strong>Review actions</strong><span>→</span></button>}
            </div>
          )}

          {bottomTab === "actions" && (
            <div className="action-list">
              {version === 1 ? <div className="empty-state"><strong>No actions proposed</strong><span>The active IPS v1 crypto rule passes.</span></div> : ACTION_PROPOSALS.map((action, index) => {
                const decision = decisions[action.id] ?? { status: "pending", original: action.summary };
                const finalDecision = decision.status === "approved" || decision.status === "rejected";
                return (
                  <article className={`action-card ${action.id === "case" ? "primary" : "parallel"} ${decision.status}`} key={action.id}>
                    <div className="action-index">0{index + 1}</div>
                    <div className="action-copy"><small>{action.eyebrow}</small><h3>{action.title}</h3>{decision.edited ? <div className="edited-copy"><p><b>Original</b>{decision.original}</p><p><b>Edited</b>{decision.edited}</p></div> : <p>{decision.original}</p>}<span>{action.evidence}</span></div>
                    {editingAction === action.id ? <div className="action-editor"><textarea aria-label={`Edit ${action.title}`} value={editDraft} onChange={(event) => setEditDraft(event.target.value)} /><button disabled={!editDraft.trim()} onClick={() => saveEdit(action.id)}>Save revision</button><button onClick={() => setEditingAction(null)}>Cancel</button></div> : (
                      <div className="action-controls">
                        <div className={`decision-state ${decision.status}`}>{decision.status}</div>
                        <button disabled={finalDecision} onClick={() => decide(action.id, "approved")}>Approve</button><button disabled={finalDecision} onClick={() => decide(action.id, "rejected")}>Reject</button><button disabled={finalDecision} onClick={() => startEdit(action.id)}>Edit</button><button onClick={() => setEvidenceUrl(action.id === "concentration" || action.id === "validation" ? "/demo/aurora-ips-v2.pdf#page=3" : "/demo/aurora-ips-v2.pdf#page=2")}>View Evidence</button>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}

          {bottomTab === "artifacts" && (
            <div className="artifact-grid">
              {caseRecord && <article className="case-record"><small>LOCAL REMEDIATION CASE</small><h3>{caseRecord.id} · {caseRecord.title}</h3><dl><div><dt>Severity</dt><dd>{caseRecord.severity}</dd></div><div><dt>Status</dt><dd>{caseRecord.status}</dd></div><div><dt>Client</dt><dd>{caseRecord.client}</dd></div><div><dt>Source versions</dt><dd>{caseRecord.sourceVersions}</dd></div><div><dt>Violated rule</dt><dd>{caseRecord.violatedRule}</dd></div><div><dt>Observed exposure</dt><dd>{caseRecord.observedExposure}</dd></div><div><dt>Threshold</dt><dd>{caseRecord.threshold}</dd></div><div><dt>Evidence</dt><dd>{caseRecord.evidence} · <a href="/demo/aurora-ips-v2.pdf#page=2" target="_blank" rel="noreferrer">Open source ↗</a></dd></div><div><dt>Approved description</dt><dd>{caseRecord.approvedDescription}</dd></div><div><dt>Owner</dt><dd>{caseRecord.owner}</dd></div><div><dt>Due-date suggestion</dt><dd>{caseRecord.dueDateSuggestion}</dd></div></dl><details><summary>Complete audit references · {caseRecord.auditReferences.length}</summary><ul>{caseRecord.auditReferences.map((reference) => <li key={reference}>{reference}</li>)}</ul></details><span>Safe local record · no ticketing system called</span></article>}
              {artifacts.map((artifact) => <article className="artifact-card" key={artifact.id}><div>MD</div><small>GENERATED ARTIFACT</small><h3>{artifact.title}</h3><p>{artifact.filename}</p><button onClick={() => downloadText(artifact.filename, artifact.content)}>Download Markdown ↓</button></article>)}
              {!caseRecord && !artifacts.length && <div className="empty-state"><strong>No generated artifacts</strong><span>Approve proposals individually to execute safe local operations.</span></div>}
            </div>
          )}

          {bottomTab === "audit" && (
            <div className="audit-list">
              {audit.map((event) => <article key={event.id}><time>{event.time}</time><i /><div><strong>{event.type}</strong><p>{event.detail}</p></div><span>{event.actor}</span></article>)}
            </div>
          )}
        </div>
      </section>

      {evidenceUrl && (
        <div className="evidence-modal" role="dialog" aria-modal="true" aria-label="Evidence viewer">
          <div className="evidence-modal-card">
            <header><div><small>PRIMARY EVIDENCE</small><strong>Aurora Family Office · Investment Policy Statement</strong></div><div><a href={evidenceUrl} target="_blank" rel="noreferrer">Open in new tab ↗</a><button onClick={() => setEvidenceUrl(null)} aria-label="Close evidence">×</button></div></header>
            <iframe src={evidenceUrl} title="Cited policy document" />
          </div>
        </div>
      )}
    </main>
  );
}

export default function NodeWitness() {
  return <ReactFlowProvider><Workspace /></ReactFlowProvider>;
}
