from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/")
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <title>Kaizen Portal</title>
      <style>
        body { font-family: system-ui, Arial, sans-serif; margin: 2rem; }
        textarea { width: 100%; height: 180px; }
        pre { background: #f5f5f5; padding: 1rem; }
        .row { margin: 0.5rem 0; }
        button { padding: 0.5rem 0.8rem; }
      </style>
    </head>
    <body>
      <h1>Kaizen Portal</h1>
      <div class="row">
        <p>Paste a suite spec JSON, then click Run. The runner will pick it up. This page polls status every 2s.</p>
      </div>
      <div class="row">
        <textarea id="spec">{
  "id": "suite-portal",
  "suite": "demo",
  "name": "sample",
  "steps": [
    {"text": "press Enter"}
  ]
}</textarea>
      </div>
      <div class="row">
        <button id="runBtn">Run Suite</button>
      </div>
      <div class="row">
        <div>Job: <span id="job"></span></div>
        <div>Run: <span id="run"></span></div>
        <div>Status: <span id="status"></span></div>
      </div>
      <div class="row">
        <h3>Stats</h3>
        <pre id="stats"></pre>
      </div>

      <script>
        const runBtn = document.getElementById('runBtn');
        const specEl = document.getElementById('spec');
        const jobEl = document.getElementById('job');
        const runEl = document.getElementById('run');
        const statusEl = document.getElementById('status');
        const statsEl = document.getElementById('stats');

        let jobId = null;

        async function postJSON(url, data) {
          const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return await r.json();
        }
        async function getJSON(url) {
          const r = await fetch(url);
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return await r.json();
        }

        async function poll() {
          if (!jobId) return;
          try {
            const data = await getJSON(`/runs/${jobId}`);
            jobEl.textContent = data.jobId || '';
            runEl.textContent = data.runId || '';
            statusEl.textContent = data.status || '';
            statsEl.textContent = JSON.stringify(data.stats || {}, null, 2);
          } catch (e) { console.error('poll error', e); }
        }

        runBtn.addEventListener('click', async () => {
          try {
            const spec = JSON.parse(specEl.value);
            const resp = await postJSON('/runs', { spec, mode: 'snapshot' });
            jobId = resp.jobId;
            jobEl.textContent = jobId;
            runEl.textContent = '';
            statusEl.textContent = 'queued';
            statsEl.textContent = '';
          } catch (e) { alert('Failed: ' + e.message); }
        });

        setInterval(poll, 2000);
      </script>
    </body>
    </html>
    "+"""
    return HTMLResponse(content=html, status_code=200)
