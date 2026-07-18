export type PolicyVersion = 1 | 2;
export type ComplianceConclusion = "Pass" | "Review Required";
export type NodeStatus =
  | "idle"
  | "queued"
  | "running"
  | "pass"
  | "attention"
  | "review"
  | "ready"
  | "modified";

export type Evidence = {
  label: string;
  excerpt: string;
  page: number;
  href: string;
  sourceVersion: string;
};

export type WorkflowNode = {
  id: string;
  position: { x: number; y: number };
  data: {
    label: string;
    kind: string;
    description: string;
    status: NodeStatus;
    inputs: string[];
    outputs: string[];
    evidence: Evidence[];
    sourceVersion: string;
    decisionBasis: string;
    promptVersion: string;
    schemaVersion: string;
    runtimeMode: string;
    timestamp: string;
    duration: string;
    runId: string;
    threadId: string | null;
    humanModified: boolean;
    history: string[];
  };
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
};

export type NormalizedAnalysis = {
  schemaVersion: "nodewitness.analysis@1";
  sourceVersion: "IPS v1" | "IPS v2";
  applicableExposure: number;
  threshold: number;
  conclusion: ComplianceConclusion;
  decisionBasis: string;
  evidence: { source: string; page: number; excerpt: string }[];
};

export type Recommendation = {
  id: string;
  title: string;
  eyebrow: string;
  summary: string;
  evidence: string;
};

export type RuntimeOperation = "workflow" | "assessment" | "correction";

export type RuntimeInput = {
  description?: string;
  nodeId?: string;
  originalOutputs?: string[];
  instruction?: string;
};

export type NormalizedRuntimeResult = {
  schemaVersion: "nodewitness.runtime@1";
  operation: RuntimeOperation;
  analysis: NormalizedAnalysis;
  recommendations: Recommendation[];
  metadata: {
    promptVersion: "nodewitness-runtime@1";
    sourceVersion: "IPS v1" | "IPS v2";
  };
  output: {
    workspace: string | null;
    workflowDescription: string | null;
    nodeIds: string[];
    nodeId: string | null;
    originalOutputs: string[];
    humanInstruction: string | null;
    revisedOutput: string | null;
    downstreamNodeIds: string[];
  };
};

export type GovernanceDecisionStatus = "pending" | "edited" | "approved" | "rejected";

const LOCAL_EXECUTION_ACTIONS = new Set(["case", "memo", "notification"]);

export function canExecuteLocalAction(actionId: string, status: GovernanceDecisionStatus) {
  return status === "approved" && LOCAL_EXECUTION_ACTIONS.has(actionId);
}

export type AuditEvent = {
  id: string;
  time: string;
  type: string;
  detail: string;
  actor: string;
};

export type SourceUpdatePhase = "idle" | "detected" | "queued" | "running" | "complete";

export const SOURCE_UPDATE_TRANSITIONS = {
  detected: { next: "queued", delayMs: 350 },
  queued: { next: "running", delayMs: 650 },
  running: { next: "complete", delayMs: 2200 },
} as const satisfies Partial<Record<SourceUpdatePhase, { next: SourceUpdatePhase; delayMs: number }>>;

export function nextSourceUpdatePhase(phase: SourceUpdatePhase) {
  return SOURCE_UPDATE_TRANSITIONS[phase as keyof typeof SOURCE_UPDATE_TRANSITIONS] ?? null;
}

export const POLICIES = {
  1: {
    version: "IPS v1",
    threshold: 10,
    scope: "Direct cryptocurrency exposure",
    rule: "Direct cryptocurrency exposure may not exceed 10% of portfolio market value.",
    href: "/demo/aurora-ips-v1.pdf",
    page: 2,
  },
  2: {
    version: "IPS v2",
    threshold: 5,
    scope: "Direct and look-through cryptocurrency exposure",
    rule: "Total cryptocurrency exposure may not exceed 5%. Total exposure includes direct holdings and look-through exposure through funds, ETFs, and derivatives.",
    href: "/demo/aurora-ips-v2.pdf",
    page: 2,
  },
} as const;

export const PORTFOLIO = {
  directCrypto: 2,
  indirectCrypto: 6.2,
  totalCrypto: 8.2,
  issuerExposure: 18.7,
  maxIssuerExposure: 20,
  liquidity: 6.4,
  minLiquidity: 5,
} as const;

export const AFFECTED_CRYPTO_NODES = [
  "ips_source",
  "source_versioning",
  "policy_extraction",
  "version_diff",
  "crypto_rule",
  "exposure_calculation",
  "compliance_evaluation",
  "recommendation_generation",
  "human_approval",
] as const;

export function evaluateCompliance(version: PolicyVersion): {
  exposure: number;
  threshold: number;
  result: ComplianceConclusion;
  variance: number;
} {
  const policy = POLICIES[version];
  const exposure = version === 1 ? PORTFOLIO.directCrypto : PORTFOLIO.totalCrypto;
  return {
    exposure,
    threshold: policy.threshold,
    result: exposure <= policy.threshold ? "Pass" : "Review Required",
    variance: Number((exposure - policy.threshold).toFixed(1)),
  };
}

export function fixtureAnalysis(version: PolicyVersion): NormalizedAnalysis {
  const policy = POLICIES[version];
  const evaluation = evaluateCompliance(version);
  return {
    schemaVersion: "nodewitness.analysis@1",
    sourceVersion: policy.version,
    applicableExposure: evaluation.exposure,
    threshold: evaluation.threshold,
    conclusion: evaluation.result,
    decisionBasis: evaluation.result === "Pass"
      ? "Direct cryptocurrency exposure is below the IPS v1 maximum."
      : "Total cryptocurrency exposure exceeds the IPS v2 maximum.",
    evidence: [{ source: `Aurora ${policy.version}`, page: policy.page, excerpt: policy.rule }],
  };
}

export function isNormalizedAnalysis(value: unknown): value is NormalizedAnalysis {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  if (
    item.schemaVersion !== "nodewitness.analysis@1" ||
    !["IPS v1", "IPS v2"].includes(String(item.sourceVersion)) ||
    typeof item.applicableExposure !== "number" ||
    typeof item.threshold !== "number" ||
    !["Pass", "Review Required"].includes(String(item.conclusion)) ||
    typeof item.decisionBasis !== "string" ||
    !Array.isArray(item.evidence)
  ) return false;
  return item.evidence.every((entry) => {
    if (!entry || typeof entry !== "object") return false;
    const citation = entry as Record<string, unknown>;
    return typeof citation.source === "string" && typeof citation.page === "number" && typeof citation.excerpt === "string";
  });
}

export function fixtureRuntimeResult(operation: RuntimeOperation, version: PolicyVersion, input: RuntimeInput = {}): NormalizedRuntimeResult {
  const analysis = fixtureAnalysis(version);
  const nodeId = input.nodeId ?? "compliance_evaluation";
  const instruction = input.instruction?.trim() ?? "";
  return {
    schemaVersion: "nodewitness.runtime@1",
    operation,
    analysis,
    recommendations: generateRecommendations(analysis),
    metadata: { promptVersion: "nodewitness-runtime@1", sourceVersion: analysis.sourceVersion },
    output: {
      workspace: operation === "workflow" ? "Aurora Family Office — Client Mandate Compliance" : null,
      workflowDescription: operation === "workflow" ? input.description?.trim() || "Generate the bundled mandate compliance workflow." : null,
      nodeIds: operation === "workflow" ? buildWorkflow(version).map((node) => node.id) : [],
      nodeId: operation === "correction" ? nodeId : null,
      originalOutputs: operation === "correction" ? input.originalOutputs ?? [] : [],
      humanInstruction: operation === "correction" ? instruction : null,
      revisedOutput: operation === "correction" ? `Revised output: ${instruction}` : null,
      downstreamNodeIds: operation === "correction" ? downstreamNodes(nodeId) : [],
    },
  };
}

export function isNormalizedRuntimeResult(value: unknown, expectedOperation?: RuntimeOperation): value is NormalizedRuntimeResult {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  if (
    item.schemaVersion !== "nodewitness.runtime@1" ||
    !["workflow", "assessment", "correction"].includes(String(item.operation)) ||
    (expectedOperation && item.operation !== expectedOperation) ||
    !isNormalizedAnalysis(item.analysis) ||
    !Array.isArray(item.recommendations) ||
    !item.recommendations.every((entry) => {
      if (!entry || typeof entry !== "object") return false;
      const recommendation = entry as Record<string, unknown>;
      return ["id", "title", "eyebrow", "summary", "evidence"].every((field) => typeof recommendation[field] === "string");
    })
  ) return false;

  const metadata = item.metadata as Record<string, unknown> | undefined;
  const output = item.output as Record<string, unknown> | undefined;
  if (
    !metadata || metadata.promptVersion !== "nodewitness-runtime@1" || !["IPS v1", "IPS v2"].includes(String(metadata.sourceVersion)) ||
    !output || !(typeof output.workspace === "string" || output.workspace === null) ||
    !(typeof output.workflowDescription === "string" || output.workflowDescription === null) ||
    !Array.isArray(output.nodeIds) || !output.nodeIds.every((entry) => typeof entry === "string") ||
    !(typeof output.nodeId === "string" || output.nodeId === null) ||
    !Array.isArray(output.originalOutputs) || !output.originalOutputs.every((entry) => typeof entry === "string") ||
    !(typeof output.humanInstruction === "string" || output.humanInstruction === null) ||
    !(typeof output.revisedOutput === "string" || output.revisedOutput === null) ||
    !Array.isArray(output.downstreamNodeIds) || !output.downstreamNodeIds.every((entry) => typeof entry === "string")
  ) return false;

  if (item.operation === "workflow") return typeof output.workspace === "string" && typeof output.workflowDescription === "string" && output.nodeIds.length > 0;
  if (item.operation === "correction") return typeof output.nodeId === "string" && typeof output.humanInstruction === "string" && typeof output.revisedOutput === "string";
  return true;
}

export function diffPolicy(from: PolicyVersion, to: PolicyVersion) {
  const oldPolicy = POLICIES[from];
  const newPolicy = POLICIES[to];
  return {
    oldRule: oldPolicy.rule,
    newRule: newPolicy.rule,
    thresholdChange: `${oldPolicy.threshold}% to ${newPolicy.threshold}%`,
    scopeChange: "Direct-only to direct + look-through",
    page: newPolicy.page,
  };
}

export function affectedNodesForSourceChange(event: string): string[] {
  return event === "source.version.changed" ? [...AFFECTED_CRYPTO_NODES] : [];
}

export function applyAffectedWorkflow(current: WorkflowNode[], version: PolicyVersion, affectedIds: string[]) {
  const affected = new Set(affectedIds);
  const next = new Map(buildWorkflow(version).map((node) => [node.id, node]));
  return current.map((node) => affected.has(node.id) ? next.get(node.id)! : node);
}

export function generateRecommendations(analysis: NormalizedAnalysis): Recommendation[] {
  if (analysis.conclusion !== "Review Required") return [];
  return [
    {
      id: "case",
      title: "Open remediation case",
      eyebrow: "PRIMARY REMEDIATION",
      summary: `Create a local case to reduce total crypto exposure from ${analysis.applicableExposure.toFixed(1)}% to ${analysis.threshold.toFixed(1)}% or below.`,
      evidence: "IPS v2 p.2 + portfolio snapshot",
    },
    {
      id: "memo",
      title: "Generate compliance memo",
      eyebrow: "DOCUMENT",
      summary: "Document the policy change, measured exposure, conclusion, and approval record.",
      evidence: "IPS v1/v2 semantic diff + run 002",
    },
    {
      id: "notification",
      title: "Draft adviser notification",
      eyebrow: "COMMUNICATION",
      summary: "Prepare a local draft requesting review; no message will be sent.",
      evidence: "Review Required conclusion",
    },
    {
      id: "validation",
      title: "Validate look-through data",
      eyebrow: "DATA QUALITY",
      summary: `Confirm the ${PORTFOLIO.indirectCrypto.toFixed(1)}% indirect exposure with the latest fund, ETF, and derivative files.`,
      evidence: "Portfolio look-through snapshot",
    },
    {
      id: "concentration",
      title: "Watch issuer concentration",
      eyebrow: "NEAR-LIMIT ATTENTION",
      summary: `Track the ${PORTFOLIO.issuerExposure.toFixed(1)}% largest-issuer position against the ${PORTFOLIO.maxIssuerExposure.toFixed(1)}% maximum.`,
      evidence: `${(PORTFOLIO.maxIssuerExposure - PORTFOLIO.issuerExposure).toFixed(1)} percentage points of headroom`,
    },
  ];
}

export function createAuditEvent(event: AuditEvent): AuditEvent {
  return { ...event };
}

const evidence = (version: PolicyVersion): Evidence[] => {
  const policy = POLICIES[version];
  return [
    {
      label: `${policy.version} / Cryptocurrency limits`,
      excerpt: policy.rule,
      page: policy.page,
      href: `${policy.href}#page=${policy.page}`,
      sourceVersion: policy.version,
    },
  ];
};

const portfolioEvidence: Evidence[] = [
  {
    label: "Portfolio snapshot / 18 Jul 2026",
    excerpt: "Direct crypto 2.0%; look-through crypto 6.2%; total crypto 8.2%; largest issuer 18.7%; liquid allocation 6.4%.",
    page: 3,
    href: "/demo/aurora-ips-v2.pdf#page=3",
    sourceVersion: "Portfolio 2026-07-18",
  },
];

const makeNode = (
  version: PolicyVersion,
  id: string,
  x: number,
  y: number,
  label: string,
  kind: string,
  description: string,
  status: NodeStatus,
  inputs: string[],
  outputs: string[],
  decisionBasis: string,
  citations: Evidence[] = evidence(version),
): WorkflowNode => {
  const changed = version === 2 && (AFFECTED_CRYPTO_NODES as readonly string[]).includes(id);
  const runNumber = changed ? "002" : "001";
  return {
    id,
    position: { x, y },
    data: {
      label,
      kind,
      description,
      status,
      inputs,
      outputs,
      evidence: citations,
      sourceVersion: id === "portfolio_source" ? "Portfolio 2026-07-18" : POLICIES[version].version,
      decisionBasis,
      promptVersion: "policy-agent@1.3.0",
      schemaVersion: "nodewitness.run@1",
      runtimeMode: "Deterministic fixture",
      timestamp: changed ? "2026-07-18T10:14:22-04:00" : "2026-07-18T09:30:06-04:00",
      duration: `${180 + id.length * 7} ms`,
      runId: `run-aurora-${runNumber}-${id}`,
      threadId: null,
      humanModified: false,
      history: changed
        ? ["Run 002 - source.version.changed", "Run 001 - initial workspace generation"]
        : ["Run 001 - initial workspace generation"],
    },
  };
};

export function buildWorkflow(version: PolicyVersion): WorkflowNode[] {
  const compliance = evaluateCompliance(version);
  const policy = POLICIES[version];
  const cryptoStatus: NodeStatus = compliance.result === "Pass" ? "pass" : "review";
  return [
    makeNode(version, "ips_source", 0, 40, "IPS document source", "SOURCE", "Authoritative client mandate PDF with stable page citations.", "ready", [policy.version], ["Verified PDF pages", "Source fingerprint"], "The bundled policy document is present and readable."),
    makeNode(version, "portfolio_source", 0, 280, "Portfolio snapshot", "SOURCE", "Synthetic holdings and look-through exposure as of 18 Jul 2026.", "ready", ["Custodian snapshot", "Fund look-through file"], ["Normalized exposure snapshot"], "All required exposure fields are present.", portfolioEvidence),
    makeNode(version, "source_versioning", 260, 40, "Source versioning", "CONTROL", "Tracks document fingerprint, version, and source-change events.", "pass", [policy.version, "PDF fingerprint"], [`Active source: ${policy.version}`], version === 1 ? "First observed source established as baseline." : "A new fingerprint emitted source.version.changed."),
    makeNode(version, "policy_extraction", 520, 40, "Policy extraction", "AGENT", "Converts policy text into a reviewable rule schema.", cryptoStatus, [policy.rule], [`Threshold: ${policy.threshold}%`, `Scope: ${policy.scope}`], "The threshold and exposure scope are copied from the cited policy clause."),
    makeNode(version, "version_diff", 520, 270, "Version diff", "MONITOR", "Compares policy meaning, not just document text.", version === 1 ? "idle" : "attention", [version === 1 ? "No prior revision" : POLICIES[1].rule, policy.rule], [version === 1 ? "Baseline recorded" : "10% -> 5%", version === 1 ? "No semantic delta" : "Direct-only -> look-through"], version === 1 ? "A baseline has no prior version to compare." : "Threshold tightened and the exposure definition expanded.", version === 1 ? evidence(1) : [...evidence(1), ...evidence(2)]),
    makeNode(version, "crypto_rule", 790, 20, "Crypto mandate rule", "RULE", "Executable client mandate constraint for cryptocurrency exposure.", cryptoStatus, [`Exposure scope: ${policy.scope}`, `Maximum: ${policy.threshold}%`], [`Rule status: ${compliance.result}`], `Compare the applicable ${compliance.exposure.toFixed(1)}% exposure with the ${policy.threshold.toFixed(1)}% maximum.`),
    makeNode(version, "exposure_calculation", 790, 270, "Exposure calculation", "COMPUTE", "Aggregates direct and eligible look-through cryptocurrency exposure.", version === 1 ? "pass" : "attention", ["Direct: 2.0%", "Indirect: 6.2%"], [version === 1 ? "Applicable exposure: 2.0%" : "Total exposure: 8.2%"], version === 1 ? "IPS v1 applies only direct holdings." : "IPS v2 explicitly includes funds, ETFs, and derivatives.", portfolioEvidence),
    makeNode(version, "compliance_evaluation", 1070, 130, "Compliance evaluation", "DECISION", "Produces the structured mandate conclusion.", cryptoStatus, [`Applicable exposure: ${compliance.exposure.toFixed(1)}%`, `Maximum: ${policy.threshold.toFixed(1)}%`], [`Conclusion: ${compliance.result}`, compliance.variance > 0 ? `Excess: ${compliance.variance.toFixed(1)} pts` : `Headroom: ${Math.abs(compliance.variance).toFixed(1)} pts`], compliance.result === "Pass" ? "Applicable exposure is below the mandate maximum." : "Total exposure exceeds the mandate maximum; human review is required.", [...evidence(version), ...portfolioEvidence]),
    makeNode(version, "concentration_check", 1060, 420, "Issuer concentration", "ATTENTION", "Parallel near-limit check for single-issuer exposure.", "attention", ["Largest issuer: 18.7%", "Maximum: 20.0%"], ["Headroom: 1.3 pts", "Attention item created"], "The limit is not breached, but remaining headroom is below 2 percentage points.", portfolioEvidence),
    makeNode(version, "liquidity_check", 1060, 630, "Liquidity minimum", "ATTENTION", "Parallel mandate check for liquid allocation.", "pass", ["Liquid allocation: 6.4%", "Minimum: 5.0%"], ["Headroom: 1.4 pts", "Pass"], "Liquid allocation remains above the policy minimum.", portfolioEvidence),
    makeNode(version, "recommendation_generation", 1350, 130, "Recommendation generation", "AGENT", "Creates discrete, independently reviewable safe actions.", version === 1 ? "idle" : "review", [`Compliance: ${compliance.result}`, "Concentration: Attention"], [version === 1 ? "No remediation required" : "5 action proposals"], version === 1 ? "No breach-driven actions are needed." : "Each proposal addresses the breach, evidence quality, communication, or near-limit risk."),
    makeNode(version, "human_approval", 1630, 130, "Human approval gate", "CONTROL", "Blocks every side effect until a named proposal is approved.", version === 1 ? "idle" : "review", [version === 1 ? "No pending proposals" : "5 pending proposals"], ["No action executed"], "Proposal status is pending until an explicit user decision is recorded."),
    makeNode(version, "remediation_case", 1920, 10, "Remediation case", "OUTPUT", "Visible local case record; no external ticketing integration.", "idle", ["Approved case proposal"], ["Local case record"], "Execution is gated by proposal-specific approval."),
    makeNode(version, "compliance_memo", 1920, 210, "Compliance memo", "OUTPUT", "Downloadable Markdown memo generated after approval.", "idle", ["Approved memo proposal"], ["Markdown artifact"], "Execution is gated by proposal-specific approval."),
    makeNode(version, "adviser_notification", 1920, 410, "Adviser notification", "OUTPUT", "Local adviser draft; no email is sent.", "idle", ["Approved notification proposal"], ["Markdown draft"], "Execution is gated by proposal-specific approval."),
  ];
}

export function searchWorkflowNodes(nodes: WorkflowNode[], query: string) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];

  return nodes.filter((node) =>
    [
      node.id,
      node.data.label,
      node.data.description,
      node.data.decisionBasis,
      ...node.data.inputs,
      ...node.data.outputs,
      ...node.data.evidence.flatMap((item) => [item.label, item.excerpt]),
    ]
      .join(" ")
      .toLowerCase()
      .includes(normalized),
  );
}

export const GRAPH_EDGES: GraphEdge[] = [
  { id: "e1", source: "ips_source", target: "source_versioning" },
  { id: "e2", source: "source_versioning", target: "policy_extraction" },
  { id: "e3", source: "source_versioning", target: "version_diff" },
  { id: "e4", source: "policy_extraction", target: "crypto_rule" },
  { id: "e5", source: "version_diff", target: "crypto_rule" },
  { id: "e6", source: "portfolio_source", target: "exposure_calculation" },
  { id: "e7", source: "crypto_rule", target: "compliance_evaluation" },
  { id: "e8", source: "exposure_calculation", target: "compliance_evaluation" },
  { id: "e9", source: "portfolio_source", target: "concentration_check" },
  { id: "e10", source: "portfolio_source", target: "liquidity_check" },
  { id: "e11", source: "compliance_evaluation", target: "recommendation_generation" },
  { id: "e12", source: "concentration_check", target: "recommendation_generation" },
  { id: "e13", source: "recommendation_generation", target: "human_approval" },
  { id: "e14", source: "human_approval", target: "remediation_case" },
  { id: "e15", source: "human_approval", target: "compliance_memo" },
  { id: "e16", source: "human_approval", target: "adviser_notification" },
];

export const ACTION_PROPOSALS = generateRecommendations(fixtureAnalysis(2));

export function downstreamNodes(nodeId: string) {
  const seen = new Set<string>();
  const queue = [nodeId];
  while (queue.length) {
    const current = queue.shift()!;
    for (const edge of GRAPH_EDGES) {
      if (edge.source === current && !seen.has(edge.target)) {
        seen.add(edge.target);
        queue.push(edge.target);
      }
    }
  }
  return [...seen];
}
