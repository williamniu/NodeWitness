import { execFile } from "node:child_process";
import { randomBytes, timingSafeEqual } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const PYTHON = process.env.NW_FINANCE_PYTHON || "python3";
const COOKIE = "nw-local-review";

function bridge(payload: object): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const child = execFile(PYTHON, ["-m", "finance_runtime.cli"], { cwd: process.cwd(), timeout: 45_000, maxBuffer: 5 * 1024 * 1024 }, (error, stdout) => {
      try {
        const response = JSON.parse(stdout);
        if (!response.ok) reject(new Error(response.error || "Local review failed"));
        else if (error) reject(error);
        else resolve(response.result);
      } catch (parseError) { reject(parseError); }
    });
    child.stdin?.end(JSON.stringify(payload));
  });
}

function localHost(request: NextRequest) {
  const local = /^(127\.0\.0\.1|localhost|\[::1\])(?::\d{1,5})?$/;
  const host = request.headers.get("host") || "";
  const forwarded = request.headers.get("x-forwarded-host");
  return local.test(host) && (!forwarded || local.test(forwarded));
}

export async function GET(request: NextRequest) {
  if (!localHost(request)) return NextResponse.json({ error: "This review is available on the local machine only." }, { status: 403 });
  try {
    const token = request.cookies.get(COOKIE)?.value || randomBytes(32).toString("hex");
    const runId = request.nextUrl.searchParams.get("run_id") || undefined;
    if (runId && !/^[A-Za-z0-9_-]{1,100}$/.test(runId)) throw new Error("Invalid run ID");
    const format = request.nextUrl.searchParams.get("download");
    const source = request.nextUrl.searchParams.get("source");
    if (source) return NextResponse.json(await bridge({ operation: "source", run_id: runId, file: source, record_id: request.nextUrl.searchParams.get("record_id") }), { headers: { "Cache-Control": "no-store" } });
    if (format) {
      const result = await bridge({ operation: "export", run_id: runId, format });
      const filename = String(result.path);
      const allowedRoot = path.resolve(process.cwd(), "outputs/nw003/exports") + path.sep;
      if (!filename.startsWith(allowedRoot)) throw new Error("Invalid export path");
      return new NextResponse(await readFile(/* turbopackIgnore: true */ filename), { headers: { "Content-Type": format === "pdf" ? "application/pdf" : format === "json" ? "application/json" : "text/markdown; charset=utf-8", "Content-Disposition": `attachment; filename="${result.filename}"`, "Cache-Control": "no-store" } });
    }
    const state = await bridge({ operation: "state", run_id: runId });
    const response = NextResponse.json({ ...state, csrf: token }, { headers: { "Cache-Control": "no-store" } });
    response.cookies.set(COOKIE, token, { httpOnly: true, sameSite: "strict", path: "/" });
    return response;
  } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "Local review unavailable" }, { status: 400 }); }
}

export async function POST(request: NextRequest) {
  const cookie = request.cookies.get(COOKIE)?.value;
  const token = request.headers.get("x-nw-local-token");
  const origin = request.headers.get("origin");
  const sameToken = cookie && token && /^[a-f0-9]{64}$/.test(cookie) && cookie.length === token.length && timingSafeEqual(Buffer.from(cookie), Buffer.from(token));
  const expectedOrigin = `${request.nextUrl.protocol}//${request.headers.get("x-forwarded-host") || request.headers.get("host")}`;
  if (!localHost(request) || origin !== expectedOrigin || !sameToken) {
    return NextResponse.json({ error: "Reload this local page before making an operator decision." }, { status: 403 });
  }
  try {
    const text = await request.text();
    if (text.length > 12_000) throw new Error("Request too large");
    const body = JSON.parse(text);
    if (!["start", "decide", "source_update", "correct_quote", "handoff"].includes(body.operation)) throw new Error("Operation not available to the local operator");
    return NextResponse.json(await bridge(body));
  } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "Operator request failed" }, { status: 409 }); }
}
