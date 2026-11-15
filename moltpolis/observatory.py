"""molt-show observatory — a read-only web dashboard over the polis.

Serves the shared polity ledger plus every citizen's private molt-show
chain as one live page: the roster's energy curves, the guard market,
the treaty, the evolution lineage and the census verdict. No write path.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                      "sovereign-agent-zero"))
from sovzero.core import EventLog  # noqa: E402

PALETTE = ["#58a6ff", "#3fb950", "#d29922", "#db61a2", "#f85149", "#8b949e"]


def _short(h: str) -> str:
    return h[:12] if h else ""


def _load(run_dir: Path) -> dict:
    shared = EventLog(str(run_dir / "log.jsonl")).events
    shows = {}
    for p in sorted((run_dir / "shows").glob("*.jsonl")):
        shows[p.stem] = EventLog(str(p)).events
    return {"shared": shared, "shows": shows}


def _series(shared: list[dict], actor: str) -> list[int]:
    """Energy at each tick, re-derived from the shared ledger alone."""
    out, bal, last_tick = [], 0, 0
    for e in shared:
        p = e["payload"]
        if e["type"] == "ledger.credit" and p.get("to") == actor:
            bal += p["amount"]
        elif e["type"] == "ledger.debit" and p.get("to") == actor:
            bal -= p["amount"]
        elif e["type"] == "world.tick":
            out.append(bal)
            last_tick = p["tick"]
    return out


def _page(data: dict, run_dir: Path) -> bytes:
    shared = data["shared"]
    shows = data["shows"]
    cens = None
    cp = Path(run_dir) / "census-report.json"
    if cp.exists():
        cens = json.loads(cp.read_text())["summary"]

    gen = next((e for e in shared if e["type"] == "polity.genesis"), None)
    roster = [r["name"] for r in gen["payload"]["roster"]] if gen else []
    names = sorted(shows)
    treaty = next((e["payload"] for e in shared
                   if e["type"] == "polity.treaty.sealed"), None)
    quarantined = {e["payload"]["actor"] for e in shared
                   if e["type"] == "actor.quarantined"}
    offers = Counter(e["actor"].split(":")[1].split("@")[0] for e in shared
                     if e["type"] == "cap.offer")
    payouts = [e["payload"] for e in shared if e["type"] == "cap.payout"]
    types = Counter(e["type"] for e in shared)

    actors = {r["name"]: r["actor"] for r in gen["payload"]["roster"]} if gen else {}

    def polyline(name: str, color: str) -> str:
        s = _series(shared, actors.get(name, ""))
        if len(s) < 2:
            return ""
        mx = max(s) or 1
        pts = " ".join(f"{i * 640 / (len(s) - 1):.1f},"
                       f"{110 - 100 * v / mx:.1f}" for i, v in enumerate(s))
        return (f'<polyline fill="none" stroke="{color}" stroke-width="2" '
                f'points="{pts}"/>')
        if len(s) < 2:
            return ""
        mx = max(s) or 1
        pts = " ".join(f"{i * 640 / (len(s) - 1):.1f},"
                       f"{110 - 100 * v / mx:.1f}" for i, v in enumerate(s))
        return (f'<polyline fill="none" stroke="{color}" stroke-width="2" '
                f'points="{pts}"/>')

    curves = "".join(polyline(n, PALETTE[i % len(PALETTE)])
                     for i, n in enumerate(names))
    legend = " ".join(
        f'<span style="color:{PALETTE[i % len(PALETTE)]}">■ {n}</span>'
        for i, n in enumerate(names))

    rev_rows = ""
    for n in names:
        for e in shows[n]:
            if e["type"] == "reactor.revision" and e["payload"].get("gen", 0):
                rev_rows += (f"<tr><td>{n}</td><td>gen {e['payload']['gen']}"
                             f"</td><td>#{e['seq']}</td>"
                             f"<td>{e['payload'].get('reason', '')[:70]}"
                             f"</td></tr>")

    type_rows = "".join(f"<tr><td>{t}</td><td>{c}</td></tr>"
                        for t, c in sorted(types.items(), key=lambda kv: -kv[1]))

    census_html = (f'<div class="card">census: <b style="color:'
                   f'{"#3fb950" if cens["verdict"] == "PASS" else "#f85149"}">'
                   f'{cens["verdict"]}</b> — {len(cens["violations"])} violations'
                   f" across {cens['total_events']} shared events</div>"
                   if cens else '<div class="card">census: not yet run</div>')

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>molt-polis observatory</title><meta http-equiv="refresh" content="5">
<style>
 body{{background:#0d1117;color:#c9d1d9;font:14px/1.5 system-ui;margin:0;padding:24px}}
 h1{{font-size:20px}} h2{{font-size:15px;color:#58a6ff;margin-top:28px}}
 .card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;margin:10px 0}}
 .k{{color:#8b949e}} table{{border-collapse:collapse;margin-top:8px;width:100%}}
 td,th{{border:1px solid #30363d;padding:4px 10px;font-size:13px}}
 svg{{background:#010409;border-radius:6px}}
</style></head><body>
<h1>molt-polis — the Living Commonwealth</h1>
<div class="card">
 <span class="k">shared ledger:</span> {len(shared)} events |
 <span class="k">private chains:</span> {len(shows)} |
 <span class="k">treaty:</span> {"sealed, quorum " + str(treaty["quorum"]) if treaty else "not sealed"} |
 <span class="k">quarantined:</span> {", ".join(q.split(":")[1].split("@")[0] for q in quarantined) or "none"}
</div>
{census_html}
<h2>Per-citizen energy (re-derived from the shared ledger)</h2>
<svg width="660" height="120" role="img">{curves}</svg>
<div>{legend}</div>
<h2>The guard market</h2>
<div class="card">
 offers by seller: {", ".join(f"{k} ×{v}" for k, v in offers.most_common())} |
 payouts: {len(payouts)} —
 {" ".join(f"{p['insurer'].split(':')[1].split('@')[0]} paid {p['buyer'].split(':')[1].split('@')[0]} {p['amount']}" for p in payouts) or "none yet"}
</div>
<h2>Evolution lineage (signed revisions)</h2>
<table><tr><th>citizen</th><th>gen</th><th>show seq</th><th>reason</th></tr>
{rev_rows or '<tr><td colspan="4">no adoptions yet</td></tr>'}</table>
<h2>Shared event census</h2>
<table><tr><th>type</th><th>count</th></tr>{type_rows}</table>
</body></html>"""
    return html.encode()


class Handler(BaseHTTPRequestHandler):
    run_dir: Path = None

    def _json(self, code: int, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            data = _load(Path(self.run_dir))
            if self.path.startswith("/api/summary"):
                shared = data["shared"]
                treaty = next((e["payload"] for e in shared
                               if e["type"] == "polity.treaty.sealed"), None)
                balances: dict[str, int] = {}
                for e in shared:
                    if e["type"] == "ledger.credit":
                        balances[e["payload"]["to"]] = \
                            balances.get(e["payload"]["to"], 0) + \
                            e["payload"]["amount"]
                    elif e["type"] == "ledger.debit":
                        balances[e["payload"]["to"]] = \
                            balances.get(e["payload"]["to"], 0) - \
                            e["payload"]["amount"]
                cens = None
                cp = Path(self.run_dir) / "census-report.json"
                if cp.exists():
                    cens = json.loads(cp.read_text())["summary"]["verdict"]
                self._json(200, {
                    "events": len(shared),
                    "private_chains": sorted(data["shows"]),
                    "treaty": treaty,
                    "balances": balances,
                    "census": cens,
                })
            elif self.path.startswith("/api/events"):
                self._json(200, data["shared"][-200:])
            else:
                body = _page(data, Path(self.run_dir))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except Exception as e:  # noqa: BLE001
            self.send_error(500, str(e))

    def log_message(self, *a):  # silence request logging
        pass


def serve(run_dir: str, port: int):
    Handler.run_dir = Path(run_dir).resolve()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"molt-polis observatory serving {Handler.run_dir} on :{port}",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "runs/default"
    p = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("PORT", "8600"))
    serve(d, p)
