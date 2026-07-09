const sections = [
  { key: 'capture', label: 'Capture' },
  { key: 'briefing', label: 'Morning Briefing' },
  { key: 'prep', label: 'Meeting Prep' },
  { key: 'search', label: 'Search / Ask' },
  { key: 'memory', label: 'Memory' },
];

const memoryTypes = [
  { key: 'companies', label: 'Companies', titleField: 'name' },
  { key: 'people', label: 'People', titleField: 'name' },
  { key: 'strategic-issues', label: 'Strategic Issues', titleField: 'title' },
  { key: 'projects', label: 'Projects', titleField: 'title' },
  { key: 'decisions', label: 'Decisions', titleField: 'title' },
  { key: 'meetings', label: 'Meetings', titleField: 'title' },
  { key: 'sops', label: 'SOPs', titleField: 'title' },
  { key: 'documents', label: 'Documents', titleField: 'title' },
  { key: 'metrics', label: 'Metrics', titleField: 'title' },
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
  return `<ul>${items.map((item) => `<li>${renderListItem(item)}</li>`).join('')}</ul>`;
}

function humanize(value) {
  return String(value).replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function companyClass(company) {
  const normalized = String(company || 'unassigned').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  if (normalized.includes('pec') || normalized.includes('pro-engineering')) return 'company-pec';
  if (normalized.includes('ryse')) return 'company-ryse';
  if (normalized.includes('everpole')) return 'company-everpole';
  if (normalized.includes('myndlog')) return 'company-myndlog';
  return 'company-unassigned';
}

function renderCompanyChip(company) {
  if (!company) return '<span class="company-chip company-unassigned">Unassigned</span>';
  return `<span class="company-chip ${companyClass(company)}">${escapeHtml(company)}</span>`;
}

function renderListItem(item) {
  if (item && typeof item === 'object' && 'label' in item) {
    return `<span class="item-with-company">${renderCompanyChip(item.company)}<span>${escapeHtml(item.label)}</span></span>`;
  }
  return escapeHtml(item);
}

function itemCount(items) {
  return Array.isArray(items) ? items.length : 0;
}

function renderPrepSection(title, items, tone = 'neutral', emptyMessage = 'Nothing found.') {
  return `
    <article class="prep-section prep-${tone}">
      <div class="prep-section-heading">
        <h4>${escapeHtml(title)}</h4>
        <span class="count-pill">${itemCount(items)}</span>
      </div>
      ${renderList(items, emptyMessage)}
    </article>
  `;
}

function renderMeetingPrepOutput(prep) {
  const contextCount = itemCount(prep.related_people) + itemCount(prep.related_strategic_issues)
    + itemCount(prep.related_projects) + itemCount(prep.open_decisions)
    + itemCount(prep.metrics) + itemCount(prep.risks);
  return `
    <div class="meeting-prep-output">
      <header class="meeting-prep-header">
        <div>
          <h3>${escapeHtml(prep.meeting)}</h3>
          ${prep.context_found === false ? '<p class="empty-notice" role="status">No matching executive memory was found. This agenda is a starting template; add more specific context or capture the meeting details first.</p>' : ''}
        </div>
        <div class="prep-stats" aria-label="Meeting prep summary">
          <span><strong>${itemCount(prep.agenda)}</strong> agenda</span>
          <span><strong>${contextCount}</strong> context</span>
          <span><strong>${itemCount(prep.action_items)}</strong> actions</span>
        </div>
      </header>
      <div class="prep-layout">
        <section class="agenda-panel">
          <div class="prep-section-heading">
            <h4>Proposed agenda</h4>
            <span class="count-pill">${itemCount(prep.agenda)}</span>
          </div>
          <ol>
            ${(prep.agenda || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}
          </ol>
        </section>
        <section class="prep-stack">
          ${renderPrepSection('Action items', prep.action_items, 'action', 'No open action items.')}
          ${renderPrepSection('Risks', prep.risks, 'risk', 'No risks found.')}
          ${renderPrepSection('Open decisions', prep.open_decisions, 'decision', 'No open decisions.')}
        </section>
      </div>
      <div class="prep-grid">
        ${renderPrepSection('People', prep.related_people, 'people')}
        ${renderPrepSection('Strategic issues', prep.related_strategic_issues, 'issue')}
        ${renderPrepSection('Projects', prep.related_projects, 'project')}
        ${renderPrepSection('Metrics', prep.metrics, 'metric')}
        ${renderPrepSection('Recent meeting context', prep.recent_meeting_context, 'context')}
        ${renderPrepSection('Recent captured updates', prep.recent_capture_context, 'context')}
      </div>
    </div>
  `;
}

function currentMemoryType() {
  return memoryTypes.find((type) => type.key === memoryType) || memoryTypes[0];
}

function editableObjectAttributes(item) {
  const attributes = { ...item };
  delete attributes.id;
  return attributes;
}

let active = 'capture';
let briefing = null;
let meetingPrep = null;
let searchResults = null;
let captureText = '';
let screenshots = [];
let searchQuery = '';
let meetingQuery = '';
let memoryType = 'people';
let memoryObjects = null;
let memoryLoading = false;
let memoryEdit = null;
let memoryMessage = '';
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
      if (!detail && Array.isArray(body.detail)) {
        detail = body.detail
          .map((issue) => typeof issue?.msg === 'string' ? issue.msg.replace(/^Value error,\s*/i, '') : '')
          .filter(Boolean)
          .join('. ');
      }
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

async function loadMemoryObjects() {
  memoryLoading = true;
  memoryMessage = '';
  try {
    memoryObjects = await safeJsonFetch(apiUrl(`/objects/${memoryType}`));
    apiError = null;
  } catch (error) {
    setApiError(error.message);
  } finally {
    memoryLoading = false;
    render();
  }
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
    const screenshotInput = app.querySelector('#screenshot-input');
    if (textarea) {
      textarea.value = captureText;
      textarea.addEventListener('input', (event) => {
        captureText = event.target.value;
        if (button) {
          button.disabled = submitting || (!captureText.trim() && !screenshots.length);
          button.textContent = screenshots.length ? `Analyze and review ${screenshots.length} screenshot${screenshots.length === 1 ? '' : 's'}` : 'Classify and review updates';
        }
        if (classificationResult) {
          classificationResult = null;
          selectedUpdateIndices = [];
          app.querySelector('#classification-review')?.remove();
        }
        captureResult = null;
      });
    }
    screenshotInput?.addEventListener('change', (event) => {
      const files = Array.from(event.target.files || []);
      if (!files.length) return;
      if (screenshots.length + files.length > 5) {
        setApiError('Attach up to 5 screenshots.');
        return;
      }
      const invalid = files.find((file) => !['image/png', 'image/jpeg', 'image/webp'].includes(file.type));
      if (invalid) {
        setApiError('Use PNG, JPEG, or WebP screenshots.');
        return;
      }
      const oversized = files.find((file) => file.size > 5 * 1024 * 1024);
      if (oversized) {
        setApiError('Each screenshot must be 5 MB or smaller.');
        return;
      }
      Promise.all(files.map((file) => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({ name: file.name, data: String(reader.result || '') });
        reader.onerror = () => reject(new Error('Screenshot could not be read.'));
        reader.readAsDataURL(file);
      }))).then((loadedScreenshots) => {
        screenshots = [...screenshots, ...loadedScreenshots];
        classificationResult = null;
        selectedUpdateIndices = [];
        captureResult = null;
        apiError = null;
        render();
      }).catch((error) => setApiError(error.message));
    });
    app.querySelectorAll('[data-remove-screenshot]').forEach((button) => {
      button.addEventListener('click', () => {
        const index = Number(button.getAttribute('data-remove-screenshot'));
        screenshots = screenshots.filter((_, screenshotIndex) => screenshotIndex !== index);
        classificationResult = null;
        selectedUpdateIndices = [];
        render();
      });
    });
    app.querySelector('#screenshots-clear')?.addEventListener('click', () => {
      screenshots = [];
      classificationResult = null;
      selectedUpdateIndices = [];
      render();
    });
    if (button) {
      button.addEventListener('click', async () => {
        if ((!captureText.trim() && !screenshots.length) || submitting) return;
        submitting = true;
        render();
        try {
          classificationResult = await safeJsonFetch(apiUrl('/capture/classify'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              text: captureText,
              image_data_list: screenshots.map((screenshot) => screenshot.data),
              confirm: true,
            }),
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
              text: captureText.trim() || `Screenshot capture: ${screenshots.map((screenshot) => screenshot.name).join(', ')}`,
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
          screenshots = [];
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

  if (active === 'memory') {
    const select = app.querySelector('#memory-type');
    select?.addEventListener('change', () => {
      memoryType = select.value;
      memoryObjects = null;
      memoryEdit = null;
      memoryMessage = '';
      render();
    });

    app.querySelectorAll('[data-edit-object]').forEach((button) => {
      button.addEventListener('click', () => {
        const id = Number(button.getAttribute('data-edit-object'));
        const item = (memoryObjects?.items || []).find((candidate) => candidate.id === id);
        if (!item) return;
        memoryEdit = {
          id,
          title: item[currentMemoryType().titleField] || `${currentMemoryType().label} #${id}`,
          text: JSON.stringify(editableObjectAttributes(item), null, 2),
        };
        memoryMessage = '';
        render();
      });
    });

    app.querySelector('#memory-cancel')?.addEventListener('click', () => {
      memoryEdit = null;
      memoryMessage = '';
      render();
    });

    app.querySelector('#memory-save')?.addEventListener('click', async () => {
      if (!memoryEdit || submitting) return;
      let attributes = {};
      try {
        attributes = JSON.parse(app.querySelector('#memory-editor')?.value || '{}');
      } catch {
        memoryMessage = 'Enter valid JSON before saving.';
        render();
        return;
      }
      submitting = true;
      render();
      try {
        await safeJsonFetch(apiUrl(`/objects/${memoryType}/${memoryEdit.id}`), {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ attributes }),
        });
        memoryEdit = null;
        memoryObjects = null;
        memoryMessage = 'Memory object updated.';
        briefing = null;
        meetingPrep = null;
        searchResults = null;
      } catch (error) {
        setApiError(error.message);
      } finally {
        submitting = false;
      }
      render();
    });

    app.querySelector('#memory-delete')?.addEventListener('click', async () => {
      if (!memoryEdit || submitting) return;
      submitting = true;
      render();
      try {
        await safeJsonFetch(apiUrl(`/objects/${memoryType}/${memoryEdit.id}`), { method: 'DELETE' });
        memoryEdit = null;
        memoryObjects = null;
        memoryMessage = 'Memory object deleted.';
        briefing = null;
        meetingPrep = null;
        searchResults = null;
      } catch (error) {
        setApiError(error.message);
      } finally {
        submitting = false;
      }
      render();
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
      <p>Enter natural language or attach a screenshot, then review and approve the structured updates.</p>
      <label for="capture-input" class="sr-only">Executive update</label>
      <textarea id="capture-input" rows="6" placeholder="Example: Morgan owns the Zephyr expansion. The main risk is distributor capacity."></textarea>
      <div class="screenshot-controls">
        <label class="file-button" for="screenshot-input">Attach screenshots</label>
        <input id="screenshot-input" type="file" accept="image/png,image/jpeg,image/webp" multiple />
        <span class="muted">PNG, JPEG, or WebP · 5 MB each · 5 maximum</span>
      </div>
      ${screenshots.length ? `<div class="screenshot-preview-grid">${screenshots.map((screenshot, index) => `
        <div class="screenshot-preview"><img src="${screenshot.data}" alt="Screenshot ${index + 1} selected for capture" /><div><strong>${escapeHtml(screenshot.name)}</strong><button data-remove-screenshot="${index}" type="button" class="secondary">Remove</button></div></div>
      `).join('')}<button id="screenshots-clear" type="button" class="secondary">Remove all</button></div>` : ''}
      <button id="capture-submit" style="margin-top: 12px;" ${submitting || (!captureText.trim() && !screenshots.length) ? 'disabled' : ''}>${submitting ? 'Working…' : screenshots.length ? `Analyze and review ${screenshots.length} screenshot${screenshots.length === 1 ? '' : 's'}` : 'Classify and review updates'}</button>
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
              ${item.role ? `<small>Role: ${escapeHtml(item.role)}</small>` : ''}
              ${item.owner ? `<small>Owner: ${escapeHtml(item.owner)}</small>` : ''}
              ${item.value ? `<small>Value: ${escapeHtml(item.value)}${item.trend ? ` · ${escapeHtml(item.trend)}` : ''}</small>` : ''}
              ${item.final_decision ? `<small>Decision: ${escapeHtml(item.final_decision)}</small>` : ''}
              ${item.reasoning ? `<small>Reasoning: ${escapeHtml(item.reasoning)}</small>` : ''}
              ${item.risks?.length ? `<small>Risks: ${escapeHtml(item.risks.join(', '))}</small>` : ''}
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
      ${meetingPrep ? renderMeetingPrepOutput(meetingPrep) : ''}
    `;
  }

  if (active === 'memory') {
    const selectedType = currentMemoryType();
    if (!memoryObjects && !memoryLoading) {
      loadMemoryObjects();
    }

    return `
      <h2>Memory</h2>
      <div class="toolbar">
        <label for="memory-type">Object type</label>
        <select id="memory-type">
          ${memoryTypes.map((type) => `<option value="${type.key}" ${type.key === memoryType ? 'selected' : ''}>${escapeHtml(type.label)}</option>`).join('')}
        </select>
      </div>
      ${memoryMessage ? `<p class="success" role="status">${escapeHtml(memoryMessage)}</p>` : ''}
      ${memoryLoading || !memoryObjects ? '<p>Loading memory…</p>' : `
        <div class="memory-list">
          ${memoryObjects.items.length ? memoryObjects.items.map((item) => `
            <article>
              <div>
                <span class="badge">#${escapeHtml(item.id)}</span>
                <h3>${escapeHtml(item[selectedType.titleField] || `${selectedType.label} memory`)}</h3>
                <p>${escapeHtml(item.company || item.status || item.type || item.value || 'Stored memory object')}</p>
              </div>
              <button type="button" class="secondary" data-edit-object="${escapeHtml(item.id)}">Edit</button>
            </article>
          `).join('') : '<p class="muted">No objects found for this type.</p>'}
        </div>
      `}
      ${memoryEdit ? `
        <div class="editor-panel">
          <div class="section-heading">
            <h3>${escapeHtml(memoryEdit.title)}</h3>
            <button id="memory-cancel" type="button" class="secondary">Close</button>
          </div>
          <label for="memory-editor" class="sr-only">Object attributes JSON</label>
          <textarea id="memory-editor" rows="12">${escapeHtml(memoryEdit.text)}</textarea>
          <div class="button-row">
            <button id="memory-save" type="button" ${submitting ? 'disabled' : ''}>${submitting ? 'Saving…' : 'Save changes'}</button>
            <button id="memory-delete" type="button" class="danger" ${submitting ? 'disabled' : ''}>${submitting ? 'Deleting…' : 'Delete object'}</button>
          </div>
        </div>
      ` : ''}
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
