/**
 * Application entry point.
 *
 * Wires the panels, the chat, the grid and the wizard together, and owns the
 * one piece of cross-cutting behaviour: every ask goes through here, so the
 * status bar, the busy state and the result panel stay in step.
 */

import { store } from './state.js';
import { api, ApiError } from './api.js';
import { el, icon, iconFilled, formatDuration, debounce } from './ui.js';
import { toast } from './toast.js';
import { initIcons } from './icons-init.js';
import { ChatPanel, buildApprovalCard } from './chat.js';
import { DataGrid } from './datagrid.js';
import { SchemaExplorer } from './explorer.js';
import { ConnectionWizard } from './wizard.js';
import { buildChart } from './chart.js';

const dom = {
    root: document.getElementById('app'),

    // Top bar
    connChip: document.getElementById('conn-chip'),
    connLabel: document.getElementById('conn-label'),
    connectBtn: document.getElementById('connect-btn'),
    themeBtn: document.getElementById('theme-btn'),

    // Panels
    leftPanel: document.getElementById('left-panel'),
    rightPanel: document.getElementById('right-panel'),
    railExplorer: document.getElementById('rail-explorer'),
    railChat: document.getElementById('rail-chat'),

    // Centre
    tabBar: document.getElementById('tab-bar'),
    sqlBody: document.getElementById('sql-body'),
    dataBody: document.getElementById('data-body'),
    chartSlot: document.getElementById('chart-slot'),
    dataEmpty: document.getElementById('data-empty'),

    // Chat
    chatPanel: document.getElementById('chat-panel'),
    exportConversation: document.getElementById('export-conversation'),

    // Explorer
    explorer: document.getElementById('explorer'),

    // Status bar
    statusConnection: document.getElementById('status-connection'),
    statusRows: document.getElementById('status-rows'),
    statusTiming: document.getElementById('status-timing'),
    statusMode: document.getElementById('status-mode'),

    // Modal
    wizardModal: document.getElementById('wizard-modal'),

    // The AI-interaction notice
    aiNotice: document.querySelector('.ai-notice'),
};

let chat;
let grid;
let explorer;
let wizard;

// ---------------------------------------------------------------------------
// Session handling
// ---------------------------------------------------------------------------

/** Copy a session's state into the panels. */
function renderSession() {
    const session = store.activeSession;
    if (!session) return;

    // --- Tabs ---
    renderTabs();

    // --- SQL panel ---
    dom.sqlBody.replaceChildren(
        session.sql
            ? el('pre', { class: 'sql-block' }, el('code', { text: session.sql }))
            : el(
                  'div',
                  { class: 'panel__empty' },
                  icon('code', 26),
                  el('div', { class: 'panel__empty-title', text: 'No query yet' }),
                  el('div', {
                      class: 'panel__empty-text',
                      text: 'Ask a question and the SQL the agent ran will appear here.',
                  }),
              ),
    );

    // --- Data panel ---
    renderResults(session);
}

function renderTabs() {
    const sessions = store.state.sessions;
    const activeId = store.state.activeSessionId;

    const tabs = sessions.map((session) => {
        // The tab is a container, not a button. Putting the close control
        // inside a <button> nests interactive elements, which is invalid
        // HTML and stops the close button working in some browsers.
        const tab = el(
            'div',
            {
                class: `tab${session.id === activeId ? ' is-active' : ''}`,
                role: 'tab',
                tabindex: '0',
                'aria-selected': String(session.id === activeId),
                onclick: () => store.setActiveSession(session.id),
                onkeydown: (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        store.setActiveSession(session.id);
                    }
                },
            },
            el('span', { class: 'tab__label', text: session.title }),
        );

        // The close control is always present, even for the only tab, so
        // that its position does not shift when a second tab is opened.
        tab.append(
            el(
                'button',
                {
                    class: 'tab__close',
                    type: 'button',
                    title: `Close ${session.title}`,
                    'aria-label': `Close ${session.title}`,
                    onclick: (event) => {
                        event.stopPropagation();
                        closeSession(session.id);
                    },
                },
                '×',
            ),
        );

        return tab;
    });

    tabs.push(
        el(
            'button',
            {
                class: 'tab tab--new',
                type: 'button',
                title: 'Start a new query',
                'aria-label': 'Start a new query',
                onclick: () => {
                    store.createSession();
                },
            },
            icon('plus', 14),
        ),
    );

    dom.tabBar.replaceChildren(...tabs);
}

/**
 * Close a query tab.
 *
 * The last remaining tab is never closed - there has to be somewhere to
 * type the next question - but the button is still shown so the control
 * does not appear and disappear as tabs come and go.
 */
function closeSession(id) {
    if (store.state.sessions.length <= 1) {
        toast('This is your only query tab. Use the + button to open another.', 'info');
        return;
    }
    store.removeSession(id);
}

function renderResults(session) {
    // Clear any previous chart.
    if (dom.chartSlot.firstChild) {
        dom.chartSlot.firstChild._chart?.destroy?.();
        dom.chartSlot.replaceChildren();
    }

    if (!session.rows?.length) {
        // No rows: hide the grid and show the empty state instead.
        dom.dataEmpty.hidden = false;
        dom.dataBody.hidden = true;
        grid.setData([], []);
        if (dom.statusRows) dom.statusRows.textContent = '';
        return;
    }

    dom.dataEmpty.hidden = true;
    dom.dataBody.hidden = false;

    // The chart sits above the table. It is decorative for the same data the
    // table holds, so it never replaces the table.
    const chart = buildChart({
        columns: session.columns,
        rows: session.rows,
        preferredType: session.chartType,
    });
    if (chart) dom.chartSlot.replaceChildren(chart);

    grid.setData(session.columns, session.rows, { truncated: session.truncated });

    if (dom.statusRows) {
        dom.statusRows.textContent = `${session.rowCount.toLocaleString()} rows`;
    }
}

// ---------------------------------------------------------------------------
// Asking a question
// ---------------------------------------------------------------------------

async function ask(question) {
    const connection = store.state.connection;

    if (!connection.dbUri) {
        wizard.open();
        toast('Connect a database first.', 'info');
        return;
    }

    const session = store.activeSession;
    if (!session || session.loading) return;

    // The tab takes the question as its title, so tabs stay meaningful.
    if (session.title.startsWith('Query')) {
        const short = question.length > 34 ? `${question.slice(0, 34)}…` : question;
        store.updateSession(session.id, { title: short });
    }

    chat.addUserMessage(question);
    dismissAiNotice();
    const typing = chat.addTyping('Looking at your data');

    store.setBusy(true);
    const started = performance.now();

    try {
        const data = await api.chat(question, connection.tenantId, connection.dbUri);
        typing.remove();

        const elapsed = performance.now() - started;
        if (dom.statusTiming) dom.statusTiming.textContent = formatDuration(elapsed);

        store.updateSession(session.id, {
            sql: data.sql_query,
            columns: data.columns?.length ? data.columns : Object.keys(data.execution_result?.[0] || {}),
            rows: data.execution_result || [],
            rowCount: data.row_count || data.execution_result?.length || 0,
            truncated: data.truncated,
            chartType: data.chart_type || 'none',
            insight: data.insight || '',
            explanation: data.sql_explanation || '',
            analysis: data.analysis || null,
        });

        chat.addAgentMessage({ ...data, question }, {
            onRunSql: (sql) => runEditedSql(session, sql),
            onFollowUp: (followUp) => ask(followUp),
            onReask: (original) => ask(original),
            onApprove: (approveBtn, rejectBtn) => approveStatement(session, approveBtn, rejectBtn),
            onReject: () => {
                toast('Nothing was changed. Your data is untouched.', 'info');
            },
            onFeedback: (kind) => {
                console.info('Answer feedback:', kind, data.sql_query);
            },
        });

        renderSession();
    } catch (err) {
        typing.remove();
        const message =
            err instanceof ApiError
                ? err.message
                : 'Something went wrong while answering. Please try again.';
        chat.addErrorMessage(message);
        toast(message, 'error', 6000);
    } finally {
        store.setBusy(false);
    }
}

/**
 * Restore the active session's conversation into the chat panel.
 *
 * Each query tab keeps its own transcript, so switching tabs shows what was
 * asked in that tab rather than an empty thread.
 */
function restoreChat() {
    const session = store.activeSession;
    if (!session) return;

    chat.renderTranscript(session.messages, {
        onRunSql: (sql) => runEditedSql(session, sql),
        onFollowUp: (question) => ask(question),
        onReask: (original) => ask(original),
        onApprove: (approveBtn, rejectBtn) => approveStatement(session, approveBtn, rejectBtn),
        onReject: () => {
            toast('Nothing was changed. Your data is untouched.', 'info');
        },
        onFeedback: (kind) => {
            console.info('Answer feedback:', kind);
        },
    });
}

/**
 * Hide the AI-interaction notice once the user has actually asked something.
 *
 * It stays until the first question, because that is the moment the
 * disclosure has to be clear and distinguishable. After that the same
 * reassurance is carried by the caveat on every answer and by the SQL that
 * is always one click away.
 */
function dismissAiNotice() {
    dom.aiNotice?.classList.add('is-dismissed');
}

/**
 * Run a SQL statement the user edited by hand.
 *
 * This is the repair loop: the agent picked a column or a filter the user
 * disagrees with, so they fix it and re-run without going back to the chat.
 */
async function runEditedSql(session, sql) {
    const connection = store.state.connection;

    const typing = chat.addTyping('Running your query');
    const started = performance.now();

    try {
        const result = await api.runSql(sql, connection.dbUri, 500);
        typing.remove();

        const elapsed = performance.now() - started;
        if (dom.statusTiming) dom.statusTiming.textContent = formatDuration(elapsed);

        store.updateSession(session.id, {
            sql,
            columns: result.columns || [],
            rows: result.result || [],
            rowCount: result.row_count || 0,
            chartType: 'none',
        });

        chat.addSystemMessage(
            `Your query returned ${(result.row_count || 0).toLocaleString()} row(s).`,
            'info',
        );

        renderSession();
    } catch (err) {
        typing.remove();
        const message =
            err instanceof ApiError ? err.message : 'The query could not be run.';
        chat.addErrorMessage(message);
    }
}

/**
 * Run a statement the user approved, after showing them what it would do.
 */
async function approveStatement(session, approveBtn, rejectBtn) {
    const sql = session.sql;
    const connection = store.state.connection;

    // Remember the label so it can be restored if the run fails.
    const originalLabel = approveBtn.textContent;

    approveBtn.disabled = true;
    rejectBtn.disabled = true;
    approveBtn.textContent = 'Working…';

    try {
        const result = await api.executeApproved(sql, connection.tenantId, connection.dbUri);

        toast(
            `Change applied. ${result.result?.[0]?.rows_affected ?? 0} row(s) affected.`,
            'success',
        );

        store.updateSession(session.id, {
            rows: result.result || [],
            columns: result.columns || [],
            rowCount: result.row_count || 0,
        });
        renderSession();
    } catch (err) {
        const message = err instanceof ApiError ? err.message : 'The change could not be applied.';
        toast(message, 'error', 6000);
        approveBtn.disabled = false;
        rejectBtn.disabled = false;
        approveBtn.textContent = originalLabel;
    }
}

/**
 * Show the approval card once the server has confirmed what the statement
 * would do. The user never sees a "Run" button before the impact is known.
 */
async function showApprovalCard(data, container, handlers) {
    const connection = store.state.connection;

    container.replaceChildren(
        el(
            'div',
            { class: 'callout' },
            icon('clock', 15),
            el('span', { text: 'Checking what this change would do…' }),
        ),
    );

    try {
        const { analysis, preview } = await api.previewSql(data.sql_query, connection.dbUri);

        const card = buildApprovalCard({ analysis, preview, handlers });
        container.replaceChildren(card);
    } catch {
        // If the preview fails, still let the user decide - just say so.
        container.replaceChildren(
            buildApprovalCard({
                analysis: data.analysis || { description: 'This statement modifies data.' },
                preview: null,
                handlers,
            }),
        );
    }
}

/** Build the approval card. Kept separate so it can be re-created on error. */
// ---------------------------------------------------------------------------
// Connection
// ---------------------------------------------------------------------------

async function loadSchema() {
    const connection = store.state.connection;
    if (!connection.dbUri) return;

    try {
        const schema = await api.schema(connection.tenantId, connection.dbUri);
        store.setSchema(schema);
        explorer.setTables(schema.tables || []);
    } catch (err) {
        toast(
            err instanceof ApiError ? err.message : 'Could not read the database structure.',
            'error',
        );
    }
}

async function loadStarters() {
    const connection = store.state.connection;
    if (!connection.dbUri) return;

    try {
        const result = await api.starterQuestions(connection.tenantId, connection.dbUri);
        store.setStarters(result.questions || []);
    } catch {
        // Starter questions are a convenience; failing to get them is not fatal.
        store.setStarters([]);
    }
}

function updateConnectionUI() {
    const connection = store.state.connection;

    if (connection.connected) {
        dom.connChip.classList.add('conn-chip--on');
        dom.connLabel.textContent = `${connection.dbType} · ${connection.tenantId}`;
        dom.connChip.title = `Connected to ${connection.dbUri.replace(/:[^:@/]+@/, ':•••@')}`;
        dom.statusConnection.textContent = `● ${connection.dbType}`;
        dom.connectBtn.textContent = 'Change database';
    } else {
        dom.connChip.classList.remove('conn-chip--on');
        dom.connLabel.textContent = 'Not connected';
        dom.connChip.title = 'No database connected';
        dom.statusConnection.textContent = 'Not connected';
        dom.connectBtn.textContent = 'Connect a database';
    }
}

// ---------------------------------------------------------------------------
// Splitters
// ---------------------------------------------------------------------------

function initSplitters() {
    let dragging = null;

    const configs = [
        { id: 'split-left', axis: 'x', target: dom.leftPanel, min: 180, max: 460, invert: false },
        { id: 'split-right', axis: 'x', target: dom.rightPanel, min: 280, max: 620, invert: true },
    ];

    const onMove = (event) => {
        if (!dragging) return;

        const { target, min, max, invert, axis } = dragging;
        const rect = target.getBoundingClientRect();

        let size;
        if (axis === 'x') {
            const delta = event.clientX - dragging.startX;
            size = invert ? dragging.startSize - delta : dragging.startSize + delta;
        } else {
            size = dragging.startSize + (event.clientY - dragging.startY);
        }

        size = Math.max(min, Math.min(size, max));
        target.style.width = `${size}px`;
        target.style.flex = `0 0 ${size}px`;
    };

    const onUp = () => {
        if (!dragging) return;
        dragging.target.classList.remove('is-dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        dragging = null;
    };

    for (const config of configs) {
        const handle = document.getElementById(config.id);
        if (!handle) continue;

        handle.addEventListener('mousedown', (event) => {
            dragging = {
                ...config,
                startX: event.clientX,
                startY: event.clientY,
                startSize: config.target.getBoundingClientRect().width,
            };
            config.target.classList.add('is-dragging');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            event.preventDefault();
        });
    }

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

function boot() {
    // Theme first, so the first paint is correct.
    document.documentElement.setAttribute('data-theme', store.state.theme);
    initIcons();

    // --- Chat ---
    chat = new ChatPanel(dom.chatPanel, {
        onApprovalNeeded: (data, container, handlers) => {
            showApprovalCard(data, container, handlers);
        },
    });
    chat.onSubmit = (question) => ask(question);

    // Every message is filed against the session that is active when it is
    // added, so each tab keeps its own conversation.
    chat.onRecord = (entry) => {
        const session = store.activeSession;
        if (!session) return;
        store.addMessage(session.id, entry);
    };

    // --- Grid ---
    grid = new DataGrid(dom.dataBody);

    // --- Explorer ---
    explorer = new SchemaExplorer(dom.explorer, {
        onAskAbout: (question) => ask(question),
    });

    // --- Wizard ---
    wizard = new ConnectionWizard(dom.wizardModal, {
        onConnected: async (info) => {
            store.setConnection(info);
            updateConnectionUI();

            // A different database means the old answers no longer describe
            // it, so every tab starts fresh rather than showing results
            // that came from somewhere else.
            store.clearMessages();
            chat.clear();
            chat.addSystemMessage(
                `Connected to ${info.dbType}. Its structure has been indexed, so the agent knows what is in there.`,
            );

            await Promise.all([loadSchema(), loadStarters()]);

            // Offer the starter questions once the schema has loaded.
            const starters = store.state.starters;
            if (starters.length) {
                chat.addStarters(starters, (question) => ask(question));
            }
        },
    });

    // --- Top bar ---
    dom.connectBtn.addEventListener('click', () => {
        wizard.open({
            type: store.state.connection.dbType,
            tenantId: store.state.connection.tenantId,
        });
    });

    dom.connChip.addEventListener('click', () => {
        wizard.open({
            type: store.state.connection.dbType,
            tenantId: store.state.connection.tenantId,
        });
    });

    dom.themeBtn.addEventListener('click', () => {
        store.toggleTheme();
        // The chart colours are CSS variables, so it must be redrawn.
        const session = store.activeSession;
        if (session?.rows?.length) renderResults(session);
    });

    dom.exportConversation.addEventListener('click', () => {
        chat.exportTranscript();
    });

    // --- Activity rail ---
    dom.railExplorer.addEventListener('click', () => store.togglePanel('left'));
    dom.railChat.addEventListener('click', () => store.togglePanel('right'));

    // --- Panel visibility ---
    const applyPanels = () => {
        const { panels } = store.state;
        dom.leftPanel.classList.toggle('is-collapsed', !panels.left);
        dom.rightPanel.classList.toggle('is-collapsed', !panels.right);
        dom.railExplorer.classList.toggle('is-active', panels.left);
        dom.railChat.classList.toggle('is-active', panels.right);
        document.getElementById('split-left').style.display = panels.left ? '' : 'none';
        document.getElementById('split-right').style.display = panels.right ? '' : 'none';
    };
    store.subscribe((_, changed) => {
        if (changed.includes('panels')) applyPanels();
        if (changed.includes('connection')) updateConnectionUI();

        // The tab bar and the active session's panels both depend on the
        // session list. Without this, opening or closing a tab leaves the
        // bar showing whatever it last drew.
        if (changed.includes('sessions') || changed.includes('activeSessionId')) {
            renderTabs();
        }

        // Switching tabs restores that tab's conversation, SQL and results.
        if (changed.includes('activeSessionId')) {
            renderSession();
            restoreChat();
        }
    });
    applyPanels();

    // --- Keyboard shortcuts ---
    document.addEventListener('keydown', (event) => {
        const meta = event.metaKey || event.ctrlKey;

        if (meta && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            document.getElementById('user-input')?.focus();
        }
        if (meta && event.key.toLowerCase() === 'b') {
            event.preventDefault();
            store.togglePanel('left');
        }
        if (meta && event.key.toLowerCase() === 'j') {
            event.preventDefault();
            store.togglePanel('right');
        }
        if (meta && event.key === ',') {
            event.preventDefault();
            wizard.open({
                type: store.state.connection.dbType,
                tenantId: store.state.connection.tenantId,
            });
        }
    });

    initSplitters();

    // --- First session ---
    // createSession emits, which runs renderTabs/renderSession/restoreChat.
    // The transcript is empty at this point, so restoreChat just leaves the
    // panel clear for the welcome message below.
    store.createSession();
    renderSession();
    updateConnectionUI();

    // --- Restore a previous connection ---
    if (store.state.connection.connected) {
        chat.addSystemMessage(
            `Reconnected to ${store.state.connection.dbType}. Loading the structure…`,
        );
        Promise.all([loadSchema(), loadStarters()]).then(() => {
            const starters = store.state.starters;
            if (starters.length) chat.addStarters(starters, (question) => ask(question));
        });
    } else {
        chat.addSystemMessage(
            'Welcome. Connect a database to get started - there is a sample database included in the project if you want to try it first.',
        );
        renderWelcome();
    }
}

/**
 * The empty-state panel shown before a database is connected.
 */
function renderWelcome() {
    const steps = [
        { text: 'Connect a database', done: false },
        { text: 'Pick a question or write your own', done: false },
        { text: 'Read the answer, the table and the SQL', done: false },
    ];

    dom.dataEmpty.hidden = false;
    dom.dataEmpty.replaceChildren(
        el(
            'div',
            { class: 'welcome__inner' },
            el(
                'div',
                { class: 'welcome__hero' },
                el('div', { class: 'welcome__mark', text: 'S' }),
                el('h1', { class: 'welcome__title', text: 'Ask your database anything' }),
                el('p', {
                    class: 'welcome__text',
                    text: 'Type a question in plain English. The agent finds the right tables, writes the SQL, runs it, and shows you both the answer and the query behind it.',
                }),
            ),
            el(
                'div',
                { class: 'welcome__section' },
                el(
                    'div',
                    { class: 'welcome__section-head' },
                    icon('sparkle', 15),
                    el('span', { class: 'welcome__section-title', text: 'Getting started' }),
                ),
                el(
                    'ul',
                    { class: 'checklist' },
                    ...steps.map((step) =>
                        el(
                            'li',
                            { class: 'checklist__item' },
                            el('span', { class: 'checklist__mark' }),
                            el('span', { class: 'checklist__text', text: step.text }),
                        ),
                    ),
                ),
                el(
                    'button',
                    {
                        class: 'btn btn--primary',
                        style: 'align-self: flex-start',
                        onclick: () => wizard.open(),
                    },
                    icon('database', 14),
                    'Connect a database',
                ),
            ),
        ),
    );
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
} else {
    boot();
}
