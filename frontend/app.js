const sections = [
  { key: 'capture', label: 'Capture' },
  { key: 'captureAudit', label: 'Capture Audit' },
  { key: 'briefing', label: 'Morning Briefing' },
  { key: 'inbox', label: 'Executive Inbox' },
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
  { key: 'tasks', label: 'Tasks', titleField: 'title' },
];

const auditRecordTypeToMemoryType = {
  company: 'companies',
  person: 'people',
  strategic_issue: 'strategic-issues',
  project: 'projects',
  decision: 'decisions',
  meeting: 'meetings',
  sop: 'sops',
  document: 'documents',
  metric: 'metrics',
  task: 'tasks',
};

const app = document.getElementById('app');
const configuredApiBase = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').trim();
const API_BASE = (/^https?:\/\//i.test(configuredApiBase) ? configuredApiBase : `https://${configuredApiBase}`).replace(/\/$/, '');
const apiUrl = (path) => `${API_BASE}${path}`;
const TOKEN_KEY = 'executiveos_session';
const SCREENSHOT_MAX_DIMENSION = 1600;
const SCREENSHOT_JPEG_QUALITY = 0.72;
const SCREENSHOT_MAX_UPLOAD_BYTES = 12 * 1024 * 1024;

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

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('Screenshot could not be read.'));
    reader.readAsDataURL(file);
  });
}

function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('Screenshot could not be prepared.'));
    image.src = dataUrl;
  });
}

async function prepareScreenshot(file) {
  const originalData = await readFileAsDataUrl(file);
  const image = await loadImage(originalData);
  const originalWidth = image.naturalWidth || image.width;
  const originalHeight = image.naturalHeight || image.height;
  const scale = Math.min(1, SCREENSHOT_MAX_DIMENSION / Math.max(originalWidth, originalHeight));
  const width = Math.max(1, Math.round(originalWidth * scale));
  const height = Math.max(1, Math.round(originalHeight * scale));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d', { alpha: false });

  if (!context) {
    return {
      name: file.name,
      data: originalData,
      originalSize: file.size,
      compressedSize: file.size,
      width: originalWidth,
      height: originalHeight,
      compressed: false,
    };
  }

  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);
  const compressedData = canvas.toDataURL('image/jpeg', SCREENSHOT_JPEG_QUALITY);
  const compressedBytes = Math.round((compressedData.length - 'data:image/jpeg;base64,'.length) * 0.75);
  const useOriginal = scale === 1 && originalData.length <= compressedData.length;

  return {
    name: useOriginal ? file.name : file.name.replace(/\.(png|webp|jpe?g)$/i, '.jpg'),
    data: useOriginal ? originalData : compressedData,
    originalSize: file.size,
    compressedSize: useOriginal ? file.size : compressedBytes,
    width,
    height,
    compressed: !useOriginal,
  };
}

function renderList(items, emptyMessage = 'Nothing needs attention right now.', renderer = renderListItem) {
  if (!items?.length) return `<p class="muted">${escapeHtml(emptyMessage)}</p>`;
  return `<ul>${items.map((item) => `<li>${renderer(item)}</li>`).join('')}</ul>`;
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
  if (item && typeof item === 'object' && 'title' in item) {
    return renderDashboardItem(item);
  }
  if (item && typeof item === 'object' && 'label' in item) {
    return renderCompactItem(item);
  }
  return escapeHtml(item);
}

function isCompletableTaskItem(item) {
  const taskId = item?.task_id || (item?.record_type === 'task' ? item?.record_id : '');
  const status = String(item?.status || '').toLowerCase();
  return Boolean(taskId) && !['completed', 'cancelled'].includes(status);
}

function isResolvableItem(item) {
  const recordType = String(item?.record_type || '');
  const status = String(item?.status || '').toLowerCase();
  const itemId = item?.resolvable_item_id || (['risk', 'meeting_action'].includes(recordType) ? item?.record_id : '');
  return !isCompletableTaskItem(item)
    && !['completed', 'cancelled', 'resolved'].includes(status)
    && Boolean(itemId)
    && (item?.resolvable || ['risk', 'meeting_action'].includes(recordType));
}

function actionControlButton(item) {
  if (isResolvableItem(item)) {
    const recordType = String(item?.record_type || '');
    const itemId = item.resolvable_item_id || (['risk', 'meeting_action'].includes(recordType) ? item.record_id : '');
    return `<button type="button" class="item-action-button resolve-action" data-resolve-item="${escapeHtml(itemId)}" ${submitting ? 'disabled' : ''}>✓ Resolve</button>`;
  }
  if (!isCompletableTaskItem(item)) return '';
  const taskId = item.task_id || item.record_id;
  return `<button type="button" class="item-action-button complete-action" data-complete-task="${escapeHtml(taskId)}" ${submitting ? 'disabled' : ''}>✓ Complete</button>`;
}

function renderCompactItem(item) {
  const meta = [
    item.owner ? `Owner: ${item.owner}` : '',
    item.status ? humanize(item.status) : '',
    item.due_date ? `Due: ${item.due_date}` : '',
  ].filter(Boolean);
  const actionButton = actionControlButton(item);
  return `
    <span class="item-with-company actionable-row">
      <span class="actionable-copy">
        <span class="actionable-title">
          ${renderCompanyChip(item.company)}
          <span>${escapeHtml(item.label)}</span>
        </span>
        ${meta.length ? `<small>${meta.map(escapeHtml).join(' · ')}</small>` : ''}
      </span>
      ${actionButton ? `<span class="item-action-row">${actionButton}</span>` : ''}
    </span>
  `;
}

function renderDashboardItem(item) {
  const reasons = Array.isArray(item.score_reasons) ? item.score_reasons.filter(Boolean) : [];
  const actionButton = actionControlButton(item);
  return `
    <div class="dashboard-item">
      <div class="dashboard-item-content">
        <div class="dashboard-item-main">
          ${renderCompanyChip(item.company)}
          <strong>${escapeHtml(item.title || item.label || 'Untitled item')}</strong>
          ${item.score ? `<span class="score-pill">${escapeHtml(item.score)}</span>` : ''}
        </div>
        <div class="dashboard-meta">
          ${item.owner ? `<span>Owner: ${escapeHtml(item.owner)}</span>` : ''}
          ${item.status ? `<span>${escapeHtml(humanize(item.status))}</span>` : ''}
          ${item.due_date ? `<span>Due: ${escapeHtml(item.due_date)}</span>` : ''}
        </div>
        ${item.why_it_matters ? `<p>${escapeHtml(item.why_it_matters)}</p>` : ''}
        ${item.recommended_next_action ? `<small>Next: ${escapeHtml(item.recommended_next_action)}</small>` : ''}
        ${item.source?.summary ? `<small>Source: ${escapeHtml(item.source.summary)}</small>` : ''}
        ${reasons.length ? `<div class="score-reasons">${reasons.map((reason) => `<span>${escapeHtml(reason)}</span>`).join('')}</div>` : ''}
        ${actionButton ? `<div class="item-action-row">${actionButton}</div>` : ''}
      </div>
    </div>
  `;
}

function renderBriefingSection(title, items, tone = '') {
  return `
    <article class="briefing-section ${tone}">
      <div class="section-heading">
        <h3>${escapeHtml(title)}</h3>
        <span class="count-pill">${itemCount(items)}</span>
      </div>
      ${renderList(items)}
    </article>
  `;
}

function renderCollapsedBriefingSection(title, items) {
  return `
    <details class="briefing-details">
      <summary><span>${escapeHtml(title)}</span><span class="count-pill">${itemCount(items)}</span></summary>
      ${renderList(items)}
    </details>
  `;
}

function itemCount(items) {
  return Array.isArray(items) ? items.length : 0;
}

function renderPrepSection(title, items, tone = 'neutral', emptyMessage = 'Nothing found.', renderer = renderListItem) {
  const actionListClass = renderer === renderPrepActionItem ? ' prep-action-list' : '';
  return `
    <article class="prep-section prep-${tone}${actionListClass}">
      <div class="prep-section-heading">
        <h4>${escapeHtml(title)}</h4>
        <span class="count-pill">${itemCount(items)}</span>
      </div>
      ${renderList(items, emptyMessage, renderer)}
    </article>
  `;
}

function renderPrepActionItem(item) {
  if (!item || typeof item !== 'object' || !('label' in item)) {
    return `<span class="prep-action-item prep-action-item-static"><span>${renderListItem(item)}</span></span>`;
  }
  const meta = [
    item.owner ? `Owner: ${item.owner}` : '',
    item.status ? humanize(item.status) : '',
    item.due_date ? `Due: ${item.due_date}` : '',
  ].filter(Boolean);
  const actionButton = actionControlButton(item);
  return `
    <span class="prep-action-item ${actionButton ? 'has-action-control' : ''}">
      <span class="prep-action-copy">
        <span class="prep-action-title">
          ${renderCompanyChip(item.company)}
          <span>${escapeHtml(item.label)}</span>
        </span>
        ${meta.length ? `<small>${meta.map(escapeHtml).join(' · ')}</small>` : ''}
      </span>
      <span class="prep-action-control">${actionButton || '<span class="prep-action-spacer" aria-hidden="true"></span>'}</span>
    </span>
  `;
}

function renderAgendaSection(items) {
  return `
    <article class="prep-section prep-agenda">
      <div class="prep-section-heading">
        <h4>Proposed agenda</h4>
        <span class="count-pill">${itemCount(items)}</span>
      </div>
      ${items?.length ? `<ol>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>` : '<p class="muted">No agenda items found.</p>'}
    </article>
  `;
}

function renderCollapsedPrepSection(title, items, tone = 'neutral', emptyMessage = 'Nothing found.') {
  return `
    <details class="briefing-details prep-detail">
      <summary><span>${escapeHtml(title)}</span><span class="count-pill">${itemCount(items)}</span></summary>
      <div class="prep-detail-body prep-${tone}">
        ${renderList(items, emptyMessage)}
      </div>
    </details>
  `;
}

function leadershipFindingItems(review) {
  return (review?.leadership_signals || review?.findings || []).map((finding) => ({
    title: finding.finding || 'Leadership signal',
    label: finding.finding || 'Leadership signal',
    company: review.company || finding.company || '',
    status: finding.severity || 'advisor',
    why_it_matters: [
      finding.category ? humanize(finding.category) : '',
      finding.supported_facts?.[0] || '',
    ].filter(Boolean).join(' · '),
    recommended_next_action: finding.recommended_action || '',
    score_reasons: finding.leadership_principles || [],
    record_type: 'leadership_review',
    record_id: review.id,
  }));
}

function renderLeadershipReviewSummary(review) {
  if (!review) return '';
  const findings = leadershipFindingItems(review).slice(0, 3);
  return `
    <aside class="focus leadership-review-card">
      <strong>Leadership Advisor</strong>
      <p>${escapeHtml(review.executive_summary || 'Advisor review is ready.')}</p>
      ${findings.length ? renderList(findings) : ''}
    </aside>
  `;
}

function prepItems(prep, detailKey, fallbackKey) {
  return prep[detailKey]?.length ? prep[detailKey] : prep[fallbackKey];
}

function renderMeetingPrepOutput(prep) {
  const actionItems = prepItems(prep, 'action_items_detail', 'action_items') || [];
  const openCommitments = prepItems(prep, 'open_commitments_detail', 'open_commitments') || [];
  const overdueTasks = prepItems(prep, 'overdue_tasks_detail', 'overdue_tasks') || [];
  const risks = prepItems(prep, 'risks_detail', 'risks') || [];
  const contextCount = itemCount(prep.related_people) + itemCount(prep.related_strategic_issues)
    + itemCount(prep.related_projects) + itemCount(prep.open_decisions)
    + itemCount(prep.metrics) + itemCount(risks);
  const commandSections = [
    { title: 'Proposed agenda', items: prep.agenda || [], tone: 'agenda', renderer: renderAgendaSection },
    { title: 'Action items', items: actionItems, tone: 'action', empty: 'No open action items.', itemRenderer: renderPrepActionItem },
    { title: 'Questions to ask', items: prep.questions_to_ask || [], tone: 'decision' },
    { title: 'Open decisions', items: prep.open_decisions || [], tone: 'decision', empty: 'No open decisions.' },
    { title: 'Risks', items: risks, tone: 'risk', empty: 'No risks found.' },
    { title: 'Overdue tasks', items: overdueTasks, tone: 'risk', itemRenderer: renderPrepActionItem },
  ].filter((section) => section.title === 'Proposed agenda' || itemCount(section.items) > 0);
  const supportingSections = [
    ['Open commitments', openCommitments, 'action'],
    ['Conflicts or contradictions', prep.conflicts_or_contradictions || [], 'risk'],
    ['People', prep.related_people || [], 'people'],
    ['Strategic issues', prep.related_strategic_issues || [], 'issue'],
    ['Projects', prep.related_projects || [], 'project'],
    ['Metrics', prep.metrics || [], 'metric'],
    ['Sensitive people context', prep.sensitive_people_context || [], 'people'],
    ['Suggested follow-up actions', prep.suggested_follow_up_actions || [], 'action'],
    ['Recent meeting context', prep.recent_meeting_context || [], 'context'],
    ['Recent captured updates', prep.recent_capture_context || [], 'context'],
  ];
  const supportingCount = supportingSections.reduce((count, [, items]) => count + itemCount(items), 0);
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
          <span><strong>${itemCount(actionItems)}</strong> actions</span>
        </div>
      </header>
      <div class="command-grid prep-command-grid">
        ${commandSections.map((section) => (
          section.renderer
            ? section.renderer(section.items)
            : renderPrepSection(section.title, section.items, section.tone, section.empty, section.itemRenderer)
        )).join('')}
      </div>
      <details class="supporting-briefing prep-supporting">
        <summary><span>Supporting context</span><span class="count-pill">${supportingCount}</span></summary>
        <div class="briefing-grid">
          ${supportingSections.map(([title, items, tone]) => renderCollapsedPrepSection(title, items, tone)).join('')}
        </div>
      </details>
    </div>
  `;
}

function currentMemoryType() {
  return memoryTypes.find((type) => type.key === memoryType) || memoryTypes[0];
}

function editableObjectAttributes(item) {
  const attributes = { ...item };
  delete attributes.id;
  delete attributes.is_overdue;
  return attributes;
}

function renderRelatedPanel(related) {
  const groups = Object.entries(related.related || {});
  return `
    <div id="memory-detail-panel" class="editor-panel related-panel">
      <div class="section-heading">
        <div>
          <h3>Related memory</h3>
          <p class="muted">${escapeHtml(related.object?.name || related.object?.title || 'Selected object')}</p>
        </div>
        <button id="related-close" type="button" class="secondary">Close</button>
      </div>
      ${groups.length ? groups.map(([recordType, items]) => `
        <details class="briefing-details" open>
          <summary><span>${escapeHtml(humanize(recordType))}</span><span class="count-pill">${itemCount(items)}</span></summary>
          ${renderList(items.map((item) => ({
            label: item.label,
            company: item.company,
            status: item.reason,
          })), 'No related records.')}
        </details>
      `).join('') : '<p class="muted">No related records found yet.</p>'}
    </div>
  `;
}

function renderInboxItem(item) {
  const reasons = Array.isArray(item.score_reasons) ? item.score_reasons.filter(Boolean) : [];
  const sources = Array.isArray(item.supporting_sources) ? item.supporting_sources.filter(Boolean) : [];
  if (item.source_type === 'leadership_review') {
    return `
      <article class="inbox-item">
        <div class="dashboard-item-main">
          ${renderCompanyChip(item.company)}
          <strong>${escapeHtml(item.title || 'Leadership review ready')}</strong>
          <span class="score-pill">${escapeHtml(item.priority || 'advisor')}</span>
        </div>
        <p>${escapeHtml(item.summary || item.suggested_action || 'Review leadership implications and proposed follow-ups.')}</p>
        ${item.suggested_action ? `<small>Next: ${escapeHtml(item.suggested_action)}</small>` : ''}
        ${reasons.length ? `<div class="score-reasons">${reasons.map((reason) => `<span>${escapeHtml(reason)}</span>`).join('')}</div>` : ''}
        ${item.strategic_questions?.length ? `<details class="inbox-evidence"><summary>Strategic questions</summary>${renderList(item.strategic_questions)}</details>` : ''}
        ${sources.length ? `<details class="inbox-evidence"><summary>Evidence</summary>${renderList(sources.map((source) => source.label || source.text || source.summary || `${source.object_type || source.source_type || 'source'} #${source.object_id || source.source_id || ''}`))}</details>` : ''}
        <div class="inbox-actions">
          <button type="button" class="secondary" data-review-leadership="${escapeHtml(item.source_id)}">Reviewed</button>
          <button type="button" class="secondary" data-apply-leadership-proposals="${escapeHtml(item.source_id)}">Create follow-ups</button>
          <button type="button" class="secondary" data-dismiss-leadership="${escapeHtml(item.source_id)}">Dismiss</button>
        </div>
      </article>
    `;
  }
  if (item.source_type !== 'clarification') {
    const actions = [
      item.source_type === 'task' ? `<button type="button" class="secondary" data-complete-task="${escapeHtml(item.source_id)}">Complete</button>` : '',
      item.source_type === 'resolvable_item' ? `<button type="button" class="secondary" data-resolve-item="${escapeHtml(item.source_id)}">Resolve</button>` : '',
    ].filter(Boolean).join('');
    return `
      <article class="inbox-item">
        <div class="dashboard-item-main">
          ${renderCompanyChip(item.company)}
          <strong>${escapeHtml(item.title || humanize(item.source_type || 'Inbox item'))}</strong>
          <span class="score-pill">${escapeHtml(item.priority || 'medium')}</span>
        </div>
        <p>${escapeHtml(item.summary || item.suggested_action || 'Review this item.')}</p>
        ${item.suggested_action ? `<small>Next: ${escapeHtml(item.suggested_action)}</small>` : ''}
        ${reasons.length ? `<div class="score-reasons">${reasons.map((reason) => `<span>${escapeHtml(reason)}</span>`).join('')}</div>` : ''}
        ${sources.length ? `<details class="inbox-evidence"><summary>Evidence</summary>${renderList(sources.map((source) => source.label || source.text || source.summary || `${source.source_type || 'source'} #${source.source_id || ''}`))}</details>` : ''}
        ${actions ? `<div class="inbox-actions">${actions}</div>` : ''}
      </article>
    `;
  }
  const actionPanel = executiveInboxAction?.id === String(item.source_id) ? renderClarificationActionPanel(item) : '';
  return `
    <article class="inbox-item">
      <div class="dashboard-item-main">
        ${renderCompanyChip(item.company)}
        <strong>${escapeHtml(item.title || 'Clarification needed')}</strong>
        <span class="score-pill">${escapeHtml(item.priority || 'medium')}</span>
      </div>
      <p>${escapeHtml(item.summary || 'Review this item before changing memory.')}</p>
      ${reasons.length ? `<div class="score-reasons">${reasons.map((reason) => `<span>${escapeHtml(reason)}</span>`).join('')}</div>` : ''}
      ${sources.length ? `<details class="inbox-evidence"><summary>Evidence</summary>${renderList(sources.map((source) => source.text || source.summary || `${source.source_type || 'source'} #${source.source_id || ''}`))}</details>` : ''}
      <div class="inbox-actions">
        <button type="button" class="secondary" data-answer-clarification="${escapeHtml(item.source_id)}">Answer</button>
        <button type="button" class="secondary" data-snooze-clarification="${escapeHtml(item.source_id)}">Ask later</button>
        <button type="button" class="secondary" data-unknown-clarification="${escapeHtml(item.source_id)}">Intentionally unknown</button>
        <button type="button" class="secondary" data-dismiss-clarification="${escapeHtml(item.source_id)}">Dismiss</button>
      </div>
      ${actionPanel}
    </article>
  `;
}

function renderClarificationActionPanel(item) {
  const id = String(item.source_id || '');
  const action = executiveInboxAction?.action || '';
  const preview = executiveInboxAction?.preview || null;
  const updates = preview?.proposed_update?.updates || [];
  const summary = clarificationUpdateSummary(updates);
  const title = {
    answer: 'Answer clarification',
    snooze: 'Ask later',
    dismiss: 'Dismiss clarification',
    'intentionally-unknown': 'Mark intentionally unknown',
  }[action] || 'Clarification action';

  if (action === 'answer' && preview) {
    return `
      <div class="inline-action-panel">
        <div class="section-heading">
          <h4>${escapeHtml(title)}</h4>
          <button type="button" class="secondary" data-cancel-clarification-action>Close</button>
        </div>
        <p class="muted">Review the memory update before applying it.</p>
        ${summary.length ? `<ul>${summary.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>` : '<p class="muted">No field changes were found.</p>'}
        <div class="button-row">
          <button type="button" data-confirm-clarification="${escapeHtml(id)}" ${submitting ? 'disabled' : ''}>${submitting ? 'Saving…' : 'Confirm update'}</button>
          <button type="button" class="secondary" data-cancel-clarification-action>Keep as preview</button>
        </div>
      </div>
    `;
  }

  if (action === 'answer') {
    return `
      <form class="inline-action-panel" data-clarification-form data-clarification-id="${escapeHtml(id)}" data-clarification-action="answer">
        <div class="section-heading">
          <h4>${escapeHtml(title)}</h4>
          <button type="button" class="secondary" data-cancel-clarification-action>Cancel</button>
        </div>
        <label>Answer<textarea name="answer" rows="3" required placeholder="Type the missing context or correction."></textarea></label>
        <label>Note<textarea name="note" rows="2" placeholder="Optional context for your future self."></textarea></label>
        <button type="submit" ${submitting ? 'disabled' : ''}>${submitting ? 'Previewing…' : 'Preview update'}</button>
      </form>
    `;
  }

  if (action === 'snooze') {
    return `
      <form class="inline-action-panel" data-clarification-form data-clarification-id="${escapeHtml(id)}" data-clarification-action="snooze">
        <div class="section-heading">
          <h4>${escapeHtml(title)}</h4>
          <button type="button" class="secondary" data-cancel-clarification-action>Cancel</button>
        </div>
        <label>Ask again after<input name="snoozed_until" type="datetime-local" value="${escapeHtml(tomorrowDateTimeLocalValue())}" required /></label>
        <label>Note<textarea name="note" rows="2" placeholder="Optional reason for snoozing."></textarea></label>
        <button type="submit" ${submitting ? 'disabled' : ''}>${submitting ? 'Saving…' : 'Ask later'}</button>
      </form>
    `;
  }

  return `
    <form class="inline-action-panel" data-clarification-form data-clarification-id="${escapeHtml(id)}" data-clarification-action="${escapeHtml(action)}">
      <div class="section-heading">
        <h4>${escapeHtml(title)}</h4>
        <button type="button" class="secondary" data-cancel-clarification-action>Cancel</button>
      </div>
      <label>${action === 'intentionally-unknown' ? 'Note' : 'Reason'}<textarea name="reason" rows="2" placeholder="${action === 'intentionally-unknown' ? 'Optional note.' : 'Optional reason.'}"></textarea></label>
      <button type="submit" ${submitting ? 'disabled' : ''}>${submitting ? 'Saving…' : escapeHtml(action === 'dismiss' ? 'Dismiss' : 'Mark intentionally unknown')}</button>
    </form>
  `;
}

let active = 'capture';
let briefing = null;
let meetingPrep = null;
let searchResults = null;
let captureText = '';
let screenshots = [];
let screenshotsProcessing = false;
let capturePhase = '';
let searchQuery = '';
let meetingQuery = '';
let memoryType = 'people';
let memoryCompanyFilter = '';
let memoryObjects = null;
let memoryLoading = false;
let memoryEdit = null;
let memoryRelated = null;
let memoryMessage = '';
let executiveInbox = null;
let executiveInboxLoading = false;
let executiveInboxMessage = '';
let executiveInboxAction = null;
let backupImportMode = 'merge';
let captureResult = null;
let classificationResult = null;
let selectedUpdateIndices = [];
let captureObservability = null;
let captureObservabilityLoading = false;
let captureAuditList = null;
let captureAuditLoading = false;
let captureAuditDetail = null;
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

async function loadCaptureAudit(captureId = null) {
  if (captureAuditLoading) return;
  captureAuditLoading = true;
  try {
    if (captureId) {
      captureAuditDetail = await safeJsonFetch(apiUrl(`/captures/${captureId}/audit`));
    } else {
      captureAuditList = await safeJsonFetch(apiUrl('/captures?limit=25'));
    }
    apiError = null;
  } catch (error) {
    setApiError(error.message);
  } finally {
    captureAuditLoading = false;
    render();
  }
}

async function loadMemoryObjects() {
  memoryLoading = true;
  memoryMessage = '';
  try {
    const params = new URLSearchParams();
    if (memoryCompanyFilter.trim()) params.set('company', memoryCompanyFilter.trim());
    const query = params.toString();
    memoryObjects = await safeJsonFetch(apiUrl(`/objects/${memoryType}${query ? `?${query}` : ''}`));
    apiError = null;
  } catch (error) {
    setApiError(error.message);
  } finally {
    memoryLoading = false;
    render();
  }
}

async function openAuditLinkedRecord(recordType, recordId, mode = 'view') {
  const mappedType = auditRecordTypeToMemoryType[recordType] || recordType;
  const id = Number(recordId);
  if (!mappedType || !id) {
    setApiError('This audit row is not linked to a saved memory record.');
    return;
  }
  submitting = true;
  render();
  try {
    const objects = await safeJsonFetch(apiUrl(`/objects/${mappedType}`));
    const item = (objects.items || []).find((candidate) => Number(candidate.id) === id);
    if (!item) {
      throw new Error(`Saved ${humanize(recordType)} #${id} was not found.`);
    }
    memoryType = mappedType;
    memoryObjects = objects;
    memoryCompanyFilter = '';
    memoryMessage = '';
    memoryRelated = null;
    memoryEdit = null;
    if (mode === 'edit') {
      const selectedType = currentMemoryType();
      memoryEdit = {
        id,
        title: item[selectedType.titleField] || `${selectedType.label} #${id}`,
        text: JSON.stringify(editableObjectAttributes(item), null, 2),
      };
    } else if (mode === 'related') {
      memoryRelated = await safeJsonFetch(apiUrl(`/objects/${mappedType}/${id}/related`));
    } else {
      memoryMessage = `Opened ${humanize(recordType)} #${id}.`;
    }
    active = 'memory';
    apiError = null;
  } catch (error) {
    setApiError(error.message);
  } finally {
    submitting = false;
  }
  render();
  if (mode === 'edit' || mode === 'related') scrollMemoryDetailIntoView();
}

function reopenAuditCaptureForReview(mode = 'review') {
  const rawText = captureAuditDetail?.capture?.raw_text || '';
  if (!rawText.trim()) {
    setApiError('This audit does not include capture text to review again.');
    return;
  }
  captureText = mode === 'tasks'
    ? `Create qualified tasks and follow-ups from this capture:\n\n${rawText}`
    : rawText;
  screenshots = [];
  classificationResult = null;
  selectedUpdateIndices = [];
  captureResult = null;
  capturePhase = '';
  active = 'capture';
  apiError = null;
  render();
}

async function loadExecutiveInbox() {
  executiveInboxLoading = true;
  executiveInboxMessage = '';
  try {
    executiveInbox = await safeJsonFetch(apiUrl('/executive-inbox'));
    apiError = null;
  } catch (error) {
    setApiError(error.message);
  } finally {
    executiveInboxLoading = false;
    render();
  }
}

function invalidateGeneratedViews() {
  executiveInbox = null;
  briefing = null;
  meetingPrep = null;
  searchResults = null;
}

function scrollMemoryDetailIntoView() {
  window.requestAnimationFrame(() => {
    app.querySelector('#memory-detail-panel')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  });
}

function openClarificationAction(id, action) {
  if (!id || submitting) return;
  executiveInboxAction = {
    id: String(id),
    action,
    preview: null,
  };
  executiveInboxMessage = '';
  render();
}

function cancelClarificationAction() {
  executiveInboxAction = null;
  render();
}

function tomorrowDateTimeLocalValue() {
  const date = new Date(Date.now() + 24 * 60 * 60 * 1000);
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function clarificationUpdateSummary(updates) {
  return (updates || []).map((update) => {
    const fields = Object.entries(update.attributes || {})
      .map(([field, value]) => `${humanize(field)}: ${Array.isArray(value) ? value.join(', ') : value}`)
      .join(', ');
    return `${humanize(update.object_type || 'record')} #${update.object_id || ''}${fields ? ` — ${fields}` : ''}`;
  }).filter(Boolean);
}

async function submitClarificationAction(form) {
  const id = form.getAttribute('data-clarification-id');
  const action = form.getAttribute('data-clarification-action');
  if (!id || !action || submitting) return;
  const formData = new FormData(form);
  submitting = true;
  render();
  try {
    if (action === 'answer') {
      const answer = String(formData.get('answer') || '').trim();
      const note = String(formData.get('note') || '').trim();
      const preview = await safeJsonFetch(apiUrl(`/clarifications/${id}/answer`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer, note }),
      });
      executiveInboxAction = { id: String(id), action, preview: preview.clarification };
      executiveInboxMessage = 'Answer preview ready.';
    } else if (action === 'snooze') {
      const rawDate = String(formData.get('snoozed_until') || '').trim();
      const snoozedUntil = rawDate ? new Date(rawDate).toISOString() : '';
      await safeJsonFetch(apiUrl(`/clarifications/${id}/snooze`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          snoozed_until: snoozedUntil,
          note: String(formData.get('note') || '').trim(),
        }),
      });
      executiveInboxMessage = 'Clarification snoozed.';
      executiveInboxAction = null;
      invalidateGeneratedViews();
    } else {
      await safeJsonFetch(apiUrl(`/clarifications/${id}/${action}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: String(formData.get('reason') || '').trim() }),
      });
      executiveInboxMessage = action === 'dismiss' ? 'Clarification dismissed.' : 'Clarification marked intentionally unknown.';
      executiveInboxAction = null;
      invalidateGeneratedViews();
    }
    apiError = null;
  } catch (error) {
    setApiError(error.message);
  } finally {
    submitting = false;
  }
  render();
}

async function confirmClarificationAnswer(id) {
  if (!id || submitting) return;
  submitting = true;
  render();
  try {
    await safeJsonFetch(apiUrl(`/clarifications/${id}/confirm`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    executiveInboxMessage = 'Clarification answered.';
    executiveInboxAction = null;
    invalidateGeneratedViews();
    apiError = null;
  } catch (error) {
    setApiError(error.message);
  } finally {
    submitting = false;
  }
  render();
}

async function updateLeadershipReview(id, action) {
  if (!id || submitting) return;
  submitting = true;
  render();
  try {
    const path = action === 'proposals'
      ? `/leadership-reviews/${id}/proposals`
      : `/leadership-reviews/${id}/${action}`;
    const options = action === 'proposals'
      ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ finding_indexes: [] }),
        }
      : { method: 'POST' };
    const result = await safeJsonFetch(apiUrl(path), options);
    executiveInboxMessage = action === 'dismiss'
      ? 'Leadership review dismissed.'
      : action === 'proposals'
        ? `${result.applied?.length || 0} advisor follow-up${result.applied?.length === 1 ? '' : 's'} created.`
        : 'Leadership review marked reviewed.';
    invalidateGeneratedViews();
    apiError = null;
  } catch (error) {
    setApiError(error.message);
  } finally {
    submitting = false;
  }
  render();
}

async function completeTaskFromControl(taskId) {
  if (!taskId || submitting) return;
  submitting = true;
  render();
  try {
    await safeJsonFetch(apiUrl(`/tasks/${taskId}/complete`), { method: 'POST' });
    memoryObjects = null;
    executiveInbox = null;
    searchResults = null;
    apiError = null;
    if (active === 'briefing') {
      briefing = null;
    } else if (active === 'prep' && meetingPrep) {
      const meeting = meetingQuery.trim() || meetingPrep.meeting || 'Executive meeting';
      meetingPrep = await safeJsonFetch(apiUrl('/meeting-prep'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meeting }),
      });
    } else {
      briefing = null;
      meetingPrep = null;
    }
    memoryMessage = active === 'memory' ? 'Task completed.' : '';
  } catch (error) {
    setApiError(error.message);
  } finally {
    submitting = false;
  }
  render();
}

async function resolveItemFromControl(itemId) {
  const id = String(itemId || '').trim();
  if (!id || submitting) return;
  submitting = true;
  render();
  try {
    await safeJsonFetch(apiUrl(`/resolvable-items/${id}/resolve`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: 'Resolved from briefing or meeting prep control.' }),
    });
    memoryObjects = null;
    executiveInbox = null;
    searchResults = null;
    apiError = null;
    if (active === 'briefing') {
      briefing = null;
    } else if (active === 'prep' && meetingPrep) {
      const meeting = meetingQuery.trim() || meetingPrep.meeting || 'Executive meeting';
      meetingPrep = await safeJsonFetch(apiUrl('/meeting-prep'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meeting }),
      });
    } else {
      briefing = null;
      meetingPrep = null;
    }
    memoryMessage = active === 'memory' ? 'Item resolved.' : '';
  } catch (error) {
    setApiError(error.message);
  } finally {
    submitting = false;
  }
  render();
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

  app.querySelectorAll('[data-complete-task]').forEach((button) => {
    button.addEventListener('click', async () => {
      await completeTaskFromControl(button.getAttribute('data-complete-task'));
    });
  });

  app.querySelectorAll('[data-resolve-item]').forEach((button) => {
    button.addEventListener('click', async () => {
      await resolveItemFromControl(button.getAttribute('data-resolve-item'));
    });
  });

  if (active === 'inbox') {
    app.querySelector('#inbox-refresh')?.addEventListener('click', () => {
      executiveInbox = null;
      loadExecutiveInbox();
    });
    app.querySelectorAll('[data-answer-clarification]').forEach((button) => {
      button.addEventListener('click', () => openClarificationAction(button.getAttribute('data-answer-clarification'), 'answer'));
    });
    app.querySelectorAll('[data-snooze-clarification]').forEach((button) => {
      button.addEventListener('click', () => openClarificationAction(button.getAttribute('data-snooze-clarification'), 'snooze'));
    });
    app.querySelectorAll('[data-unknown-clarification]').forEach((button) => {
      button.addEventListener('click', () => openClarificationAction(button.getAttribute('data-unknown-clarification'), 'intentionally-unknown'));
    });
    app.querySelectorAll('[data-dismiss-clarification]').forEach((button) => {
      button.addEventListener('click', () => openClarificationAction(button.getAttribute('data-dismiss-clarification'), 'dismiss'));
    });
    app.querySelectorAll('[data-review-leadership]').forEach((button) => {
      button.addEventListener('click', async () => {
        await updateLeadershipReview(button.getAttribute('data-review-leadership'), 'review');
      });
    });
    app.querySelectorAll('[data-dismiss-leadership]').forEach((button) => {
      button.addEventListener('click', async () => {
        await updateLeadershipReview(button.getAttribute('data-dismiss-leadership'), 'dismiss');
      });
    });
    app.querySelectorAll('[data-apply-leadership-proposals]').forEach((button) => {
      button.addEventListener('click', async () => {
        await updateLeadershipReview(button.getAttribute('data-apply-leadership-proposals'), 'proposals');
      });
    });
    app.querySelectorAll('[data-clarification-form]').forEach((form) => {
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        await submitClarificationAction(form);
      });
    });
    app.querySelectorAll('[data-confirm-clarification]').forEach((button) => {
      button.addEventListener('click', async () => {
        await confirmClarificationAnswer(button.getAttribute('data-confirm-clarification'));
      });
    });
    app.querySelectorAll('[data-cancel-clarification-action]').forEach((button) => {
      button.addEventListener('click', cancelClarificationAction);
    });
  }

  if (active === 'capture') {
    const textarea = app.querySelector('textarea');
    const button = app.querySelector('#capture-submit');
    const screenshotInput = app.querySelector('#screenshot-input');
    if (textarea) {
      textarea.value = captureText;
      textarea.addEventListener('input', (event) => {
        captureText = event.target.value;
        if (button) {
          button.disabled = submitting || screenshotsProcessing || (!captureText.trim() && !screenshots.length);
          button.textContent = screenshotsProcessing ? 'Preparing screenshots...' : screenshots.length ? `Analyze and review ${screenshots.length} screenshot${screenshots.length === 1 ? '' : 's'}` : 'Classify and review updates';
        }
        if (classificationResult) {
          classificationResult = null;
          selectedUpdateIndices = [];
          app.querySelector('#classification-review')?.remove();
        }
        captureResult = null;
      });
    }
    screenshotInput?.addEventListener('change', async (event) => {
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
      const oversized = files.find((file) => file.size > SCREENSHOT_MAX_UPLOAD_BYTES);
      if (oversized) {
        setApiError('Each screenshot must be 12 MB or smaller.');
        return;
      }
      try {
        screenshotsProcessing = true;
        capturePhase = 'preparing';
        apiError = null;
        render();
        const loadedScreenshots = await Promise.all(files.map((file) => prepareScreenshot(file)));
        screenshots = [...screenshots, ...loadedScreenshots];
        classificationResult = null;
        selectedUpdateIndices = [];
        captureResult = null;
      } catch (error) {
        setApiError(error.message);
      } finally {
        screenshotsProcessing = false;
        capturePhase = '';
        if (event.target) event.target.value = '';
        render();
      }
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
        if ((!captureText.trim() && !screenshots.length) || submitting || screenshotsProcessing) return;
        submitting = true;
        capturePhase = screenshots.length ? 'analyzing_screenshots' : 'classifying_text';
        classificationResult = null;
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
          capturePhase = '';
        }
        render();
      });
    }

    const confirmButton = app.querySelector('#capture-confirm');
    if (confirmButton) {
      confirmButton.addEventListener('click', async () => {
        if (submitting) return;
        submitting = true;
        capturePhase = 'saving_updates';
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
              capture_id: classificationResult?.capture_id || null,
            }),
          });
          // Generated outputs are disposable views over memory. Invalidate them
          // whenever the underlying memory changes.
          briefing = null;
          executiveInbox = null;
          meetingPrep = null;
          searchResults = null;
          captureObservability = null;
          captureAuditList = null;
          captureAuditDetail = null;
          classificationResult = null;
          selectedUpdateIndices = [];
          captureText = '';
          screenshots = [];
          apiError = null;
        } catch (error) {
          setApiError(error.message);
        } finally {
          submitting = false;
          capturePhase = '';
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
    app.querySelector('[data-open-capture-audit]')?.addEventListener('click', () => {
      const captureId = Number(captureResult?.capture_id || 0);
      if (!captureId) return;
      active = 'captureAudit';
      captureAuditDetail = null;
      loadCaptureAudit(captureId);
      render();
    });
  }

  if (active === 'captureAudit') {
    app.querySelectorAll('[data-load-capture-audit]').forEach((button) => {
      button.addEventListener('click', () => {
        const captureId = Number(button.getAttribute('data-load-capture-audit'));
        if (captureId) loadCaptureAudit(captureId);
      });
    });
    app.querySelector('[data-refresh-capture-audits]')?.addEventListener('click', () => {
      captureAuditList = null;
      loadCaptureAudit();
    });
    app.querySelectorAll('[data-audit-memory-action]').forEach((button) => {
      button.addEventListener('click', () => {
        openAuditLinkedRecord(
          button.getAttribute('data-record-type'),
          button.getAttribute('data-record-id'),
          button.getAttribute('data-audit-memory-action'),
        );
      });
    });
    app.querySelector('[data-audit-review-again]')?.addEventListener('click', () => {
      reopenAuditCaptureForReview('review');
    });
    app.querySelector('[data-audit-create-tasks]')?.addEventListener('click', () => {
      reopenAuditCaptureForReview('tasks');
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
      memoryRelated = null;
      memoryMessage = '';
      render();
    });

    const companyFilterInput = app.querySelector('#memory-company-filter');
    companyFilterInput?.addEventListener('input', (event) => {
      memoryCompanyFilter = event.target.value;
    });
    app.querySelector('#memory-filter-apply')?.addEventListener('click', () => {
      memoryObjects = null;
      memoryEdit = null;
      memoryRelated = null;
      render();
    });
    companyFilterInput?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') app.querySelector('#memory-filter-apply')?.click();
    });
    app.querySelector('#memory-filter-clear')?.addEventListener('click', () => {
      memoryCompanyFilter = '';
      memoryObjects = null;
      memoryEdit = null;
      memoryRelated = null;
      render();
    });

    app.querySelector('#backup-mode')?.addEventListener('change', (event) => {
      backupImportMode = event.target.value;
    });

    app.querySelector('#backup-export')?.addEventListener('click', async () => {
      if (submitting) return;
      submitting = true;
      render();
      try {
        const backup = await safeJsonFetch(apiUrl('/backup/export'));
        const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        const date = new Date().toISOString().slice(0, 10);
        anchor.href = url;
        anchor.download = `executiveos-backup-${date}.json`;
        anchor.click();
        URL.revokeObjectURL(url);
        memoryMessage = 'Backup exported.';
        apiError = null;
      } catch (error) {
        setApiError(error.message);
      } finally {
        submitting = false;
      }
      render();
    });

    app.querySelector('#backup-import-file')?.addEventListener('change', async (event) => {
      const file = event.target.files?.[0];
      if (!file || submitting) return;
      submitting = true;
      render();
      try {
        const text = await file.text();
        const backup = JSON.parse(text);
        const result = await safeJsonFetch(apiUrl('/backup/import'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ backup, mode: backupImportMode }),
        });
        memoryObjects = null;
        memoryRelated = null;
        memoryEdit = null;
        executiveInbox = null;
        briefing = null;
        meetingPrep = null;
        searchResults = null;
        memoryMessage = `${result.total_imported || 0} backup records imported.`;
        apiError = null;
      } catch (error) {
        setApiError(error.message);
      } finally {
        submitting = false;
        event.target.value = '';
      }
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
        memoryRelated = null;
        memoryMessage = '';
        render();
        scrollMemoryDetailIntoView();
      });
    });

    app.querySelectorAll('[data-related-object]').forEach((button) => {
      button.addEventListener('click', async () => {
        if (submitting) return;
        const id = Number(button.getAttribute('data-related-object'));
        let shouldScroll = false;
        submitting = true;
        render();
        try {
          memoryRelated = await safeJsonFetch(apiUrl(`/objects/${memoryType}/${id}/related`));
          memoryEdit = null;
          memoryMessage = '';
          apiError = null;
          shouldScroll = true;
        } catch (error) {
          setApiError(error.message);
        } finally {
          submitting = false;
        }
        render();
        if (shouldScroll) scrollMemoryDetailIntoView();
      });
    });

    app.querySelector('#related-close')?.addEventListener('click', () => {
      memoryRelated = null;
      render();
    });

    app.querySelectorAll('[data-reopen-task]').forEach((button) => {
      button.addEventListener('click', async () => {
        if (submitting) return;
        const id = button.getAttribute('data-reopen-task');
        submitting = true;
        render();
        try {
          await safeJsonFetch(apiUrl(`/tasks/${id}/reopen`), { method: 'POST' });
          memoryObjects = null;
          memoryMessage = 'Task reopened.';
          executiveInbox = null;
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
        memoryRelated = null;
        memoryObjects = null;
        memoryMessage = 'Memory object updated.';
        executiveInbox = null;
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
        memoryRelated = null;
        memoryObjects = null;
        memoryMessage = 'Memory object deleted.';
        executiveInbox = null;
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

function renderCaptureProgress() {
  const screenshotsLabel = screenshots.length
    ? `${screenshots.length} screenshot${screenshots.length === 1 ? '' : 's'}`
    : 'capture';
  const states = {
    preparing: {
      title: 'Preparing screenshots',
      detail: 'Compressing images in your browser before upload.',
    },
    analyzing_screenshots: {
      title: 'Analyzing screenshot capture',
      detail: `Uploading ${screenshotsLabel} and extracting structured updates. This can take up to a minute.`,
    },
    classifying_text: {
      title: 'Classifying capture',
      detail: 'Organizing the text into reviewable updates.',
    },
    saving_updates: {
      title: 'Saving approved updates',
      detail: 'Writing approved items into executive memory.',
    },
  };
  const state = states[capturePhase];
  if (!state) return '';
  return `
    <div class="capture-progress" role="status" aria-live="polite">
      <div class="capture-progress-header">
        <strong>${escapeHtml(state.title)}</strong>
        <span>${escapeHtml(state.detail)}</span>
      </div>
      <div class="capture-progress-track" role="progressbar" aria-label="${escapeHtml(state.title)}">
        <span></span>
      </div>
    </div>
  `;
}

function renderPanel() {
  if (active === 'capture') {
    if (!captureObservability && !captureObservabilityLoading) {
      captureObservabilityLoading = true;
      safeJsonFetch(apiUrl('/capture/observability'))
        .then((data) => {
          captureObservability = data;
        })
        .catch(() => {})
        .finally(() => {
          captureObservabilityLoading = false;
          render();
        });
    }
    return `
      <h2>Capture</h2>
      <p>Enter natural language or attach a screenshot, then review and approve the structured updates.</p>
      <label for="capture-input" class="sr-only">Executive update</label>
      <textarea id="capture-input" rows="6" placeholder="Example: Morgan owns the Zephyr expansion. The main risk is distributor capacity."></textarea>
      <div class="screenshot-controls">
        <label class="file-button" for="screenshot-input">Attach screenshots</label>
        <input id="screenshot-input" type="file" accept="image/png,image/jpeg,image/webp" multiple />
        <span class="muted">PNG, JPEG, or WebP · compressed before analysis · 5 maximum</span>
      </div>
      ${screenshots.length ? `<div class="screenshot-preview-grid">${screenshots.map((screenshot, index) => `
        <div class="screenshot-preview"><img src="${screenshot.data}" alt="Screenshot ${index + 1} selected for capture" /><div><strong>${escapeHtml(screenshot.name)}</strong><p class="muted">${escapeHtml(`${screenshot.width || ''}${screenshot.width && screenshot.height ? ' x ' : ''}${screenshot.height || ''}${screenshot.compressedSize ? ` · ${formatBytes(screenshot.compressedSize)}` : ''}${screenshot.originalSize && screenshot.compressedSize && screenshot.compressedSize < screenshot.originalSize ? ` from ${formatBytes(screenshot.originalSize)}` : ''}`)}</p><button data-remove-screenshot="${index}" type="button" class="secondary">Remove</button></div></div>
      `).join('')}<button id="screenshots-clear" type="button" class="secondary">Remove all</button></div>` : ''}
      ${renderCaptureProgress()}
      <button id="capture-submit" style="margin-top: 12px;" ${submitting || screenshotsProcessing || (!captureText.trim() && !screenshots.length) ? 'disabled' : ''}>${screenshotsProcessing ? 'Preparing screenshots...' : submitting ? 'Working…' : screenshots.length ? `Analyze and review ${screenshots.length} screenshot${screenshots.length === 1 ? '' : 's'}` : 'Classify and review updates'}</button>
      ${classificationResult ? `
        <div id="classification-review" style="margin-top: 12px;">
          <div class="section-heading">
            <h3>Suggested updates</h3>
            <span class="badge">${classificationResult.classification_source === 'ai' ? 'AI organized' : 'Local preview'}</span>
          </div>
          ${classificationResult.next_best_action ? `<div class="follow-ups"><strong>Next best action</strong>${renderList([classificationResult.next_best_action])}</div>` : ''}
          ${classificationResult.diagnostics ? `
            <div class="capture-quality">
              <span><strong>${escapeHtml(classificationResult.diagnostics.average_task_quality || 0)}</strong> task quality</span>
              <span><strong>${escapeHtml(classificationResult.diagnostics.low_quality_task_count || 0)}</strong> weak tasks</span>
              ${classificationResult.diagnostics.fallback_reason ? `<span><strong>Fallback</strong> ${escapeHtml(classificationResult.diagnostics.fallback_reason)}</span>` : ''}
            </div>
          ` : ''}
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
              ${item.quality_score ? `<small>Quality score: ${escapeHtml(item.quality_score)}${item.quality_notes?.length ? ` · ${escapeHtml(item.quality_notes.join(', '))}` : ''}</small>` : ''}
              ${item.next_best_action ? `<small>Next: ${escapeHtml(item.next_best_action)}</small>` : ''}
              ${item.details ? `<small>${escapeHtml(item.details)}</small>` : ''}</span>
            </label>
          `).join('') : '<p class="muted">No reliable structured updates were found. Add a person, company, project, decision, or metric and try again.</p>'}
          ${classificationResult.follow_ups?.length ? `<div class="follow-ups"><strong>Useful follow-up</strong>${renderList(classificationResult.follow_ups)}</div>` : ''}
          ${classificationResult.suggested_updates.length ? `<button id="capture-confirm" style="margin-top: 12px;" ${submitting || selectedUpdateIndices.length === 0 ? 'disabled' : ''}>${submitting ? 'Saving…' : `Save ${selectedUpdateIndices.length} approved update${selectedUpdateIndices.length === 1 ? '' : 's'}`}</button>` : ''}
        </div>
      ` : ''}
      ${captureResult ? `
        <p class="success" role="status">${escapeHtml(captureResult.saved_count)} approved update${captureResult.saved_count === 1 ? '' : 's'} saved. Briefing, meeting prep, and search will now use the refreshed memory.</p>
        ${captureResult.capture_id ? `<button type="button" class="secondary" data-open-capture-audit>View capture audit</button>` : ''}
        ${captureResult.leadership_review ? renderLeadershipReviewSummary(captureResult.leadership_review) : ''}
        ${captureResult.leadership_review_error ? `<p class="muted">${escapeHtml(captureResult.leadership_review_error)}</p>` : ''}
      ` : ''}
      ${captureObservability ? `
        <details class="backup-panel">
          <summary><span>Capture quality</span></summary>
          <div class="capture-quality">
            <span><strong>${escapeHtml(captureObservability.total_captures)}</strong> captures</span>
            <span><strong>${escapeHtml(captureObservability.ai_captures)}</strong> AI</span>
            <span><strong>${escapeHtml(captureObservability.fallback_captures)}</strong> fallback</span>
            <span><strong>${escapeHtml(Math.round((captureObservability.fallback_rate || 0) * 100))}%</strong> fallback rate</span>
            <span><strong>${escapeHtml(captureObservability.saved_updates)}</strong> saved updates</span>
          </div>
        </details>
      ` : ''}
    `;
  }

  if (active === 'captureAudit') {
    if (!captureAuditList && !captureAuditLoading) {
      loadCaptureAudit();
    }
    const detail = captureAuditDetail;
    return `
      <h2>Capture Audit</h2>
      <p>Compare original capture input, AI interpretation, approved mutations, and actual saved values.</p>
      ${captureAuditLoading ? '<p>Loading capture audit…</p>' : ''}
      ${detail ? `
        <div class="backup-panel">
          <div class="section-heading">
            <h3>Capture #${escapeHtml(detail.capture?.id || '')}</h3>
            <span class="badge">${escapeHtml(detail.capture?.classification_source || 'unknown')}</span>
          </div>
          <div class="button-row audit-top-actions">
            <button type="button" class="secondary" data-audit-review-again>Review again in Capture</button>
            <button type="button" class="secondary" data-audit-create-tasks>Create tasks from capture</button>
          </div>
          <p><strong>Original input</strong></p>
          <p>${escapeHtml(detail.capture?.raw_text || '')}</p>
          ${detail.interpretation ? `
            <p><strong>AI interpretation</strong></p>
            <p>${escapeHtml(detail.interpretation.capture_summary || '')}</p>
            <div class="capture-quality">
              <span><strong>${escapeHtml(detail.interpretation.executive_intent || 'Intent')}</strong> intent</span>
              <span><strong>${escapeHtml(detail.interpretation.primary_company || 'No company')}</strong> company</span>
              <span><strong>${escapeHtml(detail.interpretation.confidence || 'Unknown')}</strong> confidence</span>
              <span><strong>${escapeHtml(detail.interpretation.prompt_version || '')}</strong> prompt</span>
            </div>
            ${detail.next_best_action ? `<div class="follow-ups"><strong>Next best action</strong>${renderList([detail.next_best_action])}</div>` : ''}
            ${detail.diagnostics ? `
              <div class="capture-quality">
                <span><strong>${escapeHtml(detail.diagnostics.average_task_quality || 0)}</strong> task quality</span>
                <span><strong>${escapeHtml(detail.diagnostics.low_quality_task_count || 0)}</strong> weak tasks</span>
                ${detail.diagnostics.fallback_reason ? `<span><strong>Fallback</strong> ${escapeHtml(detail.diagnostics.fallback_reason)}</span>` : ''}
              </div>
            ` : ''}
          ` : ''}
          <div class="audit-table" role="table" aria-label="Capture comparison">
            <div class="audit-row audit-header" role="row">
              <span>Original input</span>
              <span>AI interpretation</span>
              <span>Approved mutation</span>
              <span>Actual saved value</span>
              <span>Omitted or unresolved</span>
              <span>Actions</span>
            </div>
            ${(detail.comparison || []).map((row) => `
              <div class="audit-row" role="row">
                <span>${escapeHtml(row.original_input || '')}</span>
                <span>${escapeHtml(row.ai_interpretation || '')}</span>
                <span><pre>${escapeHtml(JSON.stringify(row.approved_mutation || {}, null, 2))}</pre></span>
                <span><pre>${escapeHtml(JSON.stringify(row.actual_saved_value || {}, null, 2))}</pre></span>
                <span>${escapeHtml([...(row.omitted_or_unresolved_context?.missing_material_fields || []), row.omitted_or_unresolved_context?.uncertainty || '', row.omitted_or_unresolved_context?.status || ''].filter(Boolean).join(' · '))}</span>
                <span class="audit-actions">
                  ${row.linked_record?.type && row.linked_record?.id ? `
                    <button type="button" class="secondary" data-audit-memory-action="view" data-record-type="${escapeHtml(row.linked_record.type)}" data-record-id="${escapeHtml(row.linked_record.id)}">View</button>
                    <button type="button" class="secondary" data-audit-memory-action="edit" data-record-type="${escapeHtml(row.linked_record.type)}" data-record-id="${escapeHtml(row.linked_record.id)}">Edit</button>
                    <button type="button" class="secondary" data-audit-memory-action="related" data-record-type="${escapeHtml(row.linked_record.type)}" data-record-id="${escapeHtml(row.linked_record.id)}">Related</button>
                  ` : '<small class="muted">No saved record</small>'}
                </span>
              </div>
            `).join('') || `
              <div class="empty-notice" role="status">
                No approved mutation rows were recorded for this capture. Use the actions above to review it again or extract tasks from the original input.
              </div>
            `}
          </div>
        </div>
      ` : ''}
      <div class="backup-panel">
        <div class="section-heading">
          <h3>Recent captures</h3>
          <button type="button" class="secondary" data-refresh-capture-audits>Refresh</button>
        </div>
        ${(captureAuditList?.items || []).map((capture) => `
          <div class="memory-row">
            <div>
              <strong>Capture #${escapeHtml(capture.id)}</strong>
              <p>${escapeHtml(capture.raw_text || '')}</p>
              <small>${escapeHtml(capture.created_at || '')} · ${escapeHtml(capture.classification_source || 'unknown')} · ${escapeHtml(capture.saved_count || 0)} saved</small>
            </div>
            <button type="button" class="secondary" data-load-capture-audit="${escapeHtml(capture.id)}">Open audit</button>
          </div>
        `).join('') || '<p class="muted">No captures found yet.</p>'}
      </div>
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
    const leadershipItems = leadershipFindingItems(briefing.leadership_advisor);
    const commandSections = [
      ['Leadership Advisor', leadershipItems, 'leadership'],
      ['Needs Your Attention', briefing.needs_your_attention, 'needs-attention'],
      ['Delegate or Follow Up', briefing.delegate_or_follow_up, 'delegate'],
      ['Overdue', briefing.overdue, 'overdue'],
      ['Blocked or Waiting', briefing.blocked_or_waiting, 'blocked'],
      ['Changed Since Last Briefing', briefing.changed_since_last_briefing, 'changed'],
      ['Upcoming', briefing.upcoming, 'upcoming'],
      ['Clarifications Needed', briefing.clarifications_needed, 'clarification'],
    ].filter(([, items]) => itemCount(items) > 0);
    const supportingSections = [
      ['Top Priorities', briefing.top_priorities],
      ['Strategic Issues', briefing.strategic_issues],
      ['Meetings Today', briefing.meetings_today],
      ['Open Decisions', briefing.open_decisions],
      ['People Needing Attention', briefing.people_needing_attention],
      ['Risks', briefing.risks],
      ['Recent Updates', briefing.recent_updates],
    ];

    return `
      <h2>Morning Briefing</h2>
      <aside class="focus"><strong>Recommended focus</strong><p>${escapeHtml(briefing.recommended_focus || 'Review the priorities above.')}</p></aside>
      <div class="command-grid">
        ${commandSections.length ? commandSections.map(([title, items, tone]) => renderBriefingSection(title, items || [], tone)).join('') : '<p class="muted">Nothing urgent needs attention right now.</p>'}
      </div>
      <details class="supporting-briefing">
        <summary><span>Supporting context</span><span class="count-pill">${supportingSections.reduce((count, [, items]) => count + itemCount(items), 0)}</span></summary>
        <div class="briefing-grid">
          ${supportingSections.map(([title, items]) => renderCollapsedBriefingSection(title, items || [])).join('')}
        </div>
      </details>
    `;
  }

  if (active === 'inbox') {
    if (!executiveInbox && !executiveInboxLoading) {
      loadExecutiveInbox();
    }
    return `
      <h2>Executive Inbox</h2>
      <p>Process high-value clarification questions and advisor reviews before they change durable memory.</p>
      ${executiveInboxMessage ? `<p class="success" role="status">${escapeHtml(executiveInboxMessage)}</p>` : ''}
      <div class="toolbar">
        <button id="inbox-refresh" type="button" class="secondary" ${submitting || executiveInboxLoading ? 'disabled' : ''}>Refresh</button>
      </div>
      ${executiveInboxLoading || !executiveInbox ? '<p>Loading inbox…</p>' : `
        <div class="inbox-list">
          ${executiveInbox.items?.length ? executiveInbox.items.map(renderInboxItem).join('') : '<p class="muted">No clarification questions or advisor reviews need attention right now.</p>'}
        </div>
      `}
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
        <label for="memory-company-filter">Company</label>
        <input id="memory-company-filter" value="${escapeHtml(memoryCompanyFilter)}" placeholder="All companies" />
        <button id="memory-filter-apply" type="button" class="secondary">Apply</button>
        ${memoryCompanyFilter ? '<button id="memory-filter-clear" type="button" class="secondary">Clear</button>' : ''}
      </div>
      <details class="backup-panel">
        <summary><span>Memory backup</span></summary>
        <div class="backup-controls">
          <button id="backup-export" type="button" class="secondary" ${submitting ? 'disabled' : ''}>Export JSON</button>
          <label for="backup-mode">Import mode</label>
          <select id="backup-mode">
            <option value="merge" ${backupImportMode === 'merge' ? 'selected' : ''}>Merge</option>
            <option value="replace" ${backupImportMode === 'replace' ? 'selected' : ''}>Replace all</option>
          </select>
          <label class="file-button" for="backup-import-file">Import JSON</label>
          <input id="backup-import-file" type="file" accept="application/json,.json" />
        </div>
      </details>
      ${memoryMessage ? `<p class="success" role="status">${escapeHtml(memoryMessage)}</p>` : ''}
      ${memoryRelated ? renderRelatedPanel(memoryRelated) : ''}
      ${memoryEdit ? `
        <div id="memory-detail-panel" class="editor-panel">
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
      ${memoryLoading || !memoryObjects ? '<p>Loading memory…</p>' : `
        <div class="memory-list">
          ${memoryObjects.items.length ? memoryObjects.items.map((item) => `
            <article>
              <div>
                <span class="badge">#${escapeHtml(item.id)}</span>
                <h3>${escapeHtml(item[selectedType.titleField] || `${selectedType.label} memory`)}</h3>
                <p>${escapeHtml(item.company || item.status || item.type || item.value || 'Stored memory object')}</p>
              </div>
              <div class="object-actions">
                ${memoryType === 'tasks' && item.status !== 'completed' ? `<button type="button" class="secondary" data-complete-task="${escapeHtml(item.id)}">Complete</button>` : ''}
                ${memoryType === 'tasks' && item.status === 'completed' ? `<button type="button" class="secondary" data-reopen-task="${escapeHtml(item.id)}">Reopen</button>` : ''}
                <button type="button" class="secondary" data-related-object="${escapeHtml(item.id)}">Related</button>
                <button type="button" class="secondary" data-edit-object="${escapeHtml(item.id)}">Edit</button>
              </div>
            </article>
          `).join('') : '<p class="muted">No objects found for this type.</p>'}
        </div>
      `}
    `;
  }

  return `
    <h2>Search / Ask</h2>
    <label for="search-input" class="sr-only">Question about executive memory</label>
    <input id="search-input" placeholder="Example: Why did we promote Julio?" />
    <button id="search-submit" style="margin-top: 12px;" ${submitting ? 'disabled' : ''}>${submitting ? 'Searching…' : 'Ask ExecutiveOS'}</button>
    ${searchResults ? `<div class="results"><aside class="focus"><strong>ExecutiveOS answer</strong><p>${escapeHtml(searchResults.answer || 'No matching executive memory found.')}</p></aside>
      <div class="prep-grid">
        ${renderPrepSection('Directly supported facts', searchResults.directly_supported_facts, 'context')}
        ${renderPrepSection('Inferences', searchResults.inferences, 'context', 'No inference needed.')}
        ${renderPrepSection('Missing information', searchResults.missing_information, 'risk', 'No obvious gaps.')}
      </div>
      ${searchResults.results.length ? searchResults.results.map((result) => `
      <article><span class="badge">${escapeHtml(humanize(result.type))}</span><h3>${escapeHtml(result.title)}</h3><p>${escapeHtml(result.summary)}</p></article>
    `).join('') : '<p class="muted">No matching executive memory found.</p>'}</div>` : ''}
  `;
}

initialize();
