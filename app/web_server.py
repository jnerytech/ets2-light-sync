"""
app/web_server.py – Embedded HTTP dashboard for ETS2 Light Sync.

Starts a Flask server in a daemon thread so the app is reachable from any
device on the same local network.  Scan the QR code shown in the main window
to open the dashboard on your phone.

Endpoints
─────────
GET  /              → mobile-friendly HTML dashboard
GET  /api/status    → JSON snapshot of current state
GET  /api/logs      → JSON list of last 100 log lines
POST /api/start     → queue a start request (GUI thread processes it)
POST /api/stop      → queue a stop request  (GUI thread processes it)
"""

import logging
import socket
import threading

import flask
import flask.cli

from app.state import AppState

log = logging.getLogger(__name__)

DEFAULT_PORT = 8765

# Silence Flask's "Running on http://…" banner — we log it ourselves.
flask.cli.show_server_banner = lambda *_, **__: None  # type: ignore[assignment]
# Silence per-request werkzeug logs (GET /api/status every 3 s would be noisy).
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# ── HTML dashboard ────────────────────────────────────────────────────────────
# Self-contained: no CDN, no external fonts — works fully offline on LAN.

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETS2 Light Sync</title>
<style>
:root{
  --bg:#0f0f1a;--surface:#1a1a2e;--surface2:#252542;
  --text:#e0e0f0;--muted:#7a7a9a;
  --green:#4caf50;--yellow:#ffc107;--red:#f44336;--blue:#64b5f6;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  min-height:100vh;padding:16px;max-width:480px;margin:0 auto}
header{display:flex;align-items:center;gap:10px;margin-bottom:16px}
header h1{font-size:1.15rem;font-weight:600;flex:1}
#status-dot{width:12px;height:12px;border-radius:50%;background:var(--muted);
  flex-shrink:0;transition:background .4s}
#status-text{font-size:.8rem;color:var(--muted)}
.card{background:var(--surface);border-radius:12px;padding:16px;margin-bottom:12px}
#game-time{font-size:2.4rem;font-variant-numeric:tabular-nums;font-weight:700;
  letter-spacing:.06em;color:#fff;text-align:center;padding:8px 0 2px}
#game-day{text-align:center;color:var(--muted);font-size:.82rem;margin-bottom:10px}
.row{display:flex;align-items:center;padding:9px 0;
  border-bottom:1px solid var(--surface2);gap:8px}
.row:last-child{border-bottom:none}
.lbl{font-size:.82rem;color:var(--muted);min-width:96px}
.val{flex:1;font-weight:500;text-align:right}
.bar-track{flex:1;height:8px;background:var(--surface2);border-radius:4px;overflow:hidden;margin:0 8px}
.bar-fill{height:100%;border-radius:4px;
  background:linear-gradient(to right,#e65100,#fbc02d,#fff9c4);
  transition:width .5s ease}
.btn-row{display:flex;gap:12px;margin-bottom:12px}
button{flex:1;padding:14px;border:none;border-radius:10px;
  font-size:1rem;font-weight:600;cursor:pointer;
  transition:opacity .2s,transform .1s}
button:active:not(:disabled){transform:scale(.97)}
button:disabled{opacity:.3;cursor:default}
#btn-start{background:var(--green);color:#fff}
#btn-stop{background:var(--red);color:#fff}
details summary{cursor:pointer;color:var(--muted);font-size:.8rem;
  padding:6px 0;user-select:none;list-style:none}
details summary::before{content:"▸ ";transition:transform .2s}
details[open] summary::before{content:"▾ "}
#log-box{background:var(--surface);border-radius:8px;padding:10px;
  font-family:'Consolas','Menlo',monospace;font-size:.7rem;color:#9090b0;
  max-height:260px;overflow-y:auto;margin-top:6px;
  white-space:pre-wrap;word-break:break-all}
.dot-connected{background:var(--green)}
.dot-running{background:var(--yellow)}
.dot-waiting{background:var(--yellow)}
.dot-error{background:var(--red)}
.dot-stopped{background:var(--muted)}
</style>
</head>
<body>
<header>
  <h1>&#127748; ETS2 Light Sync</h1>
  <span id="status-dot"></span>
  <span id="status-text">&#8212;</span>
</header>

<div class="card">
  <div id="game-time">--:--</div>
  <div id="game-day">Dia --</div>
  <div class="row">
    <span class="lbl">&#128161; Brilho</span>
    <div class="bar-track"><div class="bar-fill" id="bbar" style="width:0%"></div></div>
    <span class="val" id="bval" style="min-width:46px">--</span>
  </div>
  <div class="row">
    <span class="lbl">&#127777; Temperatura</span>
    <span class="val" id="kval">--</span>
  </div>
  <div class="row">
    <span class="lbl">&#128205; Pos. X</span>
    <span class="val" id="truck-x">--</span>
  </div>
  <div class="row">
    <span class="lbl">&#128205; Pos. Z</span>
    <span class="val" id="truck-z">--</span>
  </div>
</div>

<div class="btn-row">
  <button id="btn-start" onclick="act('start')" disabled>&#9654; Iniciar</button>
  <button id="btn-stop"  onclick="act('stop')"  disabled>&#9209; Parar</button>
</div>

<details id="log-details">
  <summary>&#128221; Logs</summary>
  <div id="log-box">(abra para carregar)</div>
</details>

<script>
const LABELS={
  connected:'Jogo conectado',
  running:'Aguardando jogo',
  waiting:'Jogo desconectado',
  stopped:'Parado',
  error:'Erro \u2014 verifique configura\u00e7\u00f5es'
};

async function refresh(){
  try{
    const d=await(await fetch('/api/status')).json();
    document.getElementById('game-time').textContent=d.game_time;
    document.getElementById('game-day').textContent='Dia '+d.game_day;
    const pct=Math.round(d.brightness/255*100);
    document.getElementById('bbar').style.width=pct+'%';
    document.getElementById('bval').textContent=d.brightness+'/255';
    document.getElementById('kval').textContent=d.kelvin+' K';
    document.getElementById('truck-x').textContent=d.truck_x!=null?d.truck_x:'N/A';
    document.getElementById('truck-z').textContent=d.truck_z!=null?d.truck_z:'N/A';
    const dot=document.getElementById('status-dot');
    dot.className='dot-'+d.status;
    document.getElementById('status-text').textContent=LABELS[d.status]||d.status;
    const running=d.status!=='stopped'&&d.status!=='error';
    document.getElementById('btn-start').disabled=running;
    document.getElementById('btn-stop').disabled=!running;
  }catch(e){
    document.getElementById('status-text').textContent='Sem conex\u00e3o';
  }
}

async function refreshLogs(){
  const det=document.getElementById('log-details');
  if(!det.open)return;
  try{
    const d=await(await fetch('/api/logs')).json();
    const box=document.getElementById('log-box');
    box.textContent=d.logs.join('\\n')||'(sem logs)';
    box.scrollTop=box.scrollHeight;
  }catch(_){}
}

async function act(a){
  try{await fetch('/api/'+a,{method:'POST'});}catch(_){}
  setTimeout(refresh,600);
}

refresh();
setInterval(refresh,3000);
setInterval(refreshLogs,3000);
</script>
</body>
</html>"""


# ── WebServer ─────────────────────────────────────────────────────────────────

class WebServer:
    """Flask-based HTTP server running in a background daemon thread."""

    def __init__(self, state: AppState, port: int = DEFAULT_PORT) -> None:
        self._state = state
        self._port = port
        self._url = f"http://{_local_ip()}:{port}"
        self._app = self._build_app()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def url(self) -> str:
        return self._url

    def start(self) -> None:
        """Start the server in a daemon thread (non-blocking)."""
        t = threading.Thread(
            target=self._app.run,
            kwargs=dict(
                host="0.0.0.0",
                port=self._port,
                use_reloader=False,
                threaded=True,
            ),
            daemon=True,
            name="WebServer",
        )
        t.start()
        log.info("Web dashboard disponível em %s", self._url)

    # ── Flask routes ──────────────────────────────────────────────────────────

    def _build_app(self) -> flask.Flask:
        app = flask.Flask(__name__)
        state = self._state

        @app.route("/")
        def dashboard():
            return _DASHBOARD_HTML

        @app.route("/api/status")
        def api_status():
            return flask.jsonify(state.snapshot())

        @app.route("/api/logs")
        def api_logs():
            return flask.jsonify({"logs": state.get_logs(100)})

        @app.route("/api/start", methods=["POST"])
        def api_start():
            state.request_start()
            return flask.jsonify({"queued": True})

        @app.route("/api/stop", methods=["POST"])
        def api_stop():
            state.request_stop()
            return flask.jsonify({"queued": True})

        return app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _local_ip() -> str:
    """Return the primary LAN IP address of this machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            # Connect to an external address (no data sent) to find the
            # outgoing interface IP.
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
