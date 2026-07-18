import assert from "node:assert/strict";
import test from "node:test";

import {
  AFFECTED_CRYPTO_NODES,
  affectedNodesForSourceChange,
  applyAffectedWorkflow,
  buildWorkflow,
  canExecuteLocalAction,
  createAuditEvent,
  diffPolicy,
  downstreamNodes,
  evaluateCompliance,
  fixtureAnalysis,
  fixtureRuntimeResult,
  generateRecommendations,
  isNormalizedAnalysis,
  isNormalizedRuntimeResult,
  nextSourceUpdatePhase,
  searchWorkflowNodes,
  type SourceUpdatePhase,
} from "../lib/workflow.ts";

test("IPS v1 passes direct-only exposure while IPS v2 requires review", () => {
  assert.deepEqual(evaluateCompliance(1), { exposure: 2, threshold: 10, result: "Pass", variance: -8 });
  assert.deepEqual(evaluateCompliance(2), { exposure: 8.2, threshold: 5, result: "Review Required", variance: 3.2 });
});

test("the policy diff captures threshold and semantic scope changes", () => {
  const diff = diffPolicy(1, 2);
  assert.equal(diff.thresholdChange, "10% to 5%");
  assert.equal(diff.scopeChange, "Direct-only to direct + look-through");
  assert.match(diff.oldRule, /Direct cryptocurrency exposure/);
  assert.match(diff.newRule, /look-through exposure/);
  assert.equal(diff.page, 2);
});

test("a source revision re-runs only the crypto branch", () => {
  const affected = affectedNodesForSourceChange("source.version.changed");
  assert.deepEqual(affected, [...AFFECTED_CRYPTO_NODES]);
  assert.equal(affected.includes("concentration_check"), false);
  assert.equal(affected.includes("liquidity_check"), false);
  assert.equal(affected.includes("portfolio_source"), false);

  const before = new Map(buildWorkflow(1).map((node) => [node.id, node.data.runId]));
  const after = new Map(buildWorkflow(2).map((node) => [node.id, node.data.runId]));
  assert.equal(before.get("concentration_check"), after.get("concentration_check"));
  assert.equal(before.get("liquidity_check"), after.get("liquidity_check"));
  assert.notEqual(before.get("compliance_evaluation"), after.get("compliance_evaluation"));
});

test("the normalized fixture produces the five revised-run recommendations", () => {
  const v1 = fixtureAnalysis(1);
  const v2 = fixtureAnalysis(2);
  assert.equal(isNormalizedAnalysis(v1), true);
  assert.equal(isNormalizedAnalysis(v2), true);
  assert.deepEqual(generateRecommendations(v1), []);
  assert.deepEqual(generateRecommendations(v2).map((item) => item.id), ["case", "memo", "notification", "validation", "concentration"]);
});

test("audit-event creation is pure and preserves the normalized event shape", () => {
  const input = { id: "audit-1", time: "10:14:22", type: "source.version.changed", detail: "IPS v1 -> IPS v2", actor: "Source monitor" };
  const event = createAuditEvent(input);
  assert.deepEqual(event, input);
  assert.notEqual(event, input);
});

test("workflow search indexes crypto content and ignores an empty query", () => {
  const matches = searchWorkflowNodes(buildWorkflow(2), "crypto").map((node) => node.id);
  assert.equal(matches.includes("ips_source"), true);
  assert.equal(matches.includes("crypto_rule"), true);
  assert.equal(matches.includes("exposure_calculation"), true);
  assert.equal(matches.includes("compliance_evaluation"), true);
  assert.deepEqual(searchWorkflowNodes(buildWorkflow(2), "   "), []);
});

test("the source update state machine is deterministic and preserves unaffected nodes", () => {
  const phases: SourceUpdatePhase[] = ["detected"];
  let phase: SourceUpdatePhase = "detected";
  let elapsed = 0;
  while (true) {
    const transition = nextSourceUpdatePhase(phase);
    if (!transition) break;
    elapsed += transition.delayMs;
    phase = transition.next;
    phases.push(phase);
  }
  assert.deepEqual(phases, ["detected", "queued", "running", "complete"]);
  assert.equal(elapsed <= 5000, true);

  const before = buildWorkflow(1);
  const affected = affectedNodesForSourceChange("source.version.changed");
  const after = applyAffectedWorkflow(before, 2, affected);
  for (const node of before.filter((item) => !affected.includes(item.id))) {
    assert.strictEqual(after.find((item) => item.id === node.id), node);
  }
  assert.equal(after.find((node) => node.id === "crypto_rule")?.data.status, "review");
  assert.equal(after.find((node) => node.id === "concentration_check")?.data.runId, "run-aurora-001-concentration_check");
  assert.equal(after.find((node) => node.id === "liquidity_check")?.data.status, "pass");
});

test("the governance gate permits only approved safe local actions", () => {
  assert.equal(canExecuteLocalAction("case", "approved"), true);
  assert.equal(canExecuteLocalAction("memo", "approved"), true);
  assert.equal(canExecuteLocalAction("notification", "approved"), true);
  assert.equal(canExecuteLocalAction("case", "pending"), false);
  assert.equal(canExecuteLocalAction("case", "edited"), false);
  assert.equal(canExecuteLocalAction("case", "rejected"), false);
  assert.equal(canExecuteLocalAction("validation", "approved"), false);
  assert.equal(canExecuteLocalAction("concentration", "approved"), false);
  const downstream = downstreamNodes("compliance_evaluation");
  assert.equal(downstream.includes("compliance_evaluation"), false);
  assert.equal(downstream.includes("recommendation_generation"), true);
  assert.equal(downstream.includes("remediation_case"), true);
});

test("Live Codex and Demo Mode share one strict runtime contract", () => {
  const workflow = fixtureRuntimeResult("workflow", 1, { description: "Monitor the client mandate." });
  const assessment = fixtureRuntimeResult("assessment", 2);
  const correction = fixtureRuntimeResult("correction", 2, {
    nodeId: "compliance_evaluation",
    originalOutputs: ["Conclusion: Review Required"],
    instruction: "Clarify the look-through evidence.",
  });
  assert.equal(isNormalizedRuntimeResult(workflow, "workflow"), true);
  assert.equal(isNormalizedRuntimeResult(assessment, "assessment"), true);
  assert.equal(isNormalizedRuntimeResult(correction, "correction"), true);
  assert.equal(correction.output.originalOutputs[0], "Conclusion: Review Required");
  assert.equal(correction.output.downstreamNodeIds.includes("remediation_case"), true);
  assert.equal(isNormalizedRuntimeResult({ ...workflow, schemaVersion: "invalid" }, "workflow"), false);
});
