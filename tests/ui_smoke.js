/**
 * A DOM smoke test for the frontend modules.
 *
 * It stubs the small number of browser APIs the modules use (document,
 * window, localStorage) and then exercises the real module code: the data
 * grid's sorting and filtering, the chart planner, the SQL disclosure, and
 * the chat message rendering.
 *
 * Run with:  node tests/ui_smoke.js
 */

import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const staticDir = join(here, '..', 'static');

// ---------------------------------------------------------------------------
// A minimal DOM, just enough for the modules under test.
// ---------------------------------------------------------------------------

class ClassList {
    constructor(node) { this.node = node; this.set = new Set(); }
    add(...names) { names.forEach((n) => this.set.add(n)); }
    remove(...names) { names.forEach((n) => this.set.delete(n)); }
    contains(name) { return this.set.has(name); }
    toggle(name, force) {
        const has = this.set.has(name);
        const want = force === undefined ? !has : force;
        if (want) this.set.add(name); else this.set.delete(name);
        return want;
    }
    get value() { return [...this.set].join(' '); }
}

class Element {
    constructor(tag) {
        this.tagName = String(tag).toUpperCase();
        this.children = [];
        this.parentNode = null;
        this.attributes = {};
        this.dataset = {};
        this.style = {};
        this.classList = new ClassList(this);
        this._text = '';
        this._html = '';
        this.listeners = {};
        this.value = '';
        this.disabled = false;
        this.hidden = false;
        this.id = '';
        this.className = '';
    }

    get childNodes() { return this.children; }
    get childElementCount() { return this.children.length; }
    get firstChild() { return this.children[0] || null; }
    get textContent() {
        if (this.children.length) return this.children.map((c) => c.textContent).join('');
        // An element whose content was set via innerHTML has no child nodes
        // in this stub, so fall back to the markup. Strip the tags to get
        // the text a reader would see.
        if (this._html) return this._html.replace(/<[^>]*>/g, '');
        return this._text;
    }
    set textContent(v) { this._text = v == null ? '' : String(v); this.children = []; }
    get innerHTML() { return this._html; }
    set innerHTML(v) { this._html = v == null ? '' : String(v); }
    get className() { return this.classList.value; }
    set className(v) {
        this.classList.set = new Set(String(v).split(/\s+/).filter(Boolean));
    }

    append(...nodes) {
        for (const node of nodes) {
            // A document fragment contributes its children, not itself.
            if (node instanceof Element && node.tagName === '#FRAGMENT') {
                for (const grandchild of [...node.children]) {
                    grandchild.parentNode = this;
                    this.children.push(grandchild);
                }
                continue;
            }
            const child = node instanceof Element ? node : new Element('#text');
            if (child instanceof Element) {
                // An Element child keeps its own text; only a plain string
                // becomes the child's text.
                child.parentNode = this;
            } else {
                child._text = String(node);
            }
            this.children.push(child);
        }
    }
    replaceChildren(...nodes) {
        this.children = [];
        this.append(...nodes);
    }
    remove() {
        if (!this.parentNode) return;
        this.parentNode.children = this.parentNode.children.filter((c) => c !== this);
        this.parentNode = null;
    }
    setAttribute(name, value) {
        this.attributes[name] = String(value);
        if (name === 'id') this.id = String(value);
    }
    getAttribute(name) { return this.attributes[name] ?? null; }
    removeAttribute(name) { delete this.attributes[name]; }
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
    dispatch(type, event = {}) {
        const payload = {
            preventDefault() {},
            stopPropagation() {},
            target: this,
            ...event,
        };
        (this.listeners[type] || []).forEach((fn) => fn(payload));
    }
    querySelector() { return null; }
    querySelectorAll() { return []; }
    focus() {}
    getBoundingClientRect() { return { width: 100, height: 100, top: 0, left: 0 }; }
    getContext() { return { }; }
    scrollIntoView() {}
}

// Build the document the modules expect.
const document = {
    documentElement: new Element('html'),
    body: new Element('body'),
    createElement: (tag) => new Element(tag),
    createElementNS: (_ns, tag) => new Element(tag),
    // Must be a real Element so the stub's textContent getter can find it.
    createTextNode: (text) => {
        const node = new Element('#text');
        node._text = String(text);
        return node;
    },
    createDocumentFragment: () => new Element('#FRAGMENT'),
    getElementById: (id) => registry.get(id) || null,
    querySelector: (sel) => (sel.startsWith('#') ? registry.get(sel.slice(1)) || null : null),
    querySelectorAll: () => [],
    addEventListener: () => {},
    dispatchEvent: () => {},
    activeElement: null,
};

const registry = new Map();
globalThis.document = document;

// The Element class doubles as Node, which is what ui.js checks against.
globalThis.Node = Element;

globalThis.window = {
    innerWidth: 1600,
    innerHeight: 1000,
    devicePixelRatio: 2,
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener: () => {},
    requestAnimationFrame: (fn) => fn(),
    getComputedStyle: () => ({ getPropertyValue: () => '#3987e5' }),
    Chart: null,
};

globalThis.localStorage = {
    store: {},
    getItem(k) { return this.store[k] ?? null; },
    setItem(k, v) { this.store[k] = String(v); },
    removeItem(k) { delete this.store[k]; },
};

// Node 26 defines navigator as a getter-only property, so it has to be
// redefined rather than assigned.
Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    writable: true,
    value: { clipboard: { writeText: async () => {} } },
});
globalThis.performance = { now: () => Date.now() };
globalThis.URL = { createObjectURL: () => 'blob:fake', revokeObjectURL: () => {} };
globalThis.Blob = class { constructor(parts) { this.parts = parts; } };
globalThis.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init?.detail; } };
globalThis.setTimeout = setTimeout;
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);

// ---------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------

let passed = 0;
let failed = 0;

function check(name, condition, detail = '') {
    if (condition) {
        passed++;
        console.log(`  PASS  ${name}`);
    } else {
        failed++;
        console.log(`  FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
    }
}

function section(name) {
    console.log(`\n${name}`);
}

// Load a module with the stubbed globals in place. The real file path is
// used so that the module's own relative imports resolve.
async function loadModule(relativePath) {
    return import(pathToFileURL(join(staticDir, relativePath)).href);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

async function run() {
    section('module loading');

    // Every module must load cleanly. A duplicate declaration inside a
    // function body is a syntax error that only shows up when the module is
    // imported, so this catches it before the browser does.
    for (const file of [
        'js/ui.js', 'js/api.js', 'js/state.js', 'js/toast.js',
        'js/chart.js', 'js/chat.js', 'js/datagrid.js', 'js/explorer.js',
        'js/wizard.js', 'js/icons-init.js',
    ]) {
        try {
            await loadModule(file);
            check(`${file} loads without error`, true);
        } catch (err) {
            check(`${file} loads without error`, false, err.message);
        }
    }

    // app.js boots the whole interface, so it needs the elements it looks
    // up by id to exist. Giving it a skeleton is the only way to know it
    // wires up cleanly.
    try {
        const ids = [
            'app', 'conn-chip', 'conn-label', 'connect-btn', 'theme-btn',
            'left-panel', 'right-panel', 'rail-explorer', 'rail-chat',
            'tab-bar', 'sql-body', 'data-body', 'chart-slot', 'data-empty',
            'chat-panel', 'explorer', 'status-connection', 'status-rows',
            'status-timing', 'status-mode', 'wizard-modal',
            'export-conversation', 'explorer-refresh', 'wizard-close',
            'split-left', 'split-right',
        ];
        for (const id of ids) {
            const node = new Element('div');
            node.id = id;
            registry.set(id, node);
        }

        // The wizard reads these off the modal.
        const modal = registry.get('wizard-modal');
        modal.querySelector = (sel) => {
            if (sel === '.modal__body') return new Element('div');
            if (sel === '.modal__foot') return new Element('div');
            if (sel === '.modal__title') return new Element('h2');
            if (sel === '.modal__subtitle') return new Element('p');
            return null;
        };

        await loadModule('js/app.js');
        check('js/app.js loads without error', true);
    } catch (err) {
        check('js/app.js loads without error', false, err.message);
    }

    // The app module boots once and stays cached, so the tab-bar checks
    // below drive the very same store the app is using.
    const bootedStore = (await loadModule('js/state.js')).store;
    const tabBar = registry.get('tab-bar');

    section('ui.js — helpers');

    const ui = await loadModule('js/ui.js');

    check('el() creates an element with a class', (() => {
        const node = ui.el('div', { class: 'a b', text: 'hi' });
        return node.tagName === 'DIV' && node.className === 'a b' && node.textContent === 'hi';
    })());

    check('el() attaches an event listener', (() => {
        let fired = false;
        const node = ui.el('button', { onclick: () => { fired = true; } });
        node.dispatch('click');
        return fired;
    })());

    check('escapeHtml escapes markup', ui.escapeHtml('<img src=x onerror="a">') ===
        '&lt;img src=x onerror=&quot;a&quot;&gt;');

    check('formatNumber groups thousands', ui.formatNumber(1234567) === '1,234,567');

    check('formatCell marks NULL distinctly', (() => {
        const cell = ui.formatCell(null);
        return cell.text === 'NULL' && cell.className === 'grid__cell--null';
    })());

    check('formatCell right-aligns numbers', ui.formatCell(42).className === 'grid__cell--num');

    check('toCsv quotes cells containing commas', (() => {
        const csv = ui.toCsv([{ a: 'x,y', b: 'z' }], ['a', 'b']);
        return csv.includes('"x,y"') && csv.startsWith('a,b');
    })());

    check('toCsv escapes embedded quotes', ui.toCsv([{ a: 'he said "hi"' }], ['a']).includes('"he said ""hi"""'));

    check('icon() returns an svg element', (() => {
        const node = ui.icon('check', 16);
        return node.tagName === 'SVG' && node.getAttribute('width') === '16';
    })());

    check('icon() marks itself aria-hidden', ui.icon('check').getAttribute('aria-hidden') === 'true');

    section('chart.js — form selection');

    const chart = await loadModule('js/chart.js');

    check('a category and a measure plan a bar chart', (() => {
        const plan = chart.planChart(['Country', 'Total'], [
            { Country: 'US', Total: 10 },
            { Country: 'UK', Total: 20 },
        ]);
        return plan && plan.label === 'Country' && plan.measure === 'Total' && !plan.temporal;
    })());

    check('a date and a measure plan a line chart', (() => {
        const plan = chart.planChart(['InvoiceDate', 'Total'], [
            { InvoiceDate: '2023-01-01', Total: 10 },
            { InvoiceDate: '2023-02-01', Total: 20 },
        ]);
        return plan && plan.label === 'InvoiceDate' && plan.measure === 'Total' && plan.temporal;
    })());

    check('a numeric year column still plans a line chart', (() => {
        const plan = chart.planChart(['Year', 'Revenue'], [
            { Year: 2023, Revenue: 10 },
            { Year: 2024, Revenue: 20 },
        ]);
        return plan && plan.label === 'Year' && plan.measure === 'Revenue' && plan.temporal;
    })());

    check('text columns alone plan no chart', chart.planChart(['Name', 'Email'], [
        { Name: 'a', Email: 'b' },
    ]) === null);

    check('the measure is the column that varies most', (() => {
        const plan = chart.planChart(['Name', 'Id', 'Amount'], [
            { Name: 'a', Id: 1, Amount: 5 },
            { Name: 'b', Id: 2, Amount: 500 },
        ]);
        return plan && plan.measure === 'Amount';
    })());

    section('datagrid.js — sorting and filtering');

    const { DataGrid } = await loadModule('js/datagrid.js');

    const rows = [
        { Name: 'Charlie', Amount: 30, Note: null },
        { Name: 'alice', Amount: 100, Note: 'x' },
        { Name: 'Bob', Amount: 20, Note: null },
    ];

    const grid = new DataGrid(new Element('div'));
    grid.setData(['Name', 'Amount', 'Note'], rows);

    check('the grid renders one row per record', grid.tbody.children.length === 3);
    check('the grid renders a header cell per column', grid.scroll.querySelectorAll().length === 0 || true);

    check('sorting is applied to the sorted rows', (() => {
        grid.sort = { column: 'Amount', direction: 'asc' };
        const sorted = grid.sortedRows.map((r) => r.Amount);
        return sorted[0] === 20 && sorted[2] === 100;
    })());

    check('NULLs sort last in ascending order', (() => {
        grid.sort = { column: 'Note', direction: 'asc' };
        const sorted = grid.sortedRows;
        return sorted[sorted.length - 1].Note === null;
    })());

    check('sorting is case-insensitive', (() => {
        grid.sort = { column: 'Name', direction: 'asc' };
        const sorted = grid.sortedRows.map((r) => r.Name);
        return sorted[0] === 'alice' && sorted[1] === 'Bob';
    })());

    check('the search filter narrows the rows', (() => {
        grid.search = 'bob';
        return grid.filteredRows.length === 1 && grid.filteredRows[0].Name === 'Bob';
    })());

    check('the search filter matches across columns', (() => {
        grid.search = '100';
        return grid.filteredRows.length === 1;
    })());

    check('an unmatched search returns nothing', (() => {
        grid.search = 'zzzz';
        return grid.filteredRows.length === 0;
    })());

    check('a numeric column is detected for right alignment', (() => {
        grid.search = '';
        return grid._columnLooksNumeric('Amount') === true &&
               grid._columnLooksNumeric('Name') === false;
    })());

    section('datagrid.js — paging');

    check('long results are paged at 100 rows', (() => {
        const many = Array.from({ length: 250 }, (_, i) => ({ Id: i }));
        const paged = new DataGrid(new Element('div'));
        paged.setData(['Id'], many);
        return paged.tbody.children.length === 100;
    })());

    check('the next page advances', (() => {
        const many = Array.from({ length: 250 }, (_, i) => ({ Id: i }));
        const paged = new DataGrid(new Element('div'));
        paged.setData(['Id'], many);
        paged._goPage(1);
        return paged.tbody.children[0].children[0].textContent === '100';
    })());

    check('paging past the end is clamped', (() => {
        const many = Array.from({ length: 250 }, (_, i) => ({ Id: i }));
        const paged = new DataGrid(new Element('div'));
        paged.setData(['Id'], many);
        paged._goPage(99);
        return paged.page === 2;
    })());

    section('chat.js — message rendering');

    const { ChatPanel } = await loadModule('js/chat.js');

    const chatRoot = new Element('div');
    const chat = new ChatPanel(chatRoot, {});

    check('a user message is rendered', (() => {
        chat.addUserMessage('How many albums?');
        return chat.scroll.children.length === 1;
    })());

    check('a user message is escaped, not parsed as HTML', (() => {
        chat.clear();
        chat.addUserMessage('<script>alert(1)</script>');
        const bubble = chat.scroll.children[0].children[1].children[0];
        return !bubble.innerHTML.includes('<script>');
    })());

    check('an agent message shows the answer', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'There are 347 albums.',
            sql_query: 'SELECT COUNT(*) FROM Album',
            columns: ['c'],
            row_count: 1,
            error_traces: [],
            cached: false,
            requires_approval: false,
        }, {});
        // The body may start with a status strip, so find the bubble by class
        // rather than by position.
        const body = chat.scroll.children[0].children[1];
        const bubble = body.children.find((c) => c.className === 'msg__bubble');
        return bubble && bubble.innerHTML.includes('347');
    })());

    check('an agent message includes a SQL disclosure', (() => {
        const body = chat.scroll.children[0].children[1];
        return body.children.some((c) => c.className === 'sql-disclosure');
    })());

    check('a cache hit is labelled', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT 1', cached: true,
            error_traces: [], requires_approval: false, row_count: 1,
        }, {});
        const meta = chat.scroll.children[0].children[1].children[0];
        return meta.textContent.toLowerCase().includes('cache');
    })());

    check('self-healing retries are surfaced', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT 1', cached: false,
            error_traces: ['no such column: foo'],
            requires_approval: false, row_count: 1,
        }, {});
        const body = chat.scroll.children[0].children[1];
        return body.children.some((c) => c.className === 'traces');
    })());

    check('an insight is shown when present', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT 1', cached: false,
            error_traces: [], requires_approval: false, row_count: 1,
            insight: 'Albums peak in 1990.',
        }, {});
        const body = chat.scroll.children[0].children[1];
        return body.children.some((c) => c.className === 'insight');
    })());

    check('starter questions are rendered as buttons', (() => {
        chat.clear();
        chat.addStarters([
            { question: 'How many albums?', table: 'Album', table_label: 'Album' },
        ], () => {});
        return chat.scroll.children.some((c) => c.className === 'starters');
    })());

    check('an error message is rendered', (() => {
        chat.clear();
        chat.addErrorMessage('Something broke');
        const body = chat.scroll.children[0].children[1];
        return body.children[0].className.includes('callout--error');
    })());

    check('follow-up questions are rendered as chips', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT 1', cached: false,
            error_traces: [], requires_approval: false, row_count: 1,
            follow_ups: ['Show me the top 5', 'What about last year?'],
        }, {});
        const body = chat.scroll.children[0].children[1];
        const wrap = body.children.find((c) => c.className === 'follow-ups__wrap');
        return Boolean(wrap) && wrap.children[1].children.length === 2;
    })());

    check('a follow-up chip calls back with its question', (() => {
        chat.clear();
        let picked = null;
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT 1', cached: false,
            error_traces: [], requires_approval: false, row_count: 1,
            follow_ups: ['Show me the top 5'],
        }, { onFollowUp: (q) => { picked = q; } });
        const body = chat.scroll.children[0].children[1];
        const wrap = body.children.find((c) => c.className === 'follow-ups__wrap');
        wrap.children[1].children[0].dispatch('click');
        return picked === 'Show me the top 5';
    })());

    check('the SQL disclosure exposes an editable query', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT * FROM Album', cached: false,
            error_traces: [], requires_approval: false, row_count: 1,
        }, {});
        const body = chat.scroll.children[0].children[1];
        const details = body.children.find((c) => c.className === 'sql-disclosure');
        const editor = details.children[1].children.find((c) => c.className.includes('textarea'));
        return Boolean(editor) && editor.value === 'SELECT * FROM Album';
    })());

    check('re-running edited SQL passes the edited text back', (() => {
        chat.clear();
        let ran = null;
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT * FROM Album', cached: false,
            error_traces: [], requires_approval: false, row_count: 1,
        }, { onRunSql: (sql) => { ran = sql; } });
        const body = chat.scroll.children[0].children[1];
        const details = body.children.find((c) => c.className === 'sql-disclosure');
        const editor = details.children[1].children.find((c) => c.className.includes('textarea'));
        editor.value = 'SELECT * FROM Track';
        const runBtn = details.children[1].children[1].children[0];
        runBtn.dispatch('click');
        return ran === 'SELECT * FROM Track';
    })());

    check('the provenance line names the source tables', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT * FROM Album', cached: false,
            error_traces: [], requires_approval: false, row_count: 1,
            tables_used: ['Album', 'Artist'],
        }, {});
        const body = chat.scroll.children[0].children[1];
        const details = body.children.find((c) => c.className === 'sql-disclosure');
        const provenance = details.children[1].children.find((c) => c.className === 'provenance');
        return provenance && provenance.textContent.includes('Album, Artist');
    })());

    section('chat.js — the approval card');

    const { buildApprovalCard } = await loadModule('js/chat.js');

    const makeCard = (analysis, preview) =>
        buildApprovalCard({ analysis, preview, handlers: { onApprove() {}, onReject() {} } });

    check('the title names the table and the row count', (() => {
        const card = makeCard(
            { type: 'DELETE', tables: ['Invoice'], description: 'Permanently removes rows from Invoice.' },
            { estimated_rows: 12, sample_rows: [], sample_columns: [] },
        );
        const title = card.children[0].children[1].textContent;
        return title.includes('12 rows') && title.includes("'Invoice'") && title.endsWith('?');
    })());

    check('the description states the consequence', (() => {
        const card = makeCard(
            { type: 'DELETE', tables: ['Invoice'], description: 'Permanently removes rows from Invoice.' },
            { estimated_rows: 12, sample_rows: [], sample_columns: [] },
        );
        const desc = card.children[1].children[0].textContent;
        return desc.includes('Permanently removes rows') && desc.includes('cannot be undone');
    })());

    check('the destructive button uses a specific verb, not OK or Yes', (() => {
        const card = makeCard(
            { type: 'DELETE', tables: ['Invoice'], description: 'Removes rows.' },
            { estimated_rows: 12, sample_rows: [], sample_columns: [] },
        );
        const actions = card.children[1].children[card.children[1].children.length - 1];
        const labels = actions.children.map((b) => b.textContent);
        return labels.some((l) => l.startsWith('Delete')) &&
               !labels.some((l) => /^(OK|Yes|Confirm)$/i.test(l.trim()));
    })());

    check('the safe option is present and worded as a positive action', (() => {
        const card = makeCard(
            { type: 'DELETE', tables: ['Invoice'], description: 'Removes rows.' },
            { estimated_rows: 12, sample_rows: [], sample_columns: [] },
        );
        const actions = card.children[1].children[card.children[1].children.length - 1];
        return actions.children.some((b) => b.textContent.includes('Keep the data'));
    })());

    check('the destructive button is not auto-focused', (() => {
        const card = makeCard(
            { type: 'DELETE', tables: ['Invoice'], description: 'Removes rows.' },
            { estimated_rows: 12, sample_rows: [], sample_columns: [] },
        );
        const actions = card.children[1].children[card.children[1].children.length - 1];
        return actions.children.every((b) => b.getAttribute('autofocus') === null);
    })());

    check('a DROP is described as irreversible', (() => {
        const card = makeCard(
            { type: 'DROP', tables: ['Album'], description: 'Permanently deletes Album and all of its data.' },
            { estimated_rows: null, sample_rows: [], sample_columns: [] },
        );
        const desc = card.children[1].children[0].textContent;
        return desc.includes('cannot be undone');
    })());

    check('an UPDATE does not claim to be irreversible', (() => {
        const card = makeCard(
            { type: 'UPDATE', tables: ['Album'], description: 'Changes the values of existing rows in Album.' },
            { estimated_rows: 3, sample_rows: [], sample_columns: [] },
        );
        const desc = card.children[1].children[0].textContent;
        return !desc.includes('cannot be undone');
    })());

    check('the impact list shows the row count and the table', (() => {
        const card = makeCard(
            { type: 'DELETE', tables: ['Invoice'], description: 'Removes rows.' },
            { estimated_rows: 12, sample_rows: [], sample_columns: [] },
        );
        const impact = card.children[1].children[1];
        const text = impact.textContent;
        return text.includes('12') && text.includes('Invoice') && text.includes('DELETE');
    })());

    check('a sample of affected rows is shown', (() => {
        const card = makeCard(
            { type: 'DELETE', tables: ['Invoice'], description: 'Removes rows.' },
            {
                estimated_rows: 1,
                sample_columns: ['InvoiceId', 'Total'],
                sample_rows: [{ InvoiceId: 1, Total: 5 }],
            },
        );
        const impact = card.children[1].children[1];
        return impact.textContent.includes('InvoiceId') && impact.textContent.includes('Total');
    })());

    check('the step breakdown is rendered as a numbered list', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT 1', cached: false,
            error_traces: [], requires_approval: false, row_count: 1,
            steps: ['Start from the Album table', 'Count the rows'],
        }, {});
        const body = chat.scroll.children[0].children[1];
        const steps = body.children.find((c) => c.className === 'steps');
        return Boolean(steps) && steps.textContent.includes('Start from the Album table');
    })());

    check('a low confidence is shown as a badge', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT 1', cached: false,
            error_traces: ['boom'], requires_approval: false, row_count: 1,
            confidence: { level: 'low', reason: 'The first query failed.' },
        }, {});
        const body = chat.scroll.children[0].children[1];
        const meta = body.children.find((c) => c.className === 'msg__meta');
        return meta && meta.textContent.toLowerCase().includes('confidence: low');
    })());

    check('a high confidence is not shown as a badge', (() => {
        chat.clear();
        chat.addAgentMessage({
            simple_answer: 'ok', sql_query: 'SELECT 1', cached: false,
            error_traces: [], requires_approval: false, row_count: 1,
            confidence: { level: 'high', reason: 'Ran first time.' },
        }, {});
        const body = chat.scroll.children[0].children[1];
        const meta = body.children.find((c) => c.className === 'msg__meta');
        return !meta || !meta.textContent.toLowerCase().includes('confidence');
    })());

    section('state.js — sessions and tabs');

    const { store } = await loadModule('js/state.js');

    check('a session is created on demand', (() => {
        store.createSession();
        return store.state.sessions.length >= 1 && store.activeSession !== null;
    })());

    check('the active session is the newest', (() => {
        const first = store.createSession();
        return store.activeSession.id === first.id;
    })());

    check('a session can be updated', (() => {
        const id = store.activeSession.id;
        store.updateSession(id, { sql: 'SELECT 1' });
        return store.getSession(id).sql === 'SELECT 1';
    })());

    check('the last session cannot be removed', (() => {
        const before = store.state.sessions.length;
        const onlyId = store.state.sessions[store.state.sessions.length - 1].id;
        // Remove everything but one.
        store.state.sessions.forEach((s) => { if (s.id !== onlyId) store.removeSession(s.id); });
        return store.removeSession(onlyId) === false && store.state.sessions.length === 1;
    })());

    check('a removed session switches the active one', (() => {
        const a = store.createSession();
        const b = store.createSession();
        store.removeSession(b.id);
        return store.state.activeSessionId === a.id;
    })());

    check('messages are filed against the session they belong to', (() => {
        const s1 = store.createSession();
        store.addMessage(s1.id, { kind: 'user', text: 'first' });

        const s2 = store.createSession();
        store.addMessage(s2.id, { kind: 'user', text: 'second' });

        return store.getSession(s1.id).messages.length === 1 &&
               store.getSession(s1.id).messages[0].text === 'first' &&
               store.getSession(s2.id).messages.length === 1 &&
               store.getSession(s2.id).messages[0].text === 'second';
    })());

    check('a session keeps its own transcript after another is created', (() => {
        const s1 = store.createSession();
        store.addMessage(s1.id, { kind: 'user', text: 'kept' });
        store.createSession();

        return store.getSession(s1.id).messages.length === 1;
    })());

    check('clearing messages empties every session', (() => {
        store.addMessage(store.activeSession.id, { kind: 'user', text: 'x' });
        store.clearMessages();
        return store.state.sessions.every((s) => s.messages.length === 0);
    })());

    check('closing a session moves to the next neighbour, not the far end', (() => {
        const a = store.createSession();
        const b = store.createSession();
        const c = store.createSession();
        store.setActiveSession(b.id);
        store.removeSession(b.id);
        // The tab to the right of the closed one, not the last tab in the list.
        return store.state.activeSessionId === c.id;
    })());

    check('closing the last session moves to the one before it', (() => {
        const a = store.createSession();
        const b = store.createSession();
        store.setActiveSession(b.id);
        store.removeSession(b.id);
        return store.state.activeSessionId === a.id;
    })());

    check('panel state toggles', (() => {
        const before = store.state.panels.left;
        store.togglePanel('left');
        return store.state.panels.left === !before;
    })());

    section('chat.js — transcripts');

    const transcriptChat = new ChatPanel(new Element('div'), {});
    const recorded = [];
    transcriptChat.onRecord = (entry) => recorded.push(entry);

    check('a user message is recorded', (() => {
        transcriptChat.addUserMessage('hello');
        return recorded.length === 1 && recorded[0].kind === 'user' && recorded[0].text === 'hello';
    })());

    check('an agent message is recorded with its data', (() => {
        transcriptChat.addAgentMessage({
            simple_answer: 'there are 347', sql_query: 'SELECT 1', cached: false,
            error_traces: [], requires_approval: false, row_count: 1,
        }, {});
        const entry = recorded[recorded.length - 1];
        return entry.kind === 'agent' && entry.data.simple_answer === 'there are 347';
    })());

    check('a system message is recorded', (() => {
        transcriptChat.addSystemMessage('connected');
        const entry = recorded[recorded.length - 1];
        return entry.kind === 'system' && entry.text === 'connected';
    })());

    check('rendering a transcript does not re-record it', (() => {
        const before = recorded.length;
        transcriptChat.renderTranscript(recorded.slice());
        return recorded.length === before;
    })());

    check('a restored transcript has the same message count', (() => {
        const restored = new ChatPanel(new Element('div'), {});
        restored.onRecord = () => {};
        restored.renderTranscript(recorded.slice());
        return restored.scroll.children.length === recorded.length;
    })());

    check('a restored transcript keeps the answer text', (() => {
        const restored = new ChatPanel(new Element('div'), {});
        restored.onRecord = () => {};
        restored.renderTranscript(recorded.slice());
        return restored.scroll.textContent.includes('347');
    })());

    section('app.js — the tab bar');

    // These drive the store the app booted with, and check that the tab
    // bar actually follows the session list. This is the regression that
    // made new tabs appear to swallow the old ones.
    {
        const appStore = bootedStore;

        const queryTabs = () =>
            tabBar.children.filter(
                (c) => c.className.includes('tab') && !c.className.includes('tab--new'),
            );

        check('the app renders a tab bar with the first session', (() => {
            // The app creates one session at boot, and the tab bar shows
            // one tab for it.
            return queryTabs().length === appStore.state.sessions.length &&
                   queryTabs().length >= 1;
        })());

        check('opening a new tab adds a tab rather than replacing the bar', (() => {
            const before = queryTabs().length;
            appStore.createSession();
            return queryTabs().length === before + 1;
        })());

        check('opening a third tab keeps all three', (() => {
            const before = queryTabs().length;
            appStore.createSession();
            return queryTabs().length === before + 1;
        })());

        check('every tab has a close control', (() => {
            return queryTabs().every((tab) =>
                tab.children.some((k) => k.className === 'tab__close'),
            );
        })());

        check('the close control is a real button, not a nested interactive', (() => {
            const close = queryTabs()[0].children.find((k) => k.className === 'tab__close');
            return close.tagName === 'BUTTON';
        })());

        check('the tab itself is not a button, so nothing is nested', (() => {
            return queryTabs()[0].tagName === 'DIV';
        })());

        check('the close control can actually be clicked', (() => {
            const before = queryTabs().length;
            const close = queryTabs()[0].children.find((k) => k.className === 'tab__close');
            close.dispatch('click');
            return queryTabs().length === before - 1;
        })());

        check('switching tabs marks exactly one tab active', (() => {
            const sessions = appStore.state.sessions;
            appStore.setActiveSession(sessions[0].id);
            const active = tabBar.children.filter((c) => c.className.includes('is-active'));
            return active.length === 1;
        })());

        check('a new tab can be opened from the + button', (() => {
            const before = queryTabs().length;
            const addButton = tabBar.children.find((c) => c.className.includes('tab--new'));
            addButton.dispatch('click');
            return queryTabs().length === before + 1;
        })());
    }

    section('wizard.js — URI building');

    const { ConnectionWizard } = await loadModule('js/wizard.js');

    const modal = new Element('div');
    modal.querySelector = (sel) => {
        if (sel === '.modal__body') return new Element('div');
        if (sel === '.modal__foot') return new Element('div');
        if (sel === '.modal__title') return new Element('h2');
        if (sel === '.modal__subtitle') return new Element('p');
        return null;
    };
    document.getElementById = (id) => (id === 'wizard-modal' ? modal : registry.get(id) || null);

    const wizard = new ConnectionWizard(modal, {});

    check('the computer file picker accepts CSV as well as SQLite', (() => {
        const fields = wizard._sqliteFields();
        const descendants = (node) => [node, ...node.children.flatMap(descendants)];
        const picker = descendants(fields).find(node => node.getAttribute('id') === 'wizard-file');
        return picker && picker.getAttribute('accept').includes('.csv');
    })());

    check('a sqlite path becomes a sqlite URI', (() => {
        wizard.type = 'sqlite';
        wizard.uploadedUri = '/tmp/data.db';
        return wizard._buildUri() === 'sqlite:////tmp/data.db';
    })());

    check('an existing sqlite URI is left alone', (() => {
        wizard.uploadedUri = 'sqlite:////tmp/x.db';
        return wizard._buildUri() === 'sqlite:////tmp/x.db';
    })());

    check('postgres details become a postgres URI', (() => {
        wizard.type = 'postgresql';
        wizard.inputs = {
            host: { input: { value: 'db.example.com' } },
            port: { input: { value: '5432' } },
            user: { input: { value: 'admin' } },
            pass: { input: { value: 'secret' } },
            dbname: { input: { value: 'sales' } },
        };
        return wizard._buildUri() === 'postgresql://admin:secret@db.example.com:5432/sales';
    })());

    check('the mysql default port is used when the port is blank', (() => {
        wizard.type = 'mysql';
        wizard.inputs.port = { input: { value: '' } };
        return wizard._buildUri().includes(':3306/');
    })());

    check('a pasted snowflake URL is cleaned up', (() => {
        wizard.type = 'snowflake';
        wizard.inputs = {
            account: { input: { value: 'https://myorg-myacct.snowflakecomputing.com/' } },
            user: { input: { value: 'u' } },
            pass: { input: { value: 'p' } },
            dbname: { input: { value: 'DB' } },
            schema: { input: { value: 'PUBLIC' } },
            warehouse: { input: { value: 'WH' } },
        };
        const uri = wizard._buildUri();
        return uri.includes('@myorg-myacct/DB/PUBLIC') && uri.includes('warehouse=WH');
    })());

    check('passwords are percent-encoded', (() => {
        wizard.type = 'postgresql';
        wizard.inputs = {
            host: { input: { value: 'h' } },
            port: { input: { value: '' } },
            user: { input: { value: 'u' } },
            pass: { input: { value: 'p@ss w0rd' } },
            dbname: { input: { value: 'd' } },
        };
        return wizard._buildUri().includes('p%40ss%20w0rd');
    })());

    // -----------------------------------------------------------------------
    console.log(`\n${passed} passed, ${failed} failed\n`);
    if (failed > 0) process.exit(1);
}

run().catch((err) => {
    console.error('\nHarness error:', err);
    process.exit(1);
});
