const sections = [
  { key: 'capture', label: 'Capture' },
  { key: 'briefing', label: 'Morning Briefing' },
  { key: 'prep', label: 'Meeting Prep' },
  { key: 'search', label: 'Search / Ask' },
];

const app = document.getElementById('app');
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const apiUrl = (path) => `${API_BASE}${path}`;

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

async function safeJsonFetch(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  if (!response.ok) {
    const bodyText = await response.text();
    throw new Error(`HTTP ${response.status}: ${bodyText}`);
  }
  if (!contentType.includes('application/json')) {
    const bodyText = await response.text();
    throw new Error(`Expected JSON but got ${contentType}: ${bodyText}`);
  }
  return await response.json();
}

function render() {
  app.innerHTML = `
    <h1>ExecutiveOS</h1>
    <p>AI-first executive memory and decision platform.</p>
    ${apiError ? `<div style="border:1px solid #d00; padding:12px; margin-bottom:16px; background:#fee;"><strong>API error:</strong> ${apiError}</div>` : ''}
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
        }
        render();
      });
    }

    const confirmButton = app.querySelector('#capture-confirm');
    if (confirmButton) {
      confirmButton.addEventListener('click', async () => {
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
        try {
          const input = app.querySelector('#prep-input');
          meetingPrep = await safeJsonFetch(apiUrl('/meeting-prep'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ meeting: input.value || 'Executive meeting' }),
          });
          apiError = null;
        } catch (error) {
          setApiError(error.message);
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
        try {
          searchResults = await safeJsonFetch(apiUrl('/search'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: searchQuery || 'Why did we promote Julio?' }),
          });
          apiError = null;
        } catch (error) {
          setApiError(error.message);
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
      <button id="capture-submit" style="margin-top: 12px;">Classify and review updates</button>
      ${classificationResult ? `
        <div style="margin-top: 12px;">
          <h3>Suggested updates</h3>
          ${classificationResult.suggested_updates.map((item, index) => `
            <label style="display: block; margin-top: 8px;">
              <input class="approval-toggle" type="checkbox" data-index="${index}" ${selectedUpdateIndices.includes(index) ? 'checked' : ''} />
              <strong>${item.type}</strong> — ${item.name || item.title || item.details || 'Update'}
              ${item.details ? `<div style="margin-left: 20px; color: #666;">${item.details}</div>` : ''}
            </label>
          `).join('')}
          <button id="capture-confirm" style="margin-top: 12px;">Save approved updates</button>
        </div>
      ` : ''}
      ${classificationResult ? `<pre>${JSON.stringify(classificationResult, null, 2)}</pre>` : ''}
      ${captureResult ? `<pre>${JSON.stringify(captureResult, null, 2)}</pre>` : ''}
    `;
  }

  if (active === 'briefing') {
    if (!briefing) {
      fetch(apiUrl('/briefing'))
        .then((response) => response.json())
        .then((data) => {
          briefing = data;
          render();
        })
        .catch(() => {
          briefing = { error: 'Backend unavailable' };
          render();
        });
      return '<p>Loading briefing…</p>';
    }

    return `
      <h2>Morning Briefing</h2>
      <pre>${JSON.stringify(briefing, null, 2)}</pre>
    `;
  }

  if (active === 'prep') {
    return `
      <h2>Meeting Prep</h2>
      <p>Generate a meeting agenda from recent summaries, open decisions, people, and strategic issues.</p>
      <input id="prep-input" value="RYSE leadership meeting" />
      <button id="prep-submit" style="margin-top: 12px;">Prepare meeting</button>
      ${meetingPrep ? `<pre>${JSON.stringify(meetingPrep, null, 2)}</pre>` : ''}
    `;
  }

  return `
    <h2>Search / Ask</h2>
    <input id="search-input" placeholder="Why did we promote Julio?" />
    <button id="search-submit" style="margin-top: 12px;">Ask ExecutiveOS</button>
    ${searchResults ? `<pre>${JSON.stringify(searchResults, null, 2)}</pre>` : ''}
  `;
}

render();
