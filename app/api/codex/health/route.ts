import { NextResponse } from "next/server";
import { codexHealth } from "@/lib/codex-mcp";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const health = await codexHealth();
    return NextResponse.json({ ...health, mode: health.ok ? "live" : "demo" }, { status: health.ok ? 200 : 503 });
  } catch {
    return NextResponse.json({ ok: false, mode: "demo" }, { status: 503 });
  }
}
