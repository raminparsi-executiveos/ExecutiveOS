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
const TOKEN_KEY = 'executiveos_session';

function storedToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

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
let captureText = '';
let searchQuery = '';
let meetingQuery = '';
let captureResult = null;
let classificationResult = null;
let selectedUpdateIndices = [];
let apiError = null;
let briefingLoading = false;
let submitting = false;
let authToken = storedToken();
let authState = 'loading';
let authMessage = '';
let authIsRequired = false;
let authConfigurationIssue = '';

async function safeJsonFetch(url, options) {
  const headers = new Headers(options?.headers || {});
  if (authToken) headers.set('Authorization', `Bearer ${authToken}`);
  const response = await fetch(url, { ...options, headers });
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
    if (response.status === 401) {
      logout('Your session expired. Please sign in again.');
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  if (!contentType.includes('application/json')) {
    throw new Error('The API returned an unexpected response');
  }
  return response.json();
}

function render() {
  if (authState !== 'authenticated') {
    renderAuthentication();
    return;
  }

  app.innerHTML = `
    <header class="app-header"><div><h1>ExecutiveOS</h1><p>AI-first executive memory and decision platform.</p></div>${authIsRequired ? '<button id="logout" class="secondary">Sign out</button>' : ''}</header>
    ${apiError ? `<div class="error" role="alert"><strong>API error:</strong> ${escapeHtml(apiError)}</div>` : ''}
    <nav aria-label="ExecutiveOS sections">
      ${sections.map((section) => `<button type="button" class="${section.key === active ? 'active' : ''}" data-key="${section.key}" aria-pressed="${section.key === active}">${section.label}</button>`).join('')}
    </nav>
    <section class="panel">
      ${renderPanel()}
    </section>
  `;

  app.querySelector('#logout')?.addEventListener('click', () => logout());

  app.querySelectorAll('button[data-key]').forEach((button) => {
    button.addEventListener('click', () => {
      const nextSection = button.getAttribute('data-key');
      if (nextSection === 'briefing' && nextSection !== active) briefing = null;
      active = nextSection;
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
        if (classificationResult) {
          classificationResult = null;
          selectedUpdateIndices = [];
          app.querySelector('#classification-review')?.remove();
        }
        captureResult = null;
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
              classification_source: classificationResult?.classification_source || 'unknown',
            }),
          });
          // Generated outputs are disposable views over memory. Invalidate them
          // whenever the underlying memory changes.
          briefing = null;
          meetingPrep = null;
          searchResults = null;
          classificationResult = null;
          selectedUpdateIndices = [];
          captureText = '';
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
        render();
      });
    });
  }

  if (active === 'prep') {
    const input = app.querySelector('#prep-input');
    const button = app.querySelector('#prep-submit');
    if (input) {
      input.value = meetingQuery;
      input.addEventListener('input', (event) => {
        meetingQuery = event.target.value;
      });
    }
    if (button) {
      button.addEventListener('click', async () => {
        if (submitting) return;
        const meeting = meetingQuery.trim() || 'Executive meeting';
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
    input?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') button?.click();
    });
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
    input?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') button?.click();
    });
  }
}

function renderAuthentication() {
  if (authState === 'loading') {
    app.innerHTML = '<section class="auth-card"><h1>ExecutiveOS</h1><p>Loading securely…</p></section>';
    return;
  }
  if (authState === 'configuration_error') {
    app.innerHTML = `<section class="auth-card"><h1>ExecutiveOS</h1><div class="error" role="alert">${escapeHtml(authConfigurationIssue || 'Login is not configured. Check the backend environment variables.')}</div></section>`;
    return;
  }
  app.innerHTML = `
    <section class="auth-card">
      <h1>ExecutiveOS</h1>
      <p>Sign in to your executive memory.</p>
      ${authMessage ? `<div class="error" role="alert">${escapeHtml(authMessage)}</div>` : ''}
      <form id="login-form">
        <label>Username<input id="username" name="username" autocomplete="username" required /></label>
        <label>Password<input id="password" name="password" type="password" autocomplete="current-password" required /></label>
        <button type="submit" ${submitting ? 'disabled' : ''}>${submitting ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </section>`;
  app.querySelector('#login-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (submitting) return;
    submitting = true;
    authMessage = '';
    const form = new FormData(event.currentTarget);
    const credentials = { username: form.get('username'), password: form.get('password') };
    render();
    try {
      const result = await safeJsonFetch(apiUrl('/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      });
      authToken = result.access_token;
      sessionStorage.setItem(TOKEN_KEY, authToken);
      authState = 'authenticated';
      apiError = null;
    } catch (error) {
      authMessage = error.message;
    } finally {
      submitting = false;
      render();
    }
  });
}

function logout(message = '') {
  authToken = '';
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
  authState = 'unauthenticated';
  authMessage = message;
  briefing = null;
  meetingPrep = null;
  searchResults = null;
  render();
}

async function initialize() {
  try {
    const status = await safeJsonFetch(apiUrl('/auth/status'));
    authIsRequired = status.required;
    if (status.required && !status.configured) {
      const checks = status.checks || {};
      const failures = [];
      if (!checks.password_present) failures.push('EXECUTIVEOS_PASSWORD is not reaching the backend');
      else if (!checks.password_valid) failures.push('EXECUTIVEOS_PASSWORD is shorter than 12 characters');
      if (!checks.session_secret_present) failures.push('SESSION_SECRET is not reaching the backend');
      else if (!checks.session_secret_valid) failures.push('SESSION_SECRET is shorter than 32 characters');
      authConfigurationIssue = failures.length ? failures.join('. ') : 'Login configuration is incomplete.';
      authState = 'configuration_error';
    } else {
      authState = status.required && !authToken ? 'unauthenticated' : 'authenticated';
    }
  } catch (error) {
    authState = 'unauthenticated';
    authMessage = error.message;
  }
  render();
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
      <label for="capture-input" class="sr-only">Executive update</label>
      <textarea id="capture-input" rows="6" placeholder="Example: Morgan owns the Zephyr expansion. The main risk is distributor capacity."></textarea>
      <button id="capture-submit" style="margin-top: 12px;" ${submitting ? 'disabled' : ''}>${submitting ? 'Working…' : 'Classify and review updates'}</button>
      ${classificationResult ? `
        <div id="classification-review" style="margin-top: 12px;">
          <div class="section-heading">
            <h3>Suggested updates</h3>
            <span class="badge">${classificationResult.classification_source === 'ai' ? 'AI organized' : 'Local preview'}</span>
          </div>
          ${classificationResult.suggested_updates.length ? classificationResult.suggested_updates.map((item, index) => `
            <label class="suggestion">
              <input class="approval-toggle" type="checkbox" data-index="${index}" ${selectedUpdateIndices.includes(index) ? 'checked' : ''} />
              <span><strong>${escapeHtml(humanize(item.type))}</strong> — ${escapeHtml(item.name || item.title || item.details || 'Update')}
              ${item.company ? `<small>Company: ${escapeHtml(item.company)}</small>` : ''}
              ${item.details ? `<small>${escapeHtml(item.details)}</small>` : ''}</span>
            </label>
          `).join('') : '<p class="muted">No reliable structured updates were found. Add a person, company, project, decision, or metric and try again.</p>'}
          ${classificationResult.follow_ups?.length ? `<div class="follow-ups"><strong>Useful follow-up</strong>${renderList(classificationResult.follow_ups)}</div>` : ''}
          ${classificationResult.suggested_updates.length ? `<button id="capture-confirm" style="margin-top: 12px;" ${submitting || selectedUpdateIndices.length === 0 ? 'disabled' : ''}>${submitting ? 'Saving…' : `Save ${selectedUpdateIndices.length} approved update${selectedUpdateIndices.length === 1 ? '' : 's'}`}</button>` : ''}
        </div>
      ` : ''}
      ${captureResult ? `<p class="success" role="status">${escapeHtml(captureResult.saved_count)} approved update${captureResult.saved_count === 1 ? '' : 's'} saved. Briefing, meeting prep, and search will now use the refreshed memory.</p>` : ''}
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
      <label for="prep-input" class="sr-only">Meeting name or context</label>
      <input id="prep-input" placeholder="Example: RYSE leadership meeting" />
      <button id="prep-submit" style="margin-top: 12px;" ${submitting ? 'disabled' : ''}>${submitting ? 'Preparing…' : 'Prepare meeting'}</button>
      ${meetingPrep ? `
        <div class="output">
          <h3>${escapeHtml(meetingPrep.meeting)}</h3>
          <h4>Proposed agenda</h4>${renderList(meetingPrep.agenda)}
          <div class="briefing-grid">
            <article><h4>People</h4>${renderList(meetingPrep.related_people)}</article>
            <article><h4>Strategic issues</h4>${renderList(meetingPrep.related_strategic_issues)}</article>
            <article><h4>Projects</h4>${renderList(meetingPrep.related_projects)}</article>
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
    <label for="search-input" class="sr-only">Question about executive memory</label>
    <input id="search-input" placeholder="Example: Why did we promote Julio?" />
    <button id="search-submit" style="margin-top: 12px;" ${submitting ? 'disabled' : ''}>${submitting ? 'Searching…' : 'Ask ExecutiveOS'}</button>
    ${searchResults ? `<div class="results"><aside class="focus"><strong>ExecutiveOS answer</strong><p>${escapeHtml(searchResults.answer || 'No matching executive memory found.')}</p></aside>${searchResults.results.length ? searchResults.results.map((result) => `
      <article><span class="badge">${escapeHtml(humanize(result.type))}</span><h3>${escapeHtml(result.title)}</h3><p>${escapeHtml(result.summary)}</p></article>
    `).join('') : '<p class="muted">No matching executive memory found.</p>'}</div>` : ''}
  `;
}

initialize();
