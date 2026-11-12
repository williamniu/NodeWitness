# NodeWitness: three-minute walkthrough and recording plan

Status: a 180-second silent technical video is available locally and in the portfolio preview. It uses chronological samples of actual task-browser frames, with English/Chinese descriptive captions. Owner narration and human explanation review are pending; a continuous screen recording, owner voice, publication or outreach is not claimed.

## Recording setup

1. Start the local NodeWitness app: `npm run dev -- --port 3015`.
2. Open `http://127.0.0.1:3015/environments` after exporting the completed experiment.
3. Use the real Qwen E01 recording for success, E04 for controlled diagnostic timeout handling, and E05 for safe escalation. The trace itself is recorded evidence; showing it is not a fresh model trial.
4. Keep the local view inside the recording region. Exclude desktop notifications, private tabs, terminal history, credentials and unrelated files. Record your own English voice; do not synthesize or imitate it.
5. Record a fresh action replay from a separately opened task terminal if desired. Explain that it repeats recorded actions without calling the model. Never describe a saved trace as live inference.

## Narration draft (about three minutes at a measured pace)

**00:00–00:30 — What this demonstrates**

“NodeWitness makes an agent's actions and their consequences inspectable. I extended the original financial-governance prototype with a small configuration-repair environment. A real local Qwen model investigates a Python service using a fixed tool interface. The service and data are synthetic, and its downstream operations are simulated. The model decisions and tool calls are real.”

**00:30–01:15 — A real repair, shown as a recorded trajectory**

“This is a recorded attempt. The agent reads the service contract and current evidence, diagnoses the failing job, and changes an allowed configuration value. Defaults and overrides can conflict, so changing a plausible-looking file is not enough. The agent must inspect the effective behavior, rerun the diagnostic, and cite evidence it actually read after the change. It has no arbitrary shell, host files, or Docker controls.”

**01:15–01:45 — Independent verification and reward**

“The agent's completion message does not decide the reward. An external verifier sends two actual job requests and checks the returned values and source versions. It also checks that protected state is unchanged and that cited evidence is current. A healthy process can still fail the task. The tests deliberately include bad claims and tampered state to check that the verifier rejects them.”

**01:45–02:20 — Fault handling and limits**

“This scenario injects a timeout into the first job diagnostic. It is a controlled test fault, not an invented production incident. The trajectory shows whether the agent obtains more evidence, retries, and completes the task within its budget. A different case requires operator approval; there, a supported escalation is the correct outcome. Unauthorized attempts and actual unauthorized effects are counted separately.”

**02:20–03:00 — Reproduction and engineering choices**

“Each episode starts from a seed in its own non-root container, with restricted writes, no external task network, and explicit resource limits. Action replay resets the environment and executes the same recorded actions, then compares the resulting state. It does not promise that another model call will make identical decisions. I froze six cases and three Qwen attempts per case, kept the scripted baseline separate, and retained errors and missing results. This is engineering evidence for one environment family, not proof of production reliability or a trained RL agent.”

## Shot list

| Time | Actual screen/action | Evidence to show |
| --- | --- | --- |
| 00:00 | Overview and recorded-evidence labels | Synthetic data, real Qwen, pending human review |
| 00:30 | Choose Qwen E01; expand read/diagnose/set_config/reread steps | Actual action arguments and observations |
| 01:15 | Show external verdict and current evidence; expand version/state section | Reward, verifier version, normalized state, replay |
| 01:45 | Choose Qwen E04 and expand ToolTimeout plus subsequent actions | Explicit controlled-injection message and actual handling |
| 02:10 | Choose Qwen E05 | Safe escalation and protected-state evidence |
| 02:20 | Run the documented replay command, or clearly show its saved result | Same actions, no new inference, comparable outcome |
| 02:40 | Show complete evaluation summary and limitations | Denominators, errors, baseline separation |

Use actual final run IDs from the experiment manifest; do not type an invented result or stage a fake terminal success. If any selected trial fails, either explain that failure accurately or choose a genuinely completed trial and keep the overall report intact.

## Referral-ready project description (draft; not sent)

“I built a reproducible configuration-repair environment inside NodeWitness. It combines a containerized Python task service, real Qwen tool interaction, an external behavioral verifier, structured trajectories, and same-action replay. The evaluation separates task completion, permission compliance, and infrastructure failures. I can walk through the trust boundary, a real repair, a controlled failure-handling case, and the trade-offs behind keeping the harness small.”

Publication status: local review only. The existing public repository is a project reference; the new extension has not been pushed in this task. Do not use a local URL as an externally accessible demo link. Do not claim systems-language proficiency, production isolation or a full match to every job qualification from this project.

## Owner acceptance checklist

- [ ] Review the complete video for factual alignment and private content.
- [ ] Confirm English wording and delivery in your own voice.
- [ ] Score explanation quality 0/1/2 only after viewing the associated evidence.
- [ ] Approve any later public push/publication separately.

Suggested owner time: 30–45 minutes reviewing selected trajectories, 60–90 minutes recording, 45–60 minutes English practice and corrections, then 30 minutes final review. Automated checks cannot substitute for those decisions.
