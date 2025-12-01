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
        pre { background: #f5f5f5; padding: 1rem; overflow-x: auto; }
        .row { margin: 0.5rem 0; }
        button { padding: 0.4rem 0.7rem; cursor: pointer; }
        .action-row { margin: 0.25rem 0; padding: 0.4rem 0.2rem; border-bottom: 1px solid #eee; }
        .action-header { font-size: 0.9rem; margin-bottom: 0.25rem; }
        .action-status-ok { color: #2b8a3e; }
        .action-status-failed { color: #d9480f; }
        .action-screenshots img { max-width: 220px; border: 1px solid #ddd; margin-right: 0.5rem; margin-top: 0.25rem; cursor: pointer; }
        .action-controls { margin-top: 0.25rem; }
        .action-pagebrain { font-size: 0.8rem; color: #555; margin-top: 0.1rem; }
        .ann-btn { margin-right: 0.4rem; border-radius: 3px; border: 1px solid #ccc; background: #f5f5f5; }
        .ann-btn.selected { font-weight: 600; border-color: #333; background: #e6ffe6; }
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
        <h3>Run Actions</h3>
        <div id="runActions"></div>
      </div>
      <div id="shotOverlay" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.8); z-index:9999; align-items:center; justify-content:center;">
        <img id="shotOverlayImg" src="" alt="screenshot" style="max-width:90%; max-height:90%; border:2px solid #fff; box-shadow:0 0 12px rgba(0,0,0,0.6);" />
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
        const runActionsEl = document.getElementById('runActions');
        const shotOverlay = document.getElementById('shotOverlay');
        const shotOverlayImg = document.getElementById('shotOverlayImg');

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

          async function renderRunActions(runId, data) {
          if (!runActionsEl) return;
          const actions = (data && data.actions) || [];
          if (!actions.length) {
            runActionsEl.textContent = 'No actions for this run.';
            return;
          }
          runActionsEl.innerHTML = '';
            actions.forEach((act) => {
              const row = document.createElement('div');
              row.className = 'action-row';
              const idx = act.action_index;
              const displayIndex = actions.indexOf(act);
              const tool = act.tool || '';
              const target =
                (act.semantic_target && (act.semantic_target.text || act.semantic_target.css)) ||
                '';
              const statusOk = !!act.ok;
              const statusReason = act.reason || (statusOk ? 'ok' : 'failed');
              const ann = act.annotation || {};
              const label = (ann.label || '').toLowerCase();
              const artifacts = act.artifacts || {};
              const pb = act.pagebrain || {};
              const pbCandidates = Array.isArray(pb.candidates) ? pb.candidates : [];
              const pbChosen = (pb.chosen && pb.chosen.selector && pb.chosen.selector.value) || '';
              const selector =
                (act.executor && act.executor.selector) ||
                (pb.chosen && pb.chosen.selector) ||
                null;
              const targetSig = act.target_signature || (act.executor && act.executor.signature) || null;
              const beforeName = artifacts.screenshot_before;
              const afterName = artifacts.screenshot_after;

              const header = document.createElement('div');
              header.className = 'action-header';
              const statusSpan = document.createElement('span');
              statusSpan.textContent = statusOk ? 'OK' : statusReason || 'failed';
              statusSpan.className = statusOk ? 'action-status-ok' : 'action-status-failed';
              header.textContent = `#${displayIndex} [${tool}] ${target} \u2013 `;
              header.appendChild(statusSpan);
              row.appendChild(header);

              // PageBrain debug summary (candidates + chosen)
              if (pbCandidates.length || pbChosen) {
                const pbDiv = document.createElement('div');
                pbDiv.className = 'action-pagebrain';
                const parts = [];
                if (pbChosen) {
                  const shortChosen = pbChosen.length > 80 ? pbChosen.slice(0, 77) + '...' : pbChosen;
                  parts.push(`Chosen: ${shortChosen}`);
                }
                if (pbCandidates.length) {
                  parts.push(`candidates: ${pbCandidates.length}`);
                  const others = pbCandidates
                    .slice(0, 3)
                    .map((c) => {
                      const r = (typeof c.rank === 'number') ? c.rank : 0;
                      const sel = c.selector && c.selector.value ? String(c.selector.value) : '';
                      const shortSel = sel.length > 40 ? sel.slice(0, 37) + '...' : sel;
                      return `#${r} ${shortSel}`;
                    });
                  if (others.length) {
                    parts.push(`top: ${others.join(' | ')}`);
                  }
                }
                pbDiv.textContent = parts.join(' \u2022 ');
                row.appendChild(pbDiv);
              }

            if (beforeName || afterName) {
              const shots = document.createElement('div');
              shots.className = 'action-screenshots';
                const makeShot = (name, phaseLabel) => {
                  const img = document.createElement('img');
                  img.src = `/runs/${runId}/artifacts/${encodeURIComponent(name)}`;
                  img.alt = phaseLabel;
                  img.title = `Action ${displayIndex} \u2013 ${phaseLabel}`;
                  img.addEventListener('click', () => {
                    if (!shotOverlay || !shotOverlayImg) return;
                    shotOverlayImg.src = img.src;
                    shotOverlay.style.display = 'flex';
                  });
                  return img;
                };
                if (beforeName) {
                  shots.appendChild(makeShot(beforeName, 'before'));
                }
                if (afterName) {
                  shots.appendChild(makeShot(afterName, 'after'));
                }
                row.appendChild(shots);
              }

            const controls = document.createElement('div');
            controls.className = 'action-controls';
            const passedBtn = document.createElement('button');
            passedBtn.textContent = 'Passed';
            passedBtn.className = 'ann-btn';
            const failedBtn = document.createElement('button');
            failedBtn.textContent = 'Failed';
            failedBtn.className = 'ann-btn';
            if (label === 'passed') {
              passedBtn.classList.add('selected');
            } else if (label === 'failed') {
              failedBtn.classList.add('selected');
            }
            passedBtn.addEventListener('click', async () => {
              try {
                await postJSON(`/runs/${runId}/annotations`, {
                  action_index: idx,
                  label: 'passed',
                  source: 'human_truth',
                  tool,
                  selector,
                  target_signature: targetSig,
                });
                const updated = await getJSON(`/runs/${runId}/details`);
                runDetailsEl.textContent = JSON.stringify(updated, null, 2);
                await renderRunActions(runId, updated);
              } catch (e) {
                alert('Failed to annotate: ' + e.message);
              }
            });
            failedBtn.addEventListener('click', async () => {
              try {
                await postJSON(`/runs/${runId}/annotations`, {
                  action_index: idx,
                  label: 'failed',
                  source: 'human_truth',
                  tool,
                  selector,
                  target_signature: targetSig,
                });
                const updated = await getJSON(`/runs/${runId}/details`);
                runDetailsEl.textContent = JSON.stringify(updated, null, 2);
                await renderRunActions(runId, updated);
              } catch (e) {
                alert('Failed to annotate: ' + e.message);
              }
            });
            controls.appendChild(passedBtn);
            controls.appendChild(failedBtn);
            row.appendChild(controls);

            if (label) {
              const meta = document.createElement('div');
              meta.style.fontSize = '0.8rem';
              meta.textContent = `Annotation: ${label}`;
              row.appendChild(meta);
            }

            runActionsEl.appendChild(row);
          });
        }

        async function loadRunDetailsForRun(rid) {
          if (!runDetailsEl) return;
          if (!rid) return;
          try {
            const data = await getJSON(`/runs/${rid}/details`);
            runDetailsEl.textContent = JSON.stringify(data, null, 2);
            await renderRunActions(rid, data);
          } catch (e) {
            alert('Failed to load run details: ' + e.message);
          }
        }

        async function loadRunDetails() {
          if (!runDetailsIdEl) return;
          const rid = (runDetailsIdEl.value || '').trim();
          if (!rid) return;
          await loadRunDetailsForRun(rid);
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

        if (shotOverlay) {
          shotOverlay.addEventListener('click', () => {
            shotOverlay.style.display = 'none';
            if (shotOverlayImg) {
              shotOverlayImg.src = '';
            }
          });
        }

        setInterval(poll, 2000);
      </script>
    </body>
    </html>
    "+"""
    return HTMLResponse(content=html, status_code=200)
