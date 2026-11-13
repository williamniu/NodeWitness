"""Read-only live dashboard for a terminal-task experiment.

    python3 scripts/live_dashboard.py [--experiment d5] [--models qwen36 qwen38] [--seeds 1001 ... 1005] [--port 8787]

Open http://127.0.0.1:8787. It never writes to the run: it reads finished trial records from
outputs/terminal/trials/, and
follows Docker's event stream to show every command the agent runs in its container, as it runs.
Finished trials keep their full step-by-step record (with outputs) in the trial JSON.
"""

import argparse
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRIALS = ROOT / "outputs/terminal/trials"
TASKS = sorted(p.name for p in (ROOT / "terminal_env/tasks").iterdir() if (p / "task.py").exists())
SEEN = {}  # container name -> {"started": t, "commands": [(t, cmd)]}
LOCK = threading.Lock()


def docker(*args):
    try:
        out = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=5)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


AGENT_PREFIX = "timeout -k 2 20 bash -c "


def sampler():
    """Follow Docker's event stream: every `docker exec` into a task container is one event that
    carries the full command, so no command is missed however fast it runs. Read-only."""
    args = ["docker", "events", "--since", "30m", "--format", "{{json .}}",
            "--filter", "type=container", "--filter", "label=nodewitness.task=terminal"]
    while True:
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                name = event.get("Actor", {}).get("Attributes", {}).get("name", "")
                action = event.get("Action", "")
                when = event.get("time", time.time())
                with LOCK:
                    if action == "start":
                        SEEN[name] = {"started": when, "commands": [], "ended": None}
                    entry = SEEN.setdefault(name, {"started": when, "commands": [], "ended": None})
                    if action.startswith("exec_create: " + AGENT_PREFIX) and name.startswith("nwterm-agent-"):
                        entry["commands"].append((when, action[len("exec_create: " + AGENT_PREFIX):][:400]))
                        entry["commands"] = entry["commands"][-200:]
                    elif action in ("die", "destroy"):
                        entry["ended"] = when
                    for old in [n for n, e in SEEN.items() if e["ended"] and time.time() - e["ended"] > 3600]:
                        del SEEN[old]
        except OSError:
            pass
        time.sleep(2)
        args[3] = "1m"


def status(cfg):
    trials = []
    for path in sorted(TRIALS.glob("*.json")):
        try:
            r = json.loads(path.read_text())
        except ValueError:
            continue
        if r.get("experiment_id") != cfg.experiment:
            continue
        trials.append({"agent": r["agent"], "task": r["task"], "seed": r["seed"], "status": r["status"],
                       "steps": len(r.get("steps", [])), "seconds": r.get("duration_seconds"),
                       "created_at": r.get("created_at"), "run_id": r["run_id"],
                       "failed_checks": [k for k, v in r.get("verifier", {}).get("checks", {}).items() if not v.get("passed")],
                       "commit": r.get("provenance", {}).get("git_commit", "")[:7],
                       "verifier": r.get("verifier", {}).get("version")})
    done = {(t["agent"], t["task"], t["seed"]) for t in trials}
    order = [(m, t, s) for m in cfg.models for s in cfg.seeds for t in TASKS]  # suite order
    pending = [x for x in order if x not in done]
    current = pending[0] if pending else None
    durations = {m: [t["seconds"] for t in trials if t["agent"] == m and t["seconds"]] for m in cfg.models}
    guess = {m: (sum(v) / len(v) if v else 600.0) for m, v in durations.items()}
    eta = sum(guess[m] for m, _, _ in pending)
    with LOCK:
        live = [{"container": n, "running_seconds": round(time.time() - e["started"]), "count": len(e["commands"]),
                 "commands": [{"ago": round(time.time() - t), "cmd": c} for t, c in e["commands"][-15:]][::-1]}
                for n, e in SEEN.items() if n.startswith("nwterm-agent-") and not e["ended"]]
    return {"experiment": cfg.experiment, "models": cfg.models, "tasks": TASKS, "seeds": cfg.seeds,
            "total": len(order), "finished": len(done & set(order)), "current": current,
            "eta_seconds": round(eta), "trials": trials, "live": live, "generated_at": time.strftime("%H:%M:%S")}


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>D5 live run</title>
<style>
:root{--bg:#fafaf8;--fg:#1b1b19;--mut:#6b6a65;--card:#fff;--bd:#e3e2dc;--ok:#e6f4e0;--okt:#27500a;--no:#fbe9e8;--not:#791f1f;--er:#fdf1d8;--ert:#633806;--go:#e4effa;--got:#0c447c;--q:#f1f0eb}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#efeee9;--mut:#a3a29b;--card:#1d1d1b;--bd:#33332f;--ok:#1f3310;--okt:#c0dd97;--no:#3d1515;--not:#f7c1c1;--er:#3a2a0c;--ert:#fac775;--go:#0c2a48;--got:#b5d4f4;--q:#262624}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,sans-serif}
h1{font-size:18px;font-weight:500;margin:0 0 4px} .mut{color:var(--mut);font-size:12px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:12px 0}
.k{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 12px}.k b{display:block;font-size:22px;font-weight:500}
.grid{display:grid;grid-template-columns:130px repeat(var(--n),minmax(0,1fr));gap:4px;font-size:12px;align-items:center;margin-bottom:14px}
.c{height:28px;border-radius:5px;display:flex;align-items:center;justify-content:center;cursor:default}
.passed{background:var(--ok);color:var(--okt)}.failed{background:var(--no);color:var(--not)}.error{background:var(--er);color:var(--ert)}
.now{background:var(--go);color:var(--got);outline:2px solid var(--got)}.queued{background:var(--q);color:var(--mut)}
.panel{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 12px;margin-bottom:12px}
pre{margin:0;white-space:pre-wrap;word-break:break-all;font:12px/1.5 ui-monospace,Menlo,monospace}
table{border-collapse:collapse;width:100%;font-size:12px}td,th{text-align:left;padding:4px 6px;border-bottom:1px solid var(--bd);vertical-align:top}th{font-weight:500;color:var(--mut)}
</style></head><body>
<h1>Live run: <span id="exp"></span></h1><div class="mut">Read-only. Refreshes every 5 s. Last update <span id="ts"></span></div>
<div class="kpis" id="kpis"></div>
<div id="grids"></div>
<div class="panel"><b style="font-weight:500">Agent container right now</b> <span class="mut">(every command, from Docker's event stream; newest first)</span><div id="live" style="margin-top:6px"></div></div>
<div class="panel"><b style="font-weight:500">Finished trials</b><table id="tbl"></table></div>
<script>
const fmt=s=>s>=3600?Math.floor(s/3600)+"h "+Math.round(s%3600/60)+"m":Math.round(s/60)+"m";
const esc=s=>String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
async function tick(){
 let d; try{d=await (await fetch("/api/status")).json()}catch(e){return}
 exp.textContent=d.experiment; ts.textContent=d.generated_at;
 const by={}; d.trials.forEach(t=>by[t.agent+"|"+t.task+"|"+t.seed]=t);
 let k=`<div class="k"><span class="mut">Finished</span><b>${d.finished} / ${d.total}</b></div><div class="k"><span class="mut">ETA (rough)</span><b>${d.current?fmt(d.eta_seconds):"done"}</b></div>`;
 d.models.forEach(m=>{const r=d.trials.filter(t=>t.agent==m);const p=r.filter(t=>t.status=="passed").length;const e=r.filter(t=>t.status=="error").length;
  k+=`<div class="k"><span class="mut">${m} passed</span><b>${p} / ${r.length}</b>${e?`<span class="mut">${e} error</span>`:""}</div>`});
 kpis.innerHTML=k;
 let g="";
 d.models.forEach(m=>{g+=`<div class="grid" style="--n:${d.seeds.length}"><div style="font-weight:500">${m}</div>`+d.seeds.map(s=>`<div class="mut" style="text-align:center">${s}</div>`).join("");
  d.tasks.forEach(t=>{g+=`<div class="mut">${t}</div>`;d.seeds.forEach(s=>{const x=by[m+"|"+t+"|"+s];const cur=d.current&&d.current[0]==m&&d.current[1]==t&&d.current[2]==s;
   const cls=x?x.status:(cur?"now":"queued");const tip=x?`${x.steps} steps, ${Math.round(x.seconds)}s${x.failed_checks.length?"; failed: "+x.failed_checks.join(", "):""}`:"";
   g+=`<div class="c ${cls}" title="${esc(tip)}">${x?(x.status=="passed"?"pass":x.status=="failed"?"fail":"error"):(cur?"now":"")}</div>`})});g+="</div>"});
 grids.innerHTML=g;
 live.innerHTML=d.live.length?d.live.map(l=>`<div class="mut">${esc(l.container)} running ${fmt(l.running_seconds)}, ${l.count} / 30 tool calls${d.current?`, on ${d.current.join(" / ")}`:""}</div><pre>${l.commands.length?l.commands.map(c=>`${String(c.ago).padStart(4)}s ago  ${esc(c.cmd)}`).join("\n"):"(no command caught yet)"}</pre>`).join(""):"<span class='mut'>No agent container running.</span>";
 tbl.innerHTML="<tr><th>Model</th><th>Task</th><th>Seed</th><th>Result</th><th>Steps</th><th>Time</th><th>Failed checks</th></tr>"+d.trials.slice().sort((a,b)=>(b.created_at||"").localeCompare(a.created_at||"")).map(t=>`<tr><td>${t.agent}</td><td>${t.task}</td><td>${t.seed}</td><td>${t.status}</td><td>${t.steps}</td><td>${Math.round(t.seconds)}s</td><td>${esc(t.failed_checks.join(", "))}</td></tr>`).join("");
}
tick(); setInterval(tick,5000);
</script></body></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment", default="d5")
    parser.add_argument("--models", nargs="+", default=["qwen36", "qwen38"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1001, 1002, 1003, 1004, 1005])
    parser.add_argument("--port", type=int, default=8787)
    cfg = parser.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/api/status":
                body, kind = json.dumps(status(cfg)).encode(), "application/json"
            elif self.path in ("/", "/index.html"):
                body, kind = PAGE.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    threading.Thread(target=sampler, daemon=True).start()
    print("Dashboard on http://127.0.0.1:%d (experiment %s)" % (cfg.port, cfg.experiment), flush=True)
    ThreadingHTTPServer(("127.0.0.1", cfg.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
