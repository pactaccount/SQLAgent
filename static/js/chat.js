/**
 * The chat panel.
 *
 * A message thread where the user asks in plain English and the agent answers
 * with prose, an insight, a result table, and a collapsible disclosure of the
 * SQL it ran. Every claim the agent makes is backed by something the user can
 * check.
 */

import { el, icon, iconFilled, escapeHtml, downloadText } from './ui.js';
import { toast } from './toast.js';

/**
 * Render markdown-lite: paragraphs, **bold**, `code`, and bullet lists.
 * Everything is escaped first, so no user or model content can inject markup.
 */
function renderRichText(text) {
    const safe = escapeHtml(text);
    const withCode = safe.replace(/`([^`]+)`/g, '<code>$1</code>');
    const withBold = withCode.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    return withBold
        .split(/\n{2,}/)
        .map((block) => {
            const lines = block.split('\n');
            const isList = lines.every((line) => /^\s*[-*]\s+/.test(line));
            if (isList) {
                const items = lines
                    .map((line) => `<li>${line.replace(/^\s*[-*]\s+/, '')}</li>`)
                    .join('');
                return `<ul>${items}</ul>`;
            }
            return `<p>${lines.join('<br>')}</p>`;
        })
        .join('');
}

/** A badge describing something the agent did. */
function badge(text, kind, iconName) {
    return el(
        'span',
        { class: `badge badge--${kind}` },
        iconName ? icon(iconName, 11) : null,
        text,
    );
}

/**
 * The collapsible "what SQL did this run" block.
 *
 * The SQL is editable, and an edited query can be re-run. That turns the
 * disclosure from a read-only receipt into a repair loop: if the agent
 * picked the wrong column, you can fix it without going back to the chat.
 */
function sqlDisclosure(sql, explanation, handlers = {}) {
    const details = el('details', { class: 'sql-disclosure' });

    const summary = el(
        'summary',
        { class: 'sql-disclosure__toggle' },
        icon('chevronRight', 13, 'sql-disclosure__chevron'),
        el('span', { text: 'View the SQL that was run' }),
    );

    const body = el('div', { class: 'sql-disclosure__body' });

    // The provenance line: which tables the answer came from. This is the
    // "found data in" step - it lets a number be traced to its source
    // without reading the SQL.
    if (handlers.tablesUsed?.length) {
        body.append(
            el(
                'div',
                { class: 'provenance' },
                icon('table2', 13),
                el('span', {
                    text: `Read from ${handlers.tablesUsed.join(', ')}`,
                }),
            ),
        );
    }

    if (explanation) {
        body.append(
            el(
                'div',
                { class: 'callout callout--info', style: 'margin-bottom: 12px' },
                icon('info', 15),
                el('span', { text: explanation }),
            ),
        );
    }

    const editor = el('textarea', {
        class: 'textarea sql-editor',
        spellcheck: 'false',
        'aria-label': 'The SQL that was run. Edit it to run a different query.',
    });
    editor.value = sql;

    const runBtn = el(
        'button',
        {
            class: 'btn btn--primary btn--sm',
            onclick: () => {
                const edited = editor.value.trim();
                if (!edited) {
                    toast('Write a query first.', 'warning');
                    return;
                }
                handlers.onRunSql?.(edited);
            },
        },
        icon('play', 12),
        'Run this SQL',
    );

    const copyBtn = el(
        'button',
        {
            class: 'btn btn--ghost btn--sm',
            onclick: async () => {
                try {
                    await navigator.clipboard.writeText(editor.value);
                    toast('SQL copied to your clipboard.', 'success');
                } catch {
                    toast('Could not copy to the clipboard.', 'error');
                }
            },
        },
        icon('copy', 13),
        'Copy SQL',
    );

    body.append(
        editor,
        el(
            'div',
            { class: 'sql-disclosure__actions' },
            runBtn,
            copyBtn,
            el('span', {
                class: 'sql-disclosure__hint',
                text: 'Edit and re-run to correct a wrong column or filter.',
            }),
        ),
    );

    details.append(summary, body);
    return details;
}

/**
 * A feedback control on each answer. The thumbs are a real signal about
 * answer quality, and they give the user something to do with a bad answer.
 */
function feedbackRow(onFeedback) {
    const row = el('div', { class: 'feedback' });

    const make = (name, label, glyph) =>
        el(
            'button',
            {
                class: 'feedback__btn',
                type: 'button',
                title: label,
                'aria-label': label,
                onclick: (event) => {
                    const wasActive = event.currentTarget.classList.contains('is-active');
                    row.querySelectorAll('button').forEach((b) => b.classList.remove('is-active'));
                    if (!wasActive) {
                        event.currentTarget.classList.add('is-active');
                        onFeedback(name);
                    }
                },
            },
            el('span', { class: 'feedback__glyph', 'aria-hidden': 'true', text: glyph }),
        );

    row.append(
        make('up', 'This answer was helpful', '▲'),
        make('down', 'This answer was not helpful', '▼'),
    );
    return row;
}

/**
 * The approval card for a statement that changes data.
 *
 * The wording follows the established confirmation-dialog canon:
 *   - the title is a question that names the object and uses the same verb
 *     as the confirm button
 *   - the description states the consequence in one or two sentences
 *   - the buttons use a specific verb, not "OK" or "Yes"
 *   - the safe option is the one that reads as the default, and the
 *     destructive button is never auto-focused
 */
function buildApprovalCard({ analysis, preview, handlers }) {
    const card = el('div', { class: 'approval' });

    const type = analysis?.type || 'UPDATE';
    const tables = analysis?.tables || [];
    const target = tables.length === 1 ? ` '${tables[0]}'` : '';

    // A verb that matches what will actually happen.
    const VERBS = {
        DELETE: { verb: 'Delete', gerund: 'deleting' },
        UPDATE: { verb: 'Update', gerund: 'updating' },
        INSERT: { verb: 'Add', gerund: 'adding' },
        DROP: { verb: 'Drop', gerund: 'dropping' },
        ALTER: { verb: 'Alter', gerund: 'altering' },
        CREATE: { verb: 'Create', gerund: 'creating' },
        TRUNCATE: { verb: 'Empty', gerund: 'emptying' },
    };
    const { verb, gerund } = VERBS[type] || { verb: 'Run', gerund: 'running' };

    const rows = preview?.estimated_rows;

    // The title restates what the computer is about to do, by name.
    const title = type === 'DELETE' && rows !== null && rows !== undefined
        ? `Delete ${rows.toLocaleString()} row${rows === 1 ? '' : 's'} from${target || ' the table'}?`
        : `${verb}${target} now?`;

    card.append(
        el(
            'div',
            { class: 'approval__head' },
            icon('shield', 16),
            el('span', { text: title }),
        ),
    );

    const body = el('div', { class: 'approval__body' });

    // The consequence, stated plainly, in one or two sentences.
    const consequence = analysis?.description || 'This statement modifies the database.';
    const permanence =
        type === 'DELETE' || type === 'DROP' || type === 'TRUNCATE'
            ? ' This cannot be undone.'
            : '';
    body.append(
        el('p', {
            class: 'approval__desc',
            text: `${consequence}${permanence}`,
        }),
    );

    const impact = el('div', { class: 'approval__impact' });
    const list = el('dl');

    if (rows !== null && rows !== undefined) {
        list.append(
            el('dt', { text: 'Rows affected' }),
            el('dd', { text: rows.toLocaleString() }),
        );
    }
    if (tables.length) {
        list.append(el('dt', { text: 'Table' }), el('dd', { text: tables.join(', ') }));
    }
    list.append(el('dt', { text: 'Statement' }), el('dd', { text: type }));

    impact.append(list);

    if (preview?.message) {
        impact.append(
            el('p', {
                text: preview.message,
                style: 'margin-top:8px; color:var(--text-muted)',
            }),
        );
    }

    if (preview?.sample_rows?.length) {
        impact.append(
            el('p', {
                class: 'approval__sample-label',
                text: 'Rows that would be affected:',
            }),
        );

        const table = el('table', { class: 'grid__table', style: 'margin-top:6px' });
        const head = el('tr');
        for (const column of preview.sample_columns || []) {
            head.append(el('th', { scope: 'col', text: column }));
        }
        const bodyRows = el('tbody');
        for (const row of preview.sample_rows) {
            const tr = el('tr');
            for (const column of preview.sample_columns || []) {
                const value = row[column];
                tr.append(
                    el('td', {
                        text: value === null || value === undefined ? 'NULL' : String(value),
                    }),
                );
            }
            bodyRows.append(tr);
        }
        table.append(el('thead', {}, head), bodyRows);
        impact.append(table);
    }

    body.append(impact);

    // The buttons name the action. The destructive one is a specific verb,
    // and neither button is auto-focused.
    const approveBtn = el(
        'button',
        {
            class: 'btn btn--danger',
            type: 'button',
            onclick: () => handlers.onApprove(approveBtn, rejectBtn),
        },
        icon('play', 13),
        `${verb} ${type === 'INSERT' ? 'rows' : type === 'DROP' ? 'table' : 'now'}`,
    );
    const rejectBtn = el(
        'button',
        {
            class: 'btn',
            type: 'button',
            onclick: () => handlers.onReject(),
        },
        'Keep the data',
    );

    body.append(el('div', { class: 'approval__actions' }, approveBtn, rejectBtn));
    card.append(body);
    return card;
}

/**
 * The step breakdown of the query.
 *
 * Research on NL2SQL interfaces is consistent that a single block of SQL
 * forces a non-technical reader to either verify it or ignore it. Breaking
 * the query into named steps gives the reader something they can check one
 * line at a time, and each step is a place where they can say "no, this
 * isn't what I meant" - which is far cheaper than re-phrasing the whole
 * question.
 */
function stepList(steps) {
    if (!steps?.length) return null;

    const list = el('ol', { class: 'steps-list' });

    steps.forEach((step, index) => {
        list.append(
            el(
                'li',
                { class: 'steps-list__item' },
                el('span', { class: 'steps-list__num', text: String(index + 1) }),
                el('span', { class: 'steps-list__text', text: step }),
            ),
        );
    });

    const wrap = el('div', { class: 'steps' });

    wrap.append(
        el(
            'div',
            { class: 'steps__head' },
            icon('list', 13),
            el('span', { class: 'steps__label', text: 'How this was worked out' }),
        ),
        list,
        el(
            'p',
            { class: 'steps__hint', text: 'If a step is not what you meant, say so and the agent will try again.' },
        ),
    );

    return wrap;
}

/**
 * The chat panel controller.
 */
export { buildApprovalCard };

export class ChatPanel {
    constructor(root, { onResult, onRequestSql, onApprovalNeeded }) {
        this.root = root;
        this.onResult = onResult;
        this.onRequestSql = onRequestSql;
        this.onApprovalNeeded = onApprovalNeeded;

        this.scroll = el('div', {
            class: 'chat__scroll',
            id: 'chat-scroll',
            role: 'log',
            'aria-live': 'polite',
            'aria-label': 'Conversation',
        });

        this.composer = el('div', { class: 'composer' });

        root.replaceChildren(this.scroll, this.composer);
        this._buildComposer();
    }

    _buildComposer() {
        this.input = el('textarea', {
            class: 'composer__input',
            id: 'user-input',
            rows: 1,
            placeholder: 'Ask a question about your data…',
            'aria-label': 'Ask a question about your data',
        });

        // Grow with the content, up to the CSS max-height.
        this.input.addEventListener('input', () => {
            this.input.style.height = 'auto';
            this.input.style.height = `${Math.min(this.input.scrollHeight, 140)}px`;
        });

        // Enter sends, Shift+Enter makes a new line.
        this.input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                this.form.requestSubmit();
            }
        });

        this.sendBtn = el(
            'button',
            { class: 'composer__send', type: 'submit', title: 'Send question', 'aria-label': 'Send question' },
            iconFilled('send', 15),
        );

        this.form = el(
            'form',
            { class: 'composer__box', id: 'chat-form' },
            this.input,
            this.sendBtn,
        );

        this.form.addEventListener('submit', (event) => {
            event.preventDefault();
            const query = this.input.value.trim();
            if (!query) return;
            this.input.value = '';
            this.input.style.height = 'auto';
            this.onSubmit?.(query);
        });

        this.hint = el(
            'div',
            { class: 'composer__hint' },
            el('span', { text: 'Press Enter to send · Shift+Enter for a new line' }),
        );

        this.composer.replaceChildren(this.form, this.hint);
    }

    /**
     * Scroll to the newest message - but only if the user is already at the
     * bottom. Yanking the view down while someone is reading earlier
     * messages is the single most common complaint about chat interfaces.
     */
    scrollToBottom({ force = false } = {}) {
        requestAnimationFrame(() => {
            if (!force && !this.isNearBottom()) return;
            this.scroll.scrollTop = this.scroll.scrollHeight;
        });
    }

    /** True when the scroll position is within a short distance of the end. */
    isNearBottom() {
        const { scrollTop, scrollHeight, clientHeight } = this.scroll;
        // A short answer may not fill the panel, so a small scrollHeight
        // means we are at the bottom by definition.
        if (scrollHeight <= clientHeight + 8) return true;
        return scrollHeight - (scrollTop + clientHeight) < 80;
    }

    /** Show the user's question. */
    addUserMessage(text, options = {}) {
        const body = el('div', { class: 'msg__body' });
        const bubble = el('div', { class: 'msg__bubble' });
        bubble.innerHTML = renderRichText(text);
        body.append(bubble);

        const message = el(
            'div',
            { class: 'msg msg--user' },
            el('div', { class: 'msg__avatar', text: 'You' }),
            body,
        );

        this.scroll.append(message);
        if (!options.silent) this.record({ kind: 'user', text });
        this.scrollToBottom();
        return message;
    }

    /**
     * Show a placeholder while the agent works.
     * @param {string} label
     */
    addTyping(label = 'Thinking') {
        const body = el('div', { class: 'msg__body' });
        const bubble = el('div', { class: 'msg__bubble' });

        const typing = el('span', { class: 'typing' });
        typing.append(
            el('span', { class: 'typing__dot' }),
            el('span', { class: 'typing__dot' }),
            el('span', { class: 'typing__dot' }),
        );

        bubble.append(
            el('span', { class: 'typing__label', text: `${label}…`, style: 'margin-right:8px' }),
            typing,
        );

        body.append(bubble);
        const message = el(
            'div',
            { class: 'msg msg--agent' },
            el('div', { class: 'msg__avatar', text: 'AI' }),
            body,
        );

        this.scroll.append(message);
        this.scrollToBottom();
        return message;
    }

    /**
     * Show the agent's answer.
     *
     * @param {object} data  the /chat response
     * @param {object} handlers  { onApprove, onReject, onFeedback, onRunSql, onFollowUp, onReask }
     */
    addAgentMessage(data, handlers = {}) {
        const body = el('div', { class: 'msg__body' });

        // --- Status badges: what the agent did, stated plainly. ---
        const meta = el('div', { class: 'msg__meta' });

        if (data.cached) {
            meta.append(badge('Answered from cache', 'neutral', 'bolt'));
        }
        if (data.error_traces?.length) {
            meta.append(
                badge(
                    `Self-corrected after ${data.error_traces.length} attempt${data.error_traces.length === 1 ? '' : 's'}`,
                    'warning',
                    'refresh',
                ),
            );
        }
        if (data.requires_approval) {
            meta.append(badge('Waiting for your approval', 'critical', 'lock'));
        }
        if (data.row_count) {
            meta.append(badge(`${data.row_count.toLocaleString()} rows`, 'neutral', 'table'));
        }

        // The confidence signal. It is deliberately categorical and it is
        // derived from what actually happened during the run, so it is
        // evidence rather than a number the model made up.
        if (data.confidence?.level && data.confidence.level !== 'high') {
            const kind = data.confidence.level === 'low' ? 'warning' : 'neutral';
            const confidenceBadge = badge(
                `Confidence: ${data.confidence.level}`,
                kind,
                data.confidence.level === 'low' ? 'alert' : 'info',
            );
            if (data.confidence.reason) {
                confidenceBadge.title = data.confidence.reason;
            }
            meta.append(confidenceBadge);
        }
        if (meta.childElementCount) body.append(meta);

        // --- The answer itself. ---
        const bubble = el('div', { class: 'msg__bubble' });
        bubble.innerHTML = renderRichText(data.simple_answer || '');
        body.append(bubble);

        // --- The uncertainty note. ---
        // Research on AI interfaces is consistent on this point: a confident
        // tone with no way to check makes users take a wrong answer at face
        // value. The steps and the SQL are both one click away, so point at
        // them rather than adding a vague disclaimer.
        if (!data.requires_approval && data.sql_query) {
            body.append(
                el('p', {
                    class: 'msg__caveat',
                    text: data.steps?.length
                        ? 'Check the steps and the SQL below if this number matters - the agent can misread a question.'
                        : 'Check the SQL below if this number matters - the agent can misread a question.',
                }),
            );
        }

        // --- The insight: the one thing worth reading. ---
        if (data.insight) {
            body.append(
                el(
                    'div',
                    { class: 'insight' },
                    icon('sparkle', 15, 'insight__icon'),
                    el(
                        'div',
                        {},
                        el('span', { class: 'insight__label', text: 'What stands out' }),
                        el('span', { text: data.insight }),
                    ),
                ),
            );
        }

        // --- The error traces, if the agent had to retry. ---
        if (data.error_traces?.length) {
            const traces = el('div', { class: 'traces' });
            traces.append(
                el(
                    'div',
                    { class: 'traces__title' },
                    icon('refresh', 13),
                    el('span', { text: 'The agent fixed these on its own' }),
                ),
            );
            data.error_traces.forEach((error, index) => {
                traces.append(
                    el('span', {
                        class: 'trace',
                        text: `Attempt ${index + 1}: ${error}`,
                    }),
                );
            });
            body.append(traces);
        }

        // --- The steps, so the query can be checked a line at a time. ---
        const steps = stepList(data.steps);
        if (steps) body.append(steps);

        // --- The SQL. Always available, never in the way. ---
        if (data.sql_query) {
            body.append(
                sqlDisclosure(data.sql_query, data.sql_explanation, {
                    onRunSql: handlers.onRunSql,
                    tablesUsed: data.tables_used,
                }),
            );
        }

        // --- Suggested follow-up questions. ---
        if (data.follow_ups?.length) {
            const chips = el('div', { class: 'follow-ups' });

            for (const question of data.follow_ups) {
                chips.append(
                    el(
                        'button',
                        {
                            class: 'follow-up',
                            type: 'button',
                            onclick: () => handlers.onFollowUp?.(question),
                        },
                        icon('chevronRight', 12, 'follow-up__icon'),
                        el('span', { text: question }),
                    ),
                );
            }

            body.append(
                el(
                    'div',
                    { class: 'follow-ups__wrap' },
                    el('span', { class: 'follow-ups__label', text: 'Try asking' }),
                    chips,
                ),
            );
        }

        // --- The approval card for a statement that changes data. ---
        if (data.requires_approval) {
            const card = el('div');
            body.append(card);

            // Ask the server what the statement would do before showing it.
            this.onApprovalNeeded?.(data, card, handlers);
        }

        // --- Feedback and the per-answer actions. ---
        if (!data.requires_approval) {
            body.append(
                feedbackRow((kind) => {
                    toast(
                        kind === 'up'
                            ? 'Thanks - that feedback helps.'
                            : 'Thanks - noted. Check the SQL below if the answer looks wrong.',
                        'info',
                    );
                    handlers.onFeedback?.(kind, data);
                }),
            );
        }

        // --- Copy the answer, or ask it again. ---
        body.append(
            el(
                'div',
                { class: 'msg__actions' },
                el(
                    'button',
                    {
                        class: 'btn btn--ghost btn--sm',
                        onclick: async () => {
                            try {
                                await navigator.clipboard.writeText(data.simple_answer || '');
                                toast('Answer copied to your clipboard.', 'success');
                            } catch {
                                toast('Could not copy to the clipboard.', 'error');
                            }
                        },
                    },
                    icon('copy', 12),
                    'Copy answer',
                ),
                data.question
                    ? el(
                          'button',
                          {
                              class: 'btn btn--ghost btn--sm',
                              onclick: () => handlers.onReask?.(data.question),
                          },
                          icon('refresh', 12),
                          'Ask again',
                      )
                    : null,
            ),
        );

        const message = el(
            'div',
            { class: 'msg msg--agent' },
            el('div', { class: 'msg__avatar', text: 'AI' }),
            body,
        );

        this.scroll.append(message);
        if (!handlers.silent) this.record({ kind: 'agent', data });
        this.scrollToBottom();
        return message;
    }

    /** Show a plain error message in the thread. */
    addErrorMessage(text, options = {}) {
        const body = el('div', { class: 'msg__body' });
        body.append(
            el(
                'div',
                { class: 'callout callout--error' },
                icon('alert', 15),
                el('span', { text: text }),
            ),
        );

        const message = el(
            'div',
            { class: 'msg msg--agent' },
            el('div', { class: 'msg__avatar', text: '!' }),
            body,
        );

        this.scroll.append(message);
        if (!options.silent) this.record({ kind: 'error', text });
        this.scrollToBottom();
        return message;
    }

    /** Show a neutral system note. */
    addSystemMessage(text, kind = 'info', options = {}) {
        const body = el('div', { class: 'msg__body' });
        body.append(
            el(
                'div',
                { class: `callout${kind === 'info' ? ' callout--info' : ''}` },
                icon(kind === 'info' ? 'info' : 'alert', 15),
                el('span', { text: text }),
            ),
        );

        const message = el(
            'div',
            { class: 'msg msg--agent' },
            el('div', { class: 'msg__avatar', text: 'i' }),
            body,
        );

        this.scroll.append(message);
        if (!options.silent) this.record({ kind: 'system', text, kind2: kind });
        this.scrollToBottom();
        return message;
    }

    /**
     * Record a message into the transcript.
     *
     * The transcript lives on the session, not on this panel, so switching
     * to another tab and back restores the conversation rather than
     * leaving it empty.
     */
    record(entry) {
        this.onRecord?.(entry);
    }

    /**
     * Rebuild the thread from a session's transcript.
     *
     * Used when switching tabs. The messages are replayed through the same
     * renderers that produced them originally, so a restored conversation is
     * identical to the original - not a simplified version of it.
     */
    renderTranscript(messages, handlers = {}) {
        this.scroll.replaceChildren();

        for (const entry of messages || []) {
            switch (entry.kind) {
                case 'user':
                    this.addUserMessage(entry.text, { silent: true });
                    break;
                case 'agent':
                    this.addAgentMessage(entry.data, { ...handlers, silent: true });
                    break;
                case 'error':
                    this.addErrorMessage(entry.text, { silent: true });
                    break;
                case 'system':
                    this.addSystemMessage(entry.text, entry.kind2, { silent: true });
                    break;
                default:
                    break;
            }
        }

        this.scrollToBottom({ force: true });
    }

    /**
     * Show the starter questions, derived from the connected database.
     * @param {Array} starters
     * @param {function} onPick
     */
    addStarters(starters, onPick) {
        if (!starters?.length) return null;

        const wrap = el('div', { class: 'starters' });

        for (const starter of starters) {
            wrap.append(
                el(
                    'button',
                    {
                        class: 'starter',
                        type: 'button',
                        onclick: () => onPick(starter.question),
                    },
                    icon('sparkle', 14),
                    el(
                        'span',
                        {},
                        el('span', { text: starter.question }),
                        el('span', {
                            class: 'starter__table',
                            text: `from ${starter.table_label}`,
                        }),
                    ),
                ),
            );
        }

        this.scroll.append(wrap);
        this.scrollToBottom();
        return wrap;
    }

    /** Remove every message (used when switching sessions). */
    clear() {
        this.scroll.replaceChildren();
    }

    /**
     * Export the conversation as plain text.
     *
     * A conversation you cannot take with you is a dead end - the reader
     * should be able to paste it into a document, a ticket, or an email.
     */
    exportTranscript() {
        const lines = [];

        for (const message of this.scroll.children) {
            const isUser = message.className.includes('msg--user');
            const bubble = message.children[1]?.children[0];
            const text = bubble?.textContent?.trim();
            if (!text) continue;
            lines.push(`${isUser ? 'You' : 'SQL Agent'}: ${text}`);
        }

        if (!lines.length) {
            toast('There is nothing to export yet.', 'warning');
            return;
        }

        const stamp = new Date().toISOString().slice(0, 16).replace('T', ' ');
        const body = `SQL Agent conversation - ${stamp}\n\n${lines.join('\n\n')}\n`;
        downloadText('sql-agent-conversation.txt', body, 'text/plain;charset=utf-8');
        toast('Conversation exported.', 'success');
    }

    setPlaceholder(text) {
        this.input.placeholder = text;
    }
}
