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
      <hr />
      <h2>New Test (Natural Language)</h2>
      <div class=\"row\">\n        <input id=\"url\" placeholder=\"https://example.com or data:...\" style=\"width: 100%\"/>\n      </div>
      <div class=\"row\">\n        <textarea id=\"stepsText\" placeholder=\"One step per line, e.g.\\nclick Login\\ntype hello\\npress Enter\"></textarea>\n      </div>
      <div class=\"row\">\n        <button id=\"nlRunBtn\">Run NL Test</button>\n      </div>
      <hr />
      <h2>Contract Tests (CONTRACT.md)</h2>
      <div class=\"row\">\n        <input id=\"ctTestId\" placeholder=\"test id (e.g. test_login)\" style=\"width: 100%\"/>\n      </div>
      <div class=\"row\">\n        <input id=\"ctName\" placeholder=\"Test name\" style=\"width: 100%\"/>\n      </div>
      <div class=\"row\">\n        <input id=\"ctAppUrl\" placeholder=\"app_base_url (e.g. https://app.example.com)\" style=\"width: 100%\"/>\n      </div>
      <div class=\"row\">\n        <textarea id=\"ctStepsText\" placeholder=\"One step per line, e.g.\\nOpen the login page.\\nClick Login.\"></textarea>\n      </div>
      <div class=\"row\">\n        <button id=\"ctCreateBtn\">Create Contract Test</button>\n        <button id=\"ctLoadBtn\">Load Test</button>\n        <button id=\"ctRunBtn\">Run Contract Test</button>\n      </div>
      <div class=\"row\">\n        <h3>Contract Test JSON</h3>\n        <pre id=\"ctTestJson\"></pre>\n      </div>
      <div class=\"row\">\n        <h3>Recent Runs</h3>\n        <button id=\"refreshRuns\">Refresh Runs</button>\n        <pre id=\"runs\"></pre>\n      </div>
      <div class=\"row\">\n        <h3>Artifacts</h3>\n        <div id=\"artifacts\"></div>\n        <div id=\"shot\"></div>\n      </div>
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
      <div class="row">
        <h3>Run Details (contract view)</h3>
        <input id="runDetailsId" placeholder="run id" style="width: 60%" />
        <button id="runDetailsBtn">Load Details</button>
        <pre id="runDetails"></pre>
      </div>

      <script>
        const runBtn = document.getElementById('runBtn');
        const nlRunBtn = document.getElementById('nlRunBtn');
        const specEl = document.getElementById('spec');
        const urlEl = document.getElementById('url');
        const stepsEl = document.getElementById('stepsText');
        const jobEl = document.getElementById('job');
        const runEl = document.getElementById('run');
        const statusEl = document.getElementById('status');
        const statsEl = document.getElementById('stats');
        const runsEl = document.getElementById('runs');
        const artifactsEl = document.getElementById('artifacts');
        const shotEl = document.getElementById('shot');
        const refreshRunsBtn = document.getElementById('refreshRuns');
        const ctTestIdEl = document.getElementById('ctTestId');
        const ctNameEl = document.getElementById('ctName');
        const ctAppUrlEl = document.getElementById('ctAppUrl');
        const ctStepsTextEl = document.getElementById('ctStepsText');
        const ctCreateBtn = document.getElementById('ctCreateBtn');
        const ctLoadBtn = document.getElementById('ctLoadBtn');
        const ctRunBtn = document.getElementById('ctRunBtn');
        const ctTestJsonEl = document.getElementById('ctTestJson');
        const runDetailsIdEl = document.getElementById('runDetailsId');
        const runDetailsBtn = document.getElementById('runDetailsBtn');
        const runDetailsEl = document.getElementById('runDetails');

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

        async function createContractTest() {
          if (!ctTestIdEl) return;
          const id = (ctTestIdEl.value || '').trim() || `test_${Date.now()}`;
          const name = (ctNameEl && ctNameEl.value.trim()) || id;
          const appUrl = ctAppUrlEl ? ctAppUrlEl.value.trim() : '';
          const stepsText = ctStepsTextEl ? ctStepsTextEl.value : '';
          const payload = {
            id,
            name,
            app_base_url: appUrl || undefined,
            stepsText: stepsText,
          };
          try {
            const resp = await postJSON('/tests', payload);
            ctTestIdEl.value = id;
            if (ctTestJsonEl) {
              try {
                const t = await getJSON(`/tests/${id}`);
                ctTestJsonEl.textContent = JSON.stringify(t.test || t, null, 2);
              } catch (e) {
                ctTestJsonEl.textContent = JSON.stringify(resp, null, 2);
              }
            }
          } catch (e) {
            alert('Failed to create test: ' + e.message);
          }
        }

        async function loadContractTest() {
          if (!ctTestIdEl || !ctTestJsonEl) return;
          const id = (ctTestIdEl.value || '').trim();
          if (!id) return;
          try {
            const t = await getJSON(`/tests/${id}`);
            ctTestJsonEl.textContent = JSON.stringify(t.test || t, null, 2);
          } catch (e) {
            alert('Failed to load test: ' + e.message);
          }
        }

        async function runContractTest() {
          if (!ctTestIdEl) return;
          const id = (ctTestIdEl.value || '').trim();
          if (!id) return;
          try {
            const resp = await postJSON(`/tests/${id}/runs`, { mode: 'live' });
            const rid = resp.runId || resp.run_id;
            if (rid) {
              runEl.textContent = rid;
            }
          } catch (e) {
            alert('Failed to run test: ' + e.message);
          }
        }

        async function loadRunDetails() {
          if (!runDetailsIdEl || !runDetailsEl) return;
          const rid = (runDetailsIdEl.value || '').trim();
          if (!rid) return;
          try {
            const data = await getJSON(`/runs/${rid}/details`);
            runDetailsEl.textContent = JSON.stringify(data, null, 2);
          } catch (e) {
            alert('Failed to load run details: ' + e.message);
          }
        }

        async function poll() {
          if (!jobId) return;
          try {
            const data = await getJSON(`/runs/${jobId}`);
            jobEl.textContent = data.jobId || '';
            runEl.textContent = data.runId || '';
            statusEl.textContent = data.status || '';
            statsEl.textContent = JSON.stringify(data.stats || {}, null, 2);
            if (data.status === 'finished' && data.runId) {
              try {
                const arts = await getJSON(`/runs/${data.runId}/artifacts`);
                artifactsEl.textContent = JSON.stringify(arts.items || [], null, 2);
                const hasShot = (arts.items || []).find(it => it.name === 'screenshot');
                if (hasShot) {
                  shotEl.innerHTML = `<a href="/runs/${data.runId}/artifacts/screenshot" target="_blank">Open Screenshot</a><br/><img src="/runs/${data.runId}/artifacts/screenshot" alt="screenshot" style="max-width: 100%; border: 1px solid #ddd;"/>`;
                }
              } catch (e) { console.error('artifacts error', e); }
            }
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
        nlRunBtn.addEventListener('click', async () => {
          try {
            const url = urlEl.value;
            const stepsText = stepsEl.value;
            const resp = await postJSON('/tests/nl-run', { url, stepsText });
            jobId = resp.jobId;
            jobEl.textContent = jobId;
            runEl.textContent = '';
            statusEl.textContent = 'queued';
            statsEl.textContent = '';
          } catch (e) { alert('Failed: ' + e.message); }
        });
        if (ctCreateBtn) ctCreateBtn.addEventListener('click', createContractTest);
        if (ctLoadBtn) ctLoadBtn.addEventListener('click', loadContractTest);
        if (ctRunBtn) ctRunBtn.addEventListener('click', runContractTest);
        if (runDetailsBtn) runDetailsBtn.addEventListener('click', loadRunDetails);

        async function refreshRuns() {
          try {
            const data = await getJSON('/runs?limit=10');
            runsEl.textContent = JSON.stringify(data, null, 2);
          } catch (e) { console.error('refreshRuns failed', e); }
        }
        refreshRunsBtn.addEventListener('click', refreshRuns);

        setInterval(poll, 2000);
      </script>
    </body>
    </html>
    "+"""
    return HTMLResponse(content=html, status_code=200)
