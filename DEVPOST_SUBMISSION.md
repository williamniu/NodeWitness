# NodeWitness

> Build AI agents anyone can understand, review, and control.

## Inspiration

Enterprise teams want the productivity of AI agents, but high-stakes professionals cannot delegate accountability to a black box. The gap is especially clear in wealth management: every client may have a different Investment Policy Statement, private restrictions, exceptions, and approval requirements. A conclusion that was correct yesterday can become wrong as soon as a client updates a document.

We were inspired by a simple question:

> What if the people who understand the business rules—but do not write code—could build an agent, inspect every important step, correct it, and decide exactly which actions it may execute?

That became NodeWitness: an operator-first governance layer for traceable, reviewable, monitorable, and human-controlled AI agents.

## What it does

NodeWitness turns a natural-language mandate into an interactive agent workflow. Our hackathon workspace monitors mandate compliance for the synthetic **Aurora Family Office**.

The initial IPS permits direct cryptocurrency exposure up to 10%. With 2.0% direct exposure, the deterministic engine returns **Pass**.

When IPS v2 arrives, NodeWitness:

1. preserves IPS v1 and records a `source.version.changed` event;
2. identifies the threshold change from 10% to 5%;
3. identifies the scope expansion from direct holdings to total look-through exposure;
4. cites the exact PDF version, page, and quote;
5. selects and re-runs only the affected crypto branch;
6. preserves the run IDs and statuses of unrelated concentration and liquidity checks;
7. changes the conclusion to **Review Required** because total crypto exposure is 8.2%; and
8. creates separate, evidence-backed remediation proposals behind a human approval gate.

Every node can be searched and opened to inspect its inputs, outputs, evidence, decision basis, source version, runtime metadata, and history. Every recommendation independently supports **Approve**, **Reject**, **Edit**, and **View Evidence**. Human corrections preserve the original output and re-run only downstream nodes.

Approved actions are deliberately safe and local: NodeWitness can create a remediation case, generate a downloadable Markdown compliance memo, and generate an adviser notification draft. It never sends a trade, email, or external ticket in the MVP. The complete event history can be exported as audit JSON.

## How we built it

We built NodeWitness as a small localhost-first Next.js application using React and TypeScript.

- **@xyflow/react** renders the pan-and-zoom workflow, minimap, selection, status states, search highlighting, and animated affected edges.
- A **pure deterministic TypeScript domain engine** performs policy diffing, exposure evaluation, affected-node selection, recommendation generation, and audit-event creation.
- Two bundled synthetic IPS PDFs provide stable page numbers and evidence excerpts.
- One normalized `nodewitness.runtime@1` schema accepts either deterministic fixtures or validated Live Codex results.
- A server-only **Model Context Protocol** adapter starts and reuses a local `codex mcp-server` over stdio. It uses the authenticated Codex CLI, read-only sandboxing, approval policy `never`, bounded timeouts, and strict response validation. It does not use an OpenAI API key.
- If Codex is unavailable, malformed, or slow, the application preserves its state and continues through deterministic Demo Mode.
- Browser `localStorage` preserves useful demo state, while Reset Demo restores the original IPS v1 passing baseline.
- Safe local handlers generate the remediation record and Markdown artifacts only after individual approval.

We intentionally did not add a database, authentication, cloud infrastructure, external connectors, a vector store, or a generic orchestration framework. That kept the product focused on the trust and governance experience we wanted to prove.

## Challenges we faced

### Making AI flexibility compatible with deterministic compliance

Language models are useful for interpreting and revising text, but threshold calculations and execution boundaries must be predictable. We separated those responsibilities: Codex handles bounded structured-language operations, while pure functions own the numerical decision, dependency graph, and allowed actions.

### Demonstrating “real time” without making the demo fragile

A live model or network dependency could ruin a four-minute presentation. We created identical Live and Demo contracts, strict validation, bounded timeouts, and state-preserving fallback. This let us demonstrate a real local Codex MCP runtime without making it a single point of failure.

### Re-running only what changed

The visually impressive version was not enough; unaffected checks also had to retain their original run identity. We modeled explicit graph dependencies, computed the affected closure, and verified that concentration and liquidity remain unchanged when only the crypto rule changes.

### Showing reasoning without exposing chain-of-thought

Reviewability does not require private model reasoning. We designed the inspector around concise decision basis, structured inputs and outputs, exact source evidence, schema/runtime metadata, and immutable run history.

### Preserving genuine human control

It was tempting to add a single “approve all” button. We deliberately avoided it. Each recommendation has an independent lifecycle, edited text never overwrites the original, and pending or rejected proposals cannot execute.

## What we learned

We learned that observability and governance are different products. Logs help developers debug after a run; governance helps accountable operators understand and intervene before an action occurs.

We also learned that provenance becomes most valuable when it is connected to change. A PDF citation is useful, but a versioned citation connected to a semantic diff, affected-node calculation, revised conclusion, human decision, and artifact is far more powerful.

Finally, the safest AI architecture is not “AI everywhere.” Combining a narrow generative layer with deterministic rules, strict schemas, immutable history, and explicit human gates produced a system that is both more reliable and easier to explain.

## Accomplishments that we are proud of

- A complete source-update story that finishes in about five seconds.
- Visible proof that only affected nodes re-run.
- Exact PDF page evidence for every compliance conclusion.
- Global workflow search and a separate node-level search.
- Human edits and corrections that preserve originals and downstream lineage.
- Proposal-level approval with no batch authorization.
- Tangible remediation, memo, notification, and audit artifacts.
- A real optional Codex MCP runtime with deterministic offline fallback and zero incremental API cost.
- A production build, lint pass, and focused automated test suite.

## What's next for NodeWitness

The next step is to validate the workflow with RIA compliance teams, then add authenticated workspaces, role-based approvals, durable encrypted storage, configurable policy schemas, and portfolio/document connectors. The long-term architecture is a hybrid SaaS control plane with customer-controlled private or VPC data planes.

The same primitives can extend beyond wealth management: source versions, evidence, decisions, corrections, human gates, safe actions, and audit events can govern agents in legal, healthcare, insurance, cybersecurity, procurement, and financial operations.

## Built with

- TypeScript
- Next.js
- React
- Node.js
- @xyflow/react
- Model Context Protocol (MCP)
- OpenAI Codex
- Codex CLI
- Native CSS
- HTML5
- Browser localStorage
- PDF
- ESLint
- Node.js Test Runner
- Git
- GitHub
