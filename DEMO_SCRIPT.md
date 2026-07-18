# NodeWitness — Four-Minute Demo Video Script

## Recording setup (not part of the four minutes)

1. Run `npm run dev` and open `http://127.0.0.1:3000` at 1440×900 or 1280×800.
2. Wait for the **Live Codex** badge. Keep deterministic Demo Mode ready as the fallback.
3. Click **Reset Demo**, dismiss the reset notification, and return the page to the top.
4. Keep IPS v1 active, the graph fitted to view, **Findings** selected, and the default `Compliance evaluation` node open.
5. Record the app only. Hide bookmarks, personal notifications, terminals, and unrelated tabs.
6. Speak calmly at roughly 130–140 words per minute. Pause when the graph is moving; let the product create the drama.

## Screen map

| Area | Where it is | What it proves |
|---|---|---|
| Runtime and monitoring | Top bar | Live local Codex is available; monitoring and deterministic fallback are visible |
| Workflow brief and sources | Left panel | A non-technical user defines the agent and supplies versioned evidence |
| Searchable agent graph | Center | Every operational step is visible, selectable, and incrementally executable |
| Node inspector | Right panel | Inputs, outputs, evidence, decision basis, versions, and run lineage are reviewable |
| Control Room | Bottom | Findings, individual approvals, artifacts, and the immutable audit trail stay under human control |

## Timed script

### 0:00–0:25 — Hook: AI agents need accountable control

**On screen:** Begin on the full workspace. Slowly move the cursor across **Live Codex**, **Monitoring Active**, and the graph. Do not click yet.

**Say:**

> Enterprises do not need another black-box agent. They need to know what changed, what the agent concluded, which evidence it used, and what a human approved. NodeWitness is an operator-first control layer for building AI agents anyone can understand, review, and control. This demo monitors the client mandate for Aurora Family Office.

**Judge takeaway:** State the category and the trust problem before explaining features.

### 0:25–0:50 — No-code agent, not a static diagram

**On screen:** Point to the natural-language brief in the left panel. Click **Fit View**, then pan the graph slightly from the IPS and portfolio sources toward the approval and output nodes.

**Say:**

> A compliance professional describes the mandate in plain English. NodeWitness converts it into an executable graph: source documents, policy extraction, deterministic calculations, compliance decisions, recommendations, and an approval gate. The local Codex runtime handles structured language tasks, while a deterministic domain engine owns the compliance math and impact selection.

**Judge takeaway:** Emphasize the hybrid design: flexible AI plus deterministic controls.

### 0:50–1:20 — Traceability and search

**On screen:** Type `crypto` in **Global graph search**. Click **Compliance evaluation** in the result list. In the right inspector, type `10.0` in **Search this node**. Briefly open the IPS v1 evidence link at page 2, then return to NodeWitness.

**Say:**

> Search works across labels, IDs, rules, inputs, outputs, and evidence. One click centers the matching node. Inside it, a second search finds the exact field. Under IPS version one, direct crypto exposure is two percent against a ten percent maximum, so the conclusion is Pass. We can inspect the inputs, output, concise decision basis, run ID, schema, and the exact PDF quote on page two—without exposing private chain-of-thought.

**Judge takeaway:** This is operational reviewability, not a developer log viewer.

### 1:20–2:10 — The signature moment: policy change and incremental re-evaluation

**On screen:** Clear both searches. Click **Trigger IPS v2 event** in the left panel. During the animation, point to the two retained source versions, the `10% → 5%` diff, the scope change, progress indicator, and affected edges. After completion, point to run `002` on the crypto branch and run `001` on issuer concentration and liquidity.

**Say:**

> Now a revised client IPS arrives. NodeWitness emits a source-version-changed event and keeps version one immutable. It detects two semantic changes: the threshold tightens from ten to five percent, and the scope expands from direct holdings to total look-through exposure through funds, ETFs, and derivatives. Only nine affected nodes are queued and re-run. The unrelated concentration and liquidity checks keep their original run IDs. In about five seconds, the conclusion changes from Pass to Review Required: total crypto exposure is 8.2 percent against a five percent maximum.

**Judge takeaway:** Let the animation finish. This before-and-after transition is the centerpiece of the demo.

### 2:10–3:05 — Human governance before execution

**On screen:** In the Control Room, open **Actions**. Show all five proposals. Edit **Open remediation case** to add `with adviser review within two business days`, save it, and then approve it. Approve **Generate compliance memo** and **Draft adviser notification**. Leave the data-validation and concentration items pending.

**Say:**

> NodeWitness does not jump from a finding to autonomous action. It creates five separate, evidence-backed proposals, and there is deliberately no batch approval. I can edit this remediation, while the original text remains visible, then approve it independently. I will also approve a compliance memo and an adviser notification draft. The other recommendations remain pending, so they do not execute. The approval gate allows only safe local actions—no trade, email, or external ticket is sent.

**Judge takeaway:** Slow down for the original-versus-edited text and the pending items; they prove meaningful human authority.

### 3:05–3:42 — Tangible outputs and complete accountability

**On screen:** Open **Artifacts**. Point to the remediation case fields, then the two downloadable Markdown files. Open **Audit** and scroll just enough to show source change, impact calculation, conclusion, edit, approval, and artifact events. Point to **Export Audit** in the top bar.

**Say:**

> Approved actions become tangible local artifacts: a complete remediation case with source versions, violated rule, exposure, threshold, owner, due date, evidence, and audit references; a downloadable compliance memo; and an adviser draft. The audit timeline records every source event, affected-node calculation, conclusion, human edit, approval, and artifact. It can be exported as JSON for downstream review.

**Judge takeaway:** Show the result, not just the process.

### 3:42–4:00 — Close on the platform vision

**On screen:** Return attention to the full graph and hover over **Suggest a correction** in the right inspector. End with the NodeWitness logo and tagline visible.

**Say:**

> A reviewer can also correct any key decision node, preserve the original output, and re-run only its downstream dependencies. Today, NodeWitness governs one RIA compliance workflow. The same primitives—sources, evidence, decisions, human gates, and audit events—can govern enterprise agents in finance, legal, healthcare, and operations. Every agent step, witnessed.

## Presentation choices that maximize judge impact

- Lead with the five-second `Pass → Review Required` transition. It is the clearest proof that the product is alive.
- Say **“operator-first governance”**, not merely “AI observability.” The user can intervene before execution, not only inspect traces afterward.
- Repeat the three architectural safeguards once each: deterministic compliance math, immutable evidence/version history, and proposal-level human approval.
- Keep the **Live Codex** badge visible, but never make the live model a single point of failure during recording.
- Do not spend video time on installation, code, PDF upload mechanics, or roadmap connectors.
- Do not claim legal automation or autonomous compliance. Say NodeWitness expands human attention while preserving human authority.
- If a take becomes unstable, switch to **Demo Mode**, reset, and record again. The normalized Live and Demo contracts produce the same product story.
