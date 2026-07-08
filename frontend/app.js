const sections = [
  { key: 'capture', label: 'Capture' },
  { key: 'briefing', label: 'Morning Briefing' },
  { key: 'prep', label: 'Meeting Prep' },
  { key: 'search', label: 'Search / Ask' },
];

const app = document.getElementById('app');
const configuredApiBase = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').trim();
const API_BASE = (/^https?:\/\//i.test(configuredApiBase) ? configuredApiBase : `https://${configuredApiBase}`).replace(/\/$/, '');
const apiUrl = (path) => `${API_BASE}${path}`;

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function renderList(items, emptyMessage = 'Nothing needs attention right now.') {
  if (!items?.length) return `<p class="muted">${escapeHtml(emptyMessage)}</p>`;
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
}

function humanize(value) {
  return String(value).replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

let active = 'capture';
let briefing = null;
let meetingPrep = null;
let searchResults = null;
let captureText = 'Julio is now responsible for PM quality and high-priority clients. His pay is increasing from $14.42/hr to $17.50/hr.';
let searchQuery = 'Why did we promote Julio?';
let captureResult = null;
let classificationResult = null;
let selectedUpdateIndices = [];
let apiError = null;
let briefingLoading = false;
let submitting = false;

async function safeJsonFetch(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  if (!response.ok) {
    const bodyText = await response.text();
    let detail = '';
    try {
      const body = JSON.parse(bodyText);
      detail = typeof body.detail === 'string' ? body.detail : '';
    } catch {
      // Do not expose an arbitrary upstream response body in the UI.
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  if (!contentType.includes('application/json')) {
    throw new Error('The API returned an unexpected response');
  }
  return response.json();
}

function render() {
  app.innerHTML = `
    <h1>ExecutiveOS</h1>
    <p>AI-first executive memory and decision platform.</p>
    ${apiError ? `<div class="error" role="alert"><strong>API error:</strong> ${escapeHtml(apiError)}</div>` : ''}
    <nav>
      ${sections.map((section) => `<button class="${section.key === active ? 'active' : ''}" data-key="${section.key}">${section.label}</button>`).join('')}
    </nav>
    <section class="panel">
      ${renderPanel()}
    </section>
  `;

  app.querySelectorAll('button[data-key]').forEach((button) => {
    button.addEventListener('click', () => {
      active = button.getAttribute('data-key');
      render();
    });
  });

  if (active === 'capture') {
    const textarea = app.querySelector('textarea');
    const button = app.querySelector('#capture-submit');
    if (textarea) {
      textarea.value = captureText;
      textarea.addEventListener('input', (event) => {
        captureText = event.target.value;
      });
    }
    if (button) {
      button.addEventListener('click', async () => {
        if (!captureText.trim() || submitting) return;
        submitting = true;
        render();
        try {
          classificationResult = await safeJsonFetch(apiUrl('/capture/classify'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: captureText, confirm: true }),
          });
          selectedUpdateIndices = (classificationResult.suggested_updates || []).map((_, index) => index);
          captureResult = null;
          apiError = null;
        } catch (error) {
          setApiError(error.message);
        } finally {
          submitting = false;
        }
        render();
      });
    }

    const confirmButton = app.querySelector('#capture-confirm');
    if (confirmButton) {
      confirmButton.addEventListener('click', async () => {
        if (submitting) return;
        submitting = true;
        render();
        try {
          const approvedUpdates = (classificationResult?.suggested_updates || []).filter((_, index) => selectedUpdateIndices.includes(index));
          captureResult = await safeJsonFetch(apiUrl('/capture/confirm'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              text: captureText,
              approved_updates: approvedUpdates,
            }),
          });
          apiError = null;
        } catch (error) {
          setApiError(error.message);
        } finally {
          submitting = false;
        }
        render();
      });
    }

    app.querySelectorAll('.approval-toggle').forEach((input) => {
      input.addEventListener('change', () => {
        const index = Number(input.getAttribute('data-index'));
        if (input.checked) {
          if (!selectedUpdateIndices.includes(index)) {
            selectedUpdateIndices.push(index);
          }
        } else {
          selectedUpdateIndices = selectedUpdateIndices.filter((value) => value !== index);
        }
      });
    });
  }

  if (active === 'prep') {
    const button = app.querySelector('#prep-submit');
    if (button) {
      button.addEventListener('click', async () => {
        if (submitting) return;
        const meeting = app.querySelector('#prep-input').value.trim() || 'Executive meeting';
        submitting = true;
        render();
        try {
          meetingPrep = await safeJsonFetch(apiUrl('/meeting-prep'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ meeting }),
          });
          apiError = null;
        } catch (error) {
          setApiError(error.message);
        } finally {
          submitting = false;
        }
        render();
      });
    }
  }

  if (active === 'search') {
    const input = app.querySelector('#search-input');
    const button = app.querySelector('#search-submit');
    if (input) {
      input.value = searchQuery;
      input.addEventListener('input', (event) => {
        searchQuery = event.target.value;
      });
    }
    if (button) {
      button.addEventListener('click', async () => {
        if (!searchQuery.trim() || submitting) return;
        submitting = true;
        render();
        try {
          searchResults = await safeJsonFetch(apiUrl('/search'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: searchQuery || 'Why did we promote Julio?' }),
          });
          apiError = null;
        } catch (error) {
          setApiError(error.message);
        } finally {
          submitting = false;
        }
        render();
      });
    }
  }
}

function setApiError(error) {
  apiError = error;
  render();
}

function renderPanel() {
  if (active === 'capture') {
    return `
      <h2>Capture</h2>
      <p>Enter natural language, review the suggested updates, and approve the ones that should be saved.</p>
      <textarea rows="6"></textarea>
      <button id="capture-submit" style="margin-top: 12px;" ${submitting ? 'disabled' : ''}>${submitting ? 'Working…' : 'Classify and review updates'}</button>
      ${classificationResult ? `
        <div style="margin-top: 12px;">
          <div class="section-heading">
            <h3>Suggested updates</h3>
            <span class="badge">${classificationResult.classification_source === 'ai' ? 'AI organized' : 'Local preview'}</span>
          </div>
          ${classificationResult.suggested_updates.map((item, index) => `
            <label class="suggestion">
              <input class="approval-toggle" type="checkbox" data-index="${index}" ${selectedUpdateIndices.includes(index) ? 'checked' : ''} />
              <span><strong>${escapeHtml(humanize(item.type))}</strong> — ${escapeHtml(item.name || item.title || item.details || 'Update')}
              ${item.details ? `<small>${escapeHtml(item.details)}</small>` : ''}</span>
            </label>
          `).join('')}
          ${classificationResult.follow_ups?.length ? `<div class="follow-ups"><strong>Useful follow-up</strong>${renderList(classificationResult.follow_ups)}</div>` : ''}
          <button id="capture-confirm" style="margin-top: 12px;" ${submitting ? 'disabled' : ''}>${submitting ? 'Saving…' : 'Save approved updates'}</button>
        </div>
      ` : ''}
      ${captureResult ? `<p class="success" role="status">Approved updates are now part of executive memory.</p>` : ''}
    `;
  }

  if (active === 'briefing') {
    if (!briefing && !briefingLoading) {
      briefingLoading = true;
      safeJsonFetch(apiUrl('/briefing'))
        .then((data) => {
          briefing = data;
        })
        .catch((error) => {
          apiError = error.message;
        })
        .finally(() => {
          briefingLoading = false;
          render();
        });
    }

    if (!briefing) return '<p>Loading briefing…</p>';

    return `
      <h2>Morning Briefing</h2>
      <div class="briefing-grid">
        ${Object.entries(briefing).filter(([key]) => key !== 'recommended_focus').map(([key, value]) => `
          <article><h3>${escapeHtml(humanize(key))}</h3>${Array.isArray(value) ? renderList(value) : `<p>${escapeHtml(value)}</p>`}</article>
        `).join('')}
      </div>
      <aside class="focus"><strong>Recommended focus</strong><p>${escapeHtml(briefing.recommended_focus || 'Review the priorities above.')}</p></aside>
    `;
  }

  if (active === 'prep') {
    return `
      <h2>Meeting Prep</h2>
      <p>Generate a meeting agenda from recent summaries, open decisions, people, and strategic issues.</p>
      <input id="prep-input" value="RYSE leadership meeting" />
      <button id="prep-submit" style="margin-top: 12px;" ${submitting ? 'disabled' : ''}>${submitting ? 'Preparing…' : 'Prepare meeting'}</button>
      ${meetingPrep ? `
        <div class="output">
          <h3>${escapeHtml(meetingPrep.meeting)}</h3>
          <h4>Proposed agenda</h4>${renderList(meetingPrep.agenda)}
          <div class="briefing-grid">
            <article><h4>People</h4>${renderList(meetingPrep.related_people)}</article>
            <article><h4>Strategic issues</h4>${renderList(meetingPrep.related_strategic_issues)}</article>
            <article><h4>Open decisions</h4>${renderList(meetingPrep.open_decisions)}</article>
            <article><h4>Recent context</h4>${renderList(meetingPrep.recent_meeting_context)}</article>
            <article><h4>Action items</h4>${renderList(meetingPrep.action_items)}</article>
            <article><h4>Metrics</h4>${renderList(meetingPrep.metrics)}</article>
            <article><h4>Risks</h4>${renderList(meetingPrep.risks)}</article>
          </div>
        </div>` : ''}
    `;
  }

  return `
    <h2>Search / Ask</h2>
    <input id="search-input" placeholder="Why did we promote Julio?" />
    <button id="search-submit" style="margin-top: 12px;" ${submitting ? 'disabled' : ''}>${submitting ? 'Searching…' : 'Ask ExecutiveOS'}</button>
    ${searchResults ? `<div class="results">${searchResults.results.length ? searchResults.results.map((result) => `
      <article><span class="badge">${escapeHtml(humanize(result.type))}</span><h3>${escapeHtml(result.title)}</h3><p>${escapeHtml(result.summary)}</p></article>
    `).join('') : '<p class="muted">No matching executive memory found.</p>'}</div>` : ''}
  `;
}

render();
