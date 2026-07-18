import { NextResponse } from "next/server";
import { runCodex } from "@/lib/codex-mcp";
import { buildWorkflow, type RuntimeInput, type RuntimeOperation } from "@/lib/workflow";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json() as Record<string, unknown>;
    if (body.version !== 1 && body.version !== 2) {
      return NextResponse.json({ ok: false, mode: "demo", error: "Invalid policy version" }, { status: 400 });
    }
    const operation: RuntimeOperation = body.operation === undefined ? "assessment" : body.operation as RuntimeOperation;
    if (!["workflow", "assessment", "correction"].includes(operation)) {
      return NextResponse.json({ ok: false, mode: "demo", error: "Invalid runtime operation" }, { status: 400 });
    }

    const input: RuntimeInput = {};
    if (operation === "workflow") {
      if (typeof body.description !== "string" || !body.description.trim() || body.description.length > 2000) {
        return NextResponse.json({ ok: false, mode: "demo", error: "Invalid workflow description" }, { status: 400 });
      }
      input.description = body.description;
    }
    if (operation === "correction") {
      const validNodeIds = new Set(buildWorkflow(body.version).map((node) => node.id));
      if (
        typeof body.nodeId !== "string" || !validNodeIds.has(body.nodeId) ||
        typeof body.instruction !== "string" || !body.instruction.trim() || body.instruction.length > 1000 ||
        !Array.isArray(body.originalOutputs) || !body.originalOutputs.every((item) => typeof item === "string")
      ) {
        return NextResponse.json({ ok: false, mode: "demo", error: "Invalid correction request" }, { status: 400 });
      }
      input.nodeId = body.nodeId;
      input.instruction = body.instruction;
      input.originalOutputs = body.originalOutputs;
    }

    const { result, threadId } = await runCodex(operation, body.version, input);
    const workflow = operation === "workflow" ? buildWorkflow(body.version).map((node) => ({
      ...node,
      data: {
        ...node.data,
        runtimeMode: "Live Codex MCP",
        promptVersion: result.metadata.promptVersion,
        threadId,
        history: ["Live Codex workflow validation", ...node.data.history],
      },
    })) : undefined;
    return NextResponse.json({ ok: true, mode: "live", threadId, ...result, workflow });
  } catch (error) {
    console.error("NodeWitness Live Codex analysis failed:", error instanceof Error ? error.message : "Unknown error");
    return NextResponse.json({ ok: false, mode: "demo", error: "Live analysis unavailable; deterministic state retained." }, { status: 503 });
  }
}
