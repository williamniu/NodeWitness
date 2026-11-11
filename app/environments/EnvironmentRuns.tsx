"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import styles from "./environment.module.css";

type RunSummary = { run_id: string; scenario_id: string; agent: string; status: string; label?: string; tool_calls: number; duration_seconds: number };
type Group = { planned: number; recorded: number; verified_trials: number; completed: number; failed: number; blocked: number; not_run: number; compliant_completions: number; unauthorized_attempts: number; actual_unauthorized_effects: number; three_of_three_cases: number | null };
type LearningGroup = { planned: number; recorded: number; passed: number; scored: number; truncated: number; blocked: number; by_case: Record<string, { passed: number; recorded: number }> };
type Dataset = "agent-env" | "agent-rl";
type Manifest = {
  human_review?: string; gymnasium?: string; trace_directory?: string;
  groups: Partial<{ qwen: Group; training: LearningGroup; initial: LearningGroup; learned: LearningGroup }>;
  runs: RunSummary[]; limits: string;
};
type Transition = { action_id: number; observation: Record<string, number>; reward: number; terminated: boolean; truncated: boolean };
type Trial = RunSummary & {
  seed: number; presentation: string; data_origin: string; image_id: string;
  model?: { model: string | null; digest?: string; runtime_version?: string };
  environment_version: string; verifier_version: string;
  steps: { index: number; action: { tool: string; args: unknown }; observation: { ok: boolean; kind?: string; error?: string; result?: unknown }; duration_seconds: number; transition?: Transition | null }[];
  verifier?: { reward: number; task_completion: boolean; compliant_completion: boolean; evidence_valid_and_fresh: boolean; expected_outcome: string; state_digest: string; actual_unauthorized_effects: number; job_checks?: { result?: { http_status?: number; body?: unknown } }[] } | null;
  replay?: { passed: boolean; error?: string }; termination?: { reason: string; terminated?: boolean; truncated?: boolean };
  errors: { layer: string; kind: string }[];
};

function observationStatus(observation: Trial["steps"][number]["observation"]) {
  if (!observation.ok) return observation.kind ?? "ERROR";
  const result = observation.result;
  if (result && typeof result === "object" && "http_status" in result) return `HTTP ${result.http_status}`;
  return "TOOL OK";
}

function runLabel(run: RunSummary) {
  return run.label ?? (run.agent === "baseline" ? "Scripted baseline" : "Real Qwen");
}

function learningBreakdown(group: LearningGroup) {
  return Object.entries(group.by_case).map(([caseId, result]) =>
    `${caseId} ${result.passed}/${result.recorded}`
  ).join(" · ");
}

export default function EnvironmentRuns() {
  const [dataset, setDataset] = useState<Dataset>("agent-env");
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [selected, setSelected] = useState("");
  const [loadedTrial, setTrial] = useState<Trial | null>(null);
  const trial = loadedTrial?.run_id === selected ? loadedTrial : null;
  const [error, setError] = useState("");
  const rl = dataset === "agent-rl";
  const base = `/demo/${dataset}`;
  const traces = manifest?.trace_directory ? `${base}/${encodeURIComponent(manifest.trace_directory)}` : base;

  function chooseDataset(next: Dataset) {
    if (next === dataset) return;
    setDataset(next);
    setManifest(null);
    setSelected("");
    setTrial(null);
    setError("");
  }

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${base}/manifest.json`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error("Recorded runs are not available for this dataset yet."); return response.json(); })
      .then((data: Manifest) => {
        if (controller.signal.aborted) return;
        setManifest(data);
        setSelected(data.runs.find(run => run.agent === "qwen")?.run_id ?? data.runs[0]?.run_id ?? "");
      })
      .catch(cause => { if (!controller.signal.aborted) setError(String(cause.message)); });
    return () => controller.abort();
  }, [base]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    fetch(`${traces}/${encodeURIComponent(selected)}.json`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error("This recorded run could not be loaded."); return response.json(); })
      .then(data => { if (!controller.signal.aborted) setTrial(data); })
      .catch(cause => { if (!controller.signal.aborted) setError(String(cause.message)); });
    return () => controller.abort();
  }, [selected, traces]);
  const qwen = manifest?.groups.qwen;
  const training = manifest?.groups.training;
  const initial = manifest?.groups.initial;
  const learned = manifest?.groups.learned;
  return <main className={styles.page}>
    <header className={styles.header}>
      <Link href="/" className={styles.brand}>NodeWitness <span>Agent environments</span></Link>
      <Link href="/">Open financial review workspace →</Link>
    </header>
    <nav className={styles.datasets} aria-label="Recorded datasets">
      <button type="button" aria-pressed={!rl} onClick={() => chooseDataset("agent-env")}>Agent evaluation</button>
      <button type="button" aria-pressed={rl} onClick={() => chooseDataset("agent-rl")}>RL learning</button>
    </nav>
    <section className={rl ? `${styles.intro} ${styles.rlIntro}` : styles.intro}>
      {rl ? <>
        <h1>Configuration repair · RL learning</h1>
        <p>Compare a tabular policy before and after learning from independently verified rewards. Both policies ran on the same held-out seeds for E03 and E05.</p>
        <div className={styles.labels}><span>Recorded local experiment</span><span>Synthetic service · actual job checks</span>{manifest?.gymnasium && <span>Gymnasium {manifest.gymnasium}</span>}</div>
      </> : <>
        <p className={styles.eyebrow}>CONFIGURATION REPAIR · ONE ENVIRONMENT FAMILY</p>
        <h1>Inspect what the agent did.<br />Verify what actually changed.</h1>
        <p>A real model investigates a small Python service using bounded tools. An external verifier checks actual job behavior, evidence freshness, and protected state.</p>
        <div className={styles.labels}><span>Recorded evidence · no live execution on this page</span><span>Synthetic service and data · simulated downstream</span><span>Human explanation review: {manifest?.human_review ?? "pending"}</span></div>
      </>}
    </section>
    <section className={styles.metrics} aria-label="Evaluation summary">
      {rl ? <>
        <article><small>Training episodes</small><strong>{training ? `${training.recorded} / ${training.planned}` : "—"}</strong><p>{training ? `${training.scored} scored · ${training.truncated} truncated · ${training.blocked} blocked` : "Local episode counts"}</p></article>
        <article><small>Initial policy · verified outcomes</small><strong>{initial ? `${initial.passed} / ${initial.planned}` : "—"}</strong><p>{initial ? learningBreakdown(initial) : "Held-out episodes"}</p></article>
        <article><small>Learned policy · verified outcomes</small><strong>{learned ? `${learned.passed} / ${learned.planned}` : "—"}</strong><p>{learned ? learningBreakdown(learned) : "Same held-out episodes"}</p></article>
      </> : <>
      <article><small>QWEN COMPLIANT COMPLETION</small><strong>{qwen ? `${qwen.compliant_completions} / ${qwen.planned}` : "Pending"}</strong><p>{qwen ? `${qwen.recorded} recorded · ${qwen.failed} failed · ${qwen.blocked} blocked · ${qwen.not_run} not run` : "No evaluated result is assumed."}</p></article>
      <article><small>ACTUAL UNAUTHORIZED EFFECTS</small><strong>{qwen?.verified_trials ? qwen.actual_unauthorized_effects : "Pending"}</strong><p>{qwen ? `${qwen.unauthorized_attempts} unauthorized attempts across ${qwen.verified_trials} verified trials` : "Attempts and side effects are counted separately."}</p></article>
      <article><small>THREE OF THREE REPEATS</small><strong>{qwen ? `${qwen.three_of_three_cases} / 6 cases` : "Pending"}</strong><p>Six frozen variants; this is a small experiment, not a general benchmark.</p></article>
      </>}
    </section>
    {error && <p className={styles.error} role="alert">{error}</p>}
    <section className={styles.workspace} aria-label="Recorded run inspector">
      <aside className={styles.sidebar}>
        <h2>Task / run</h2>
        <label htmlFor="recorded-run">Choose a recorded attempt</label>
        <select id="recorded-run" value={selected} onChange={event => { setError(""); setSelected(event.target.value); }}>
          {manifest?.runs.map(run => <option key={run.run_id} value={run.run_id}>{run.scenario_id} · {runLabel(run)} · {run.run_id.slice(-4)}</option>)}
        </select>
        <h3>Lifecycle</h3>
        <ol><li>Reset a seeded, isolated task.</li><li>Observe and act through permitted tools.</li><li>Verify actual service behavior.</li><li>Replay the same recorded actions.</li><li>Close the task container.</li></ol>
        <p>{rl ? "Replay repeats the saved actions in a fresh container with the same seed." : "Viewing this page is recorded replay. Action replay reruns these actions in a fresh container. A new model trial calls the model again."}</p>
        {manifest && <a href={`${base}/manifest.json`} download>Download experiment summary ↓</a>}
      </aside>
      <div className={styles.inspector} aria-live="polite" aria-busy={Boolean(selected && !trial)}>
        {!trial ? <p>{selected ? "Loading recorded run…" : "Run the CLI to generate evaluation evidence."}</p> : <>
          <div className={styles.runHeading}><div><p className={styles.eyebrow}>{runLabel(trial)}</p><h2>{trial.scenario_id} · {trial.status}</h2></div><a href={`${traces}/${encodeURIComponent(trial.run_id)}.json`} download>Download trace ↓</a></div>
          <dl className={styles.facts}>
            <div><dt>Independent reward</dt><dd>{trial.status === "blocked" ? "Unavailable" : trial.verifier?.reward ?? "Unavailable"}</dd></div>
            <div><dt>Expected outcome</dt><dd>{trial.verifier?.expected_outcome.replaceAll("_", " ") ?? "Unavailable"}</dd></div>
            <div><dt>Evidence valid and fresh</dt><dd>{trial.verifier ? String(trial.verifier.evidence_valid_and_fresh) : "Unavailable"}</dd></div>
            <div><dt>Same-action replay</dt><dd>{trial.replay ? trial.replay.passed ? "PASS" : "FAIL" : "NOT RUN"}</dd></div>
            <div><dt>Tool calls / duration</dt><dd>{trial.tool_calls} / {trial.duration_seconds}s</dd></div>
            <div><dt>Seed / episode ending</dt><dd>{trial.seed} / {trial.termination?.truncated ? "truncated" : trial.termination?.reason?.replaceAll("_", " ") ?? "Unavailable"}</dd></div>
          </dl>
          <p className={styles.explanation}>{trial.status === "truncated" ? "The runner reached its budget before a submission." : trial.status === "blocked" ? "An infrastructure error interrupted the episode." : trial.verifier?.compliant_completion ? "The external verifier accepted the expected outcome and current evidence without unauthorized attempts or effects." : "The verifier did not accept the outcome. Inspect the job responses and tool observations."}</p>
          {rl && trial.verifier?.job_checks && <details className={styles.verifier}>
            <summary>Verifier job checks · {trial.verifier.job_checks.map(check => check.result?.http_status ? `HTTP ${check.result.http_status}` : "unavailable").join(" / ")}</summary>
            <pre>{JSON.stringify(trial.verifier.job_checks.map(check => check.result), null, 2)}</pre>
          </details>}
          <h3>Trajectory</h3>
          <ol className={styles.trajectory}>
            {trial.steps.map(step => <li key={step.index}><details><summary><span>{String(step.index + 1).padStart(2, "0")} · {step.action.tool}</span><span>{observationStatus(step.observation)}{step.transition ? ` · reward ${step.transition.reward}` : ` · ${step.duration_seconds}s`}</span></summary><pre>{JSON.stringify({ action: step.action.args, observation: step.observation, ...(step.transition ? { gymnasium_step: step.transition } : {}) }, null, 2)}</pre></details></li>)}
          </ol>
          {trial.errors.length > 0 && <div className={styles.error}><h3>Recorded errors</h3><pre>{JSON.stringify(trial.errors, null, 2)}</pre></div>}
          <details><summary>Versions and comparable state</summary><dl className={styles.identity}><dt>{rl ? "Policy" : "Model"}</dt><dd>{rl ? runLabel(trial) : trial.model?.model ?? "Deterministic reference baseline"}</dd><dt>Runtime</dt><dd>{rl ? `Gymnasium ${manifest?.gymnasium ?? ""}` : trial.model?.runtime_version ?? "No model"}</dd><dt>Environment / verifier</dt><dd>{trial.environment_version} / {trial.verifier_version}</dd><dt>Image ID</dt><dd>{trial.image_id}</dd><dt>Final normalized state</dt><dd>{trial.verifier?.state_digest ?? "Unavailable"}</dd></dl></details>
        </>}
      </div>
    </section>
    <footer className={styles.footer}><p>{manifest?.limits ?? "Evaluation and human review are pending."}</p><p>CLI execution and container controls belong to the trusted local runner. This view reads reviewed public-safe exports.</p></footer>
  </main>;
}
