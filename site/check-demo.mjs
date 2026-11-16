#!/usr/bin/env node
// Check the live demo video against site/src/demo.json: HTTP 200, video/mp4, byte size, range requests
// (needed for seeking), and the SHA-256 of the full body. Usage: node site/check-demo.mjs
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
const demo = JSON.parse(readFileSync(new URL("src/demo.json", import.meta.url), "utf8"));
const fail = [];
const head = await fetch(demo.url, { method: "HEAD" });
if (head.status !== 200) fail.push(`HEAD ${head.status}`);
if (!(head.headers.get("content-type") || "").startsWith("video/mp4")) fail.push(`content-type ${head.headers.get("content-type")}`);
const range = await fetch(demo.url, { headers: { Range: "bytes=0-1023" } });
if (range.status !== 206) fail.push(`range request returned ${range.status}, not 206`);
await range.arrayBuffer();
const body = Buffer.from(await (await fetch(demo.url)).arrayBuffer());
if (body.length !== demo.bytes) fail.push(`size ${body.length}, demo.json says ${demo.bytes}`);
const sha = createHash("sha256").update(body).digest("hex");
if (sha !== demo.sha256) fail.push(`sha256 ${sha.slice(0, 12)}… differs from demo.json`);
console.log(`${demo.url}\n  ${head.status} ${head.headers.get("content-type")} · ${body.length} bytes · range ${range.status} · cache-control ${head.headers.get("cache-control")}`);
if (fail.length) { console.error("FAILED:\n  " + fail.join("\n  ")); process.exit(1); }
console.log("  sha256 matches demo.json");
