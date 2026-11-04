#!/usr/bin/env python3
"""MUSE HUB — status face (v1, 2026-11-01, DESK-1).
Read-only HTTP face for the hub: serves the runner's latest round, the
round log tail, and this box's chain count as JSON + a small live page.
The Directory deck reads /latest.json from here. Binds 0.0.0.0:8079
(Nikolai's tailnet + house LAN). No writes, no controls — a window,
not a door."""
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HUB = Path.home() / "muse-hub"
PORT = 8079


def latest():
    try:
        return json.loads((HUB / "latest.json").read_text())
    except Exception:  # noqa: BLE001
        return {}


def state():
    try:
        return json.loads((HUB / "state.json").read_text())
    except Exception:  # noqa: BLE001
        return {}


def chain_lines():
    try:
        return sum(1 for _ in open(Path.home() / "xchain" / "xchain.jsonl", "rb"))
    except Exception:  # noqa: BLE001
        return None


def log_tail(n=12):
    try:
        lines = (HUB / "rounds.log").read_text().splitlines()
        return lines[-n:]
    except Exception:  # noqa: BLE001
        return []


def payload():
    return {"hub": "muse-hub", "host": "nikolai", "now": int(time.time()),
            "nikolai_chain_records": chain_lines(), "state": state(),
            "latest_round": latest(), "rounds_log_tail": log_tail()}


PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>MUSE HUB — live</title><meta name=viewport content="width=device-width,initial-scale=1">
<style>body{background:#0b0e13;color:#dbe4f0;font-family:ui-monospace,Menlo,monospace;margin:0;padding:22px}
h1{font-size:19px;margin:0 0 2px}.sub{color:#7d8ea6;font-size:12px;margin-bottom:16px}
.card{background:#121722;border:1px solid #22304a;border-radius:10px;padding:14px 16px;margin-bottom:12px}
.big{font-size:26px;font-weight:700}.pass{color:#39d98a}.partial{color:#ffb02e}
table{border-collapse:collapse}td{padding:2px 14px 2px 0;font-size:13px}.k{color:#7d8ea6}
pre{white-space:pre-wrap;font-size:11.5px;color:#9fb2cc;margin:0}</style></head><body>
<h1>MUSE HUB</h1><div class=sub>the gadgets witness each other · rounds every 600s, in code · read-only face</div>
<div class=card id=round>loading…</div>
<div class=card><div class=k style="margin-bottom:6px">ROUNDS LOG</div><pre id=log></pre></div>
<script>
async function tick(){try{const d=await (await fetch('/latest.json')).json();
const r=d.latest_round||{};const cls=r.result==='PASS'?'pass':'partial';
document.getElementById('round').innerHTML=
 '<table><tr><td class=k>LAST ROUND</td><td>'+(r.ts||'—')+'</td></tr>'+
 '<tr><td class=k>RESULT</td><td class="big '+cls+'">'+(r.result||'—')+'</td></tr>'+
 '<tr><td class=k>PARTICIPANTS</td><td>'+((r.participants||[]).join(' · ')||'—')+'</td></tr>'+
 '<tr><td class=k>STAMPS</td><td>'+Object.entries(r.stamps||{}).map(([k,v])=>k+' '+v.slice(0,12)).join('<br>')+'</td></tr>'+
 '<tr><td class=k>VERIFY</td><td>'+Object.entries(r.verify||{}).map(([k,v])=>k+' '+(v?'PASS':'FAIL')).join(' · ')+'</td></tr>'+
 '<tr><td class=k>NIKOLAI CHAIN</td><td>'+(d.nikolai_chain_records??'—')+' records</td></tr>'+
 '<tr><td class=k>SOV (READ PEER)</td><td>'+(((d.state||{}).sov_head||'—').slice(0,16))+'</td></tr></table>';
document.getElementById('log').textContent=(d.rounds_log_tail||[]).join('\n');
}catch(e){document.getElementById('round').textContent='hub face unreachable: '+e}}
tick();setInterval(tick,10000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/latest.json"):
            body = json.dumps(payload(), indent=1).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/health"):
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()
