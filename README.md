# NodeWitness

> Build AI agents anyone can understand, review, and control.

NodeWitness is a localhost enterprise AI-agent governance MVP. The bundled workspace, **Aurora Family Office - Client Mandate Compliance**, turns a natural-language mandate into a searchable workflow graph with source versioning, evidence citations, structured decision bases, branch-level re-runs, human corrections, proposal-specific approvals, safe local artifacts, and a downloadable audit trail.

## Architecture

- **Next.js App Router + React + TypeScript**: one monolithic local application.
- **@xyflow/react**: interactive pan, zoom, fit, selection, minimap, animated affected edges, and search highlighting.
- **Deterministic policy engine**: pure diff, evaluation, affected-node, recommendation, and audit-event functions in `lib/workflow.ts` drive the complete offline demo through the same normalized schema accepted by Live Codex.
- **Local persistence**: browser `localStorage` preserves policy version, decisions, corrections, artifacts, and audit history.
- **Codex MCP adapter**: a server-only `@modelcontextprotocol/sdk` client reuses one locally authenticated `codex mcp-server` stdio process and closes it with the application. It never uses an OpenAI API key.
- **Safe execution**: approvals can only create a visible local case or downloadable Markdown files. No trade, email, or ticketing system is connected.
- **Synthetic evidence**: two stable, three-page PDFs in `public/demo` provide exact page citations.

No database, authentication, Docker, cloud service, vector store, analytics, workflow framework, or provider abstraction is used.

## Prerequisites

- Node.js 22.13 or newer
- npm
- Optional for Live Codex Mode: a locally installed and authenticated Codex CLI

## Install and start

```bash
npm install
npm run dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The development and production start commands bind to `127.0.0.1` only.

Useful checks:

```bash
npm test
npm run lint
npm run build
npm run start
```

## Codex CLI authentication

Live Mode reuses the Codex CLI's existing local authentication. If the preflight badge stays in Demo Mode:

```bash
codex login
```

Complete the CLI sign-in flow, confirm `codex mcp-server --help` works, and restart the app. No `OPENAI_API_KEY` is required.

Check the app-side preflight after startup:

```bash
curl http://127.0.0.1:3000/api/codex/health
```

A successful response includes `"ok":true`, `"mode":"live"`, and the available `codex` tool. The UI also provides **Retry Live** and **Use Demo** controls. The implementation follows the official [Codex MCP server guide](https://learn.chatgpt.com/docs/mcp-server).

> Never read, copy, display, upload, or commit `~/.codex/auth.json` or any other Codex credential file.

## Live Codex Mode

On page load, `/api/codex/health` performs a bounded server-side MCP handshake and confirms the `codex` tool exists. Only a successful preflight enables the **Live Codex** badge. The server keeps the healthy stdio client for subsequent requests instead of spawning one process per action.

When **Generate agent** runs in Live Mode, the server adapter:

1. starts or reuses `codex mcp-server` through stdio;
2. calls the documented `codex` MCP tool with `sandbox: read-only` and `approval-policy: never`;
3. requests one strict JSON object matching the same `nodewitness.runtime@1` fixture contract used by Demo Mode;
4. validates the complete object and normalizes it before returning it to the UI; and
5. reuses the MCP process until the local application exits.

Live Mode supports three bounded operations through the same endpoint:

- `workflow`: validates the natural-language request and returns the existing safe graph schema;
- `assessment`: validates the synthetic policy, exposure, conclusion, evidence, recommendations, and metadata; and
- `correction`: validates a human instruction, preserves original outputs, and returns a revised output plus downstream node IDs.

`codex-reply` is not used because each MVP operation is complete in one request. Prompts explicitly prohibit tool calls, filesystem inspection, and private reasoning. PDF bytes and arbitrary PDF text are never sent to Codex; only the bundled synthetic facts and bounded user fields enter the request.

The adapter defaults to the documented `gpt-5.4` MCP model override for compatibility with the bundled demo environment. Set `NODEWITNESS_CODEX_MODEL` only when a separately installed Codex CLI supports another model.

If preflight, timeout, parsing, or schema validation fails, NodeWitness retains all current UI state, records the runtime-mode change, shows a calm notification, and continues in Demo Mode. Invalid model output never reaches the graph. A correction starts with the deterministic result, so a late Live failure cannot interrupt the presentation.

## Demo Mode

Demo Mode has no model or network dependency. `lib/workflow.ts` provides the same normalized policy result shape used by Live Mode.

- **IPS v1** applies a 10% maximum to direct crypto only. Direct exposure is 2.0%, so the result is **Pass**.
- **IPS v2** applies a 5% maximum to total direct plus look-through exposure. Total exposure is 8.2%, so the result is **Review Required**.
- The source change updates only the crypto branch. Portfolio, issuer-concentration, and liquidity nodes keep their original run IDs.
- Reset Demo returns to IPS v1, clears all proposal decisions and generated artifacts, and restores the clean baseline audit.

The bundled parser intentionally guarantees only the two synthetic PDFs. The upload control accepts a bundled-format PDF and deterministically triggers the IPS v2 fixture for a reliable presentation.

## Exact four-minute demo flow

**0:00-0:35 - Orient the audience**

1. Open the console and point to the Aurora workspace, runtime badge, and **Monitoring active** state.
2. Show the natural-language mandate on the left and click **Generate agent**.
3. Pan or zoom the graph; select **Compliance evaluation** to show inputs, outputs, decision basis, run ID, schema, runtime, duration, and history.

**0:35-1:10 - Prove traceability and search**

1. Search `crypto` in the global search field. Note the result count and highlighted nodes.
2. Click **Crypto mandate rule** in the search results to center and open it.
3. Search `direct` inside the node inspector and open the cited IPS v1 page.
4. Show that the active result is **Pass: 2.0% direct exposure vs 10.0% maximum**.

**1:10-2:05 - Trigger source monitoring**

1. Click **Trigger IPS v2 event**.
2. Point out the `source.version.changed` notification and animated crypto branch.
3. Note that issuer concentration and liquidity do not animate and retain `run-aurora-001` IDs.
4. Open **Version diff**: 10% to 5%, direct-only to look-through, exact IPS v2 page 2 evidence.
5. Open **Compliance evaluation**: **Review Required: 8.2% total vs 5.0% maximum**.

**2:05-3:10 - Demonstrate human control**

1. Open **Actions**. Show five discrete proposals, each with Approve, Reject, Edit, and View evidence.
2. Edit the remediation proposal and save; show the audit event.
3. Approve **Open remediation case**, **Generate compliance memo**, and **Draft adviser notification** individually.
4. Reject or approve one data-quality proposal to show independent decisions.
5. Open **Artifacts** and download the memo. Emphasize that the notification is only a draft and no external action occurred.

**3:10-4:00 - Prove correction and auditability**

1. Select **Compliance evaluation**, enter a concise correction, and submit it.
2. Show **Human modified**, preservation of the original output, and downstream-only animation.
3. Open **Audit** to show source, diff, node, conclusion, edit, approval, correction, re-run, and artifact events.
4. Click **Export audit**, then **Reset demo** to return instantly to the passing IPS v1 baseline.

## Troubleshooting

- **Port 3000 is occupied:** run `npm run dev -- --port 3001` and open the printed loopback URL.
- **Demo starts in Demo Mode:** this is expected when Codex CLI is unavailable or unauthenticated. The entire presentation still works.
- **Live request returns to Demo Mode:** retry after checking `codex login`, `codex --version`, and `codex mcp-server --help`; current workflow state is intentionally retained.
- **Codex is installed outside `PATH`:** start the server with `NODEWITNESS_CODEX_COMMAND=/absolute/path/to/codex npm run dev`.
- **Verify the unavailable-command fallback:** start a second local instance with `NODEWITNESS_CODEX_COMMAND=codex-command-not-found npm run dev -- --port 3001`, open its health endpoint, and confirm it returns Demo Mode while the deterministic workflow remains usable.
- **PDF does not render inline:** use **Open in new tab** in the evidence viewer. Browser PDF support varies.
- **Stale presenter state:** click **Reset demo** or remove the `nodewitness.demo` key from browser local storage.
- **Production build fails after a Node upgrade:** use a supported Node 22 release, remove `node_modules`, and rerun `npm install`.

Never inspect, copy, serve, or commit `~/.codex/auth.json`. Authentication belongs to the separately operated Codex CLI, and `.gitignore` excludes local `.codex` state and secret-like files.

## Scope and roadmap

The MVP is deliberately one English demo workspace with bundled-source parsing and device-local state. P1 work, only when a real pilot requires it, includes authenticated workspaces, durable shared records, connector-backed source ingestion, configurable rule schemas, multi-client portfolios, role-based approvals, signed audit exports, and real external actions behind explicit policy controls.
