/**
 * The result data grid.
 *
 * A sortable, filterable, searchable table with CSV/JSON export. The table
 * uses native <table> semantics so a screen reader announces rows and cells
 * correctly; sorting state is exposed with aria-sort on the header cell.
 *
 * Long result sets are paged rather than windowed. Paging keeps the DOM small
 * and, unlike an infinite scroll, gives the user a way to say "where am I in
 * this data" and to jump to the end.
 */

import { el, formatCell, toCsv, downloadText, debounce, icon } from './ui.js';
import { toast } from './toast.js';

const PAGE_SIZE = 100;   // rows shown per page

export class DataGrid {
    /**
     * @param {HTMLElement} root
     */
    constructor(root) {
        this.root = root;
        this.columns = [];
        this.rows = [];
        this.sort = { column: null, direction: 'asc' };
        this.search = '';
        this.page = 0;
        this.pageSize = PAGE_SIZE;

        this._build();
    }

    _build() {
        this.toolbar = el('div', { class: 'grid__toolbar' });
        this.scroll = el('div', { class: 'grid__scroll' });
        this.foot = el('div', { class: 'grid__foot' });

        this.root.replaceChildren(this.toolbar, this.scroll, this.foot);
        this._renderToolbar();
    }

    /**
     * Replace the grid's contents.
     * @param {string[]} columns
     * @param {object[]} rows
     * @param {{truncated?: boolean}} options
     */
    setData(columns, rows, options = {}) {
        this.columns = columns || [];
        this.rows = rows || [];
        this.truncated = Boolean(options.truncated);
        this.sort = { column: null, direction: 'asc' };
        this.search = '';
        this.page = 0;

        this._renderToolbar();
        this._render();
    }

    /** The rows currently visible, after search and sort. */
    get filteredRows() {
        if (!this.search) return this.rows;
        const needle = this.search.toLowerCase();
        return this.rows.filter((row) =>
            this.columns.some((column) =>
                String(row[column] ?? '').toLowerCase().includes(needle),
            ),
        );
    }

    get sortedRows() {
        const rows = this.filteredRows;
        if (!this.sort.column) return rows;

        const column = this.sort.column;
        const direction = this.sort.direction === 'asc' ? 1 : -1;

        return [...rows].sort((a, b) => {
            const av = a[column];
            const bv = b[column];

            // NULLs sort last in both directions - they are the absence of a value.
            if (av === null || av === undefined) return 1;
            if (bv === null || bv === undefined) return -1;

            if (typeof av === 'number' && typeof bv === 'number') {
                return (av - bv) * direction;
            }
            return String(av).localeCompare(String(bv), undefined, { numeric: true }) * direction;
        });
    }

    // --- Toolbar ------------------------------------------------------------

    _renderToolbar() {
        const searchInput = el('input', {
            class: 'input',
            type: 'search',
            placeholder: 'Filter rows…',
            'aria-label': 'Filter result rows by text',
        });

        const onSearch = debounce((value) => {
            this.search = value.trim();
            this.page = 0;
            this._render();
        }, 160);

        searchInput.addEventListener('input', (e) => onSearch(e.target.value));

        this.searchInput = searchInput;

        const count = el('span', { class: 'grid__count' });
        this.countNode = count;

        this.toolbar.replaceChildren(
            el(
                'div',
                { class: 'grid__search' },
                icon('search', 13),
                searchInput,
            ),
            count,
            el('div', { class: 'grid__spacer' }),
            el(
                'button',
                {
                    class: 'btn btn--ghost btn--sm',
                    onclick: () => this.exportCsv(),
                    title: 'Download these results as a CSV file',
                },
                icon('download', 13),
                'CSV',
            ),
            el(
                'button',
                {
                    class: 'btn btn--ghost btn--sm',
                    onclick: () => this.exportJson(),
                    title: 'Download these results as a JSON file',
                },
                icon('download', 13),
                'JSON',
            ),
        );
    }

    // --- Table --------------------------------------------------------------

    _render() {
        const rows = this.sortedRows;
        const total = this.rows.length;

        if (this.countNode) {
            const shown = rows.length;
            const filtered = shown !== total;
            this.countNode.textContent = filtered
                ? `${shown.toLocaleString()} of ${total.toLocaleString()} rows`
                : `${total.toLocaleString()} row${total === 1 ? '' : 's'}`;
        }

        if (!this.columns.length || !total) {
            this.scroll.replaceChildren(
                el(
                    'div',
                    { class: 'panel__empty' },
                    icon('table2', 28),
                    el('div', { class: 'panel__empty-title', text: 'No rows returned' }),
                    el('div', {
                        class: 'panel__empty-text',
                        text: 'The query ran successfully but matched no data. Try widening the filters in your question.',
                    }),
                ),
            );
            this.foot.replaceChildren();
            return;
        }

        const head = el(
            'tr',
            {},
            ...this.columns.map((column) => this._headerCell(column)),
        );

        const body = el('tbody');
        this.tbody = body;

        // aria-rowcount and aria-rowindex let a screen reader announce
        // "row 5 of 347" even though only one page is in the DOM. The counts
        // include the header row, per the ARIA grid practice.
        const rowCount = rows.length + 1;

        const table = el(
            'table',
            {
                class: 'grid__table',
                role: 'grid',
                'aria-rowcount': String(rowCount),
                'aria-colcount': String(this.columns.length),
            },
            el('thead', {}, head),
            body,
        );

        this.scroll.replaceChildren(table);
        this._renderRows();

        this._renderFoot(rows.length);
    }

    _headerCell(column) {
        const isSorted = this.sort.column === column;
        const isNumeric = this._columnLooksNumeric(column);

        const th = el('th', {
            scope: 'col',
            'aria-sort': isSorted ? (this.sort.direction === 'asc' ? 'ascending' : 'descending') : 'none',
        });

        const button = el(
            'button',
            {
                class: `grid__sort${isNumeric ? ' grid__sort--numeric' : ''}`,
                type: 'button',
                onclick: () => this._toggleSort(column),
                'aria-label': `Sort by ${column}`,
            },
            el('span', { text: column }),
            icon('chevronDown', 12, 'grid__sort-icon'),
        );

        th.append(button);
        return th;
    }

    _toggleSort(column) {
        if (this.sort.column === column) {
            // asc -> desc -> unsorted
            if (this.sort.direction === 'asc') {
                this.sort = { column, direction: 'desc' };
            } else {
                this.sort = { column: null, direction: 'asc' };
            }
        } else {
            this.sort = { column, direction: 'asc' };
        }
        this._render();
    }

    _columnLooksNumeric(column) {
        const sample = this.rows.find((row) => row[column] !== null && row[column] !== undefined);
        return sample ? typeof sample[column] === 'number' : false;
    }

    /**
     * Render the current page of rows.
     */
    _renderRows() {
        if (!this.tbody) return;

        const rows = this.sortedRows;
        const total = rows.length;

        const start = Math.max(0, this.page * this.pageSize);
        const end = Math.min(total, start + this.pageSize);
        const visible = rows.slice(start, end);

        const fragment = document.createDocumentFragment();
        visible.forEach((row, offset) => {
            // aria-rowindex is 1-based and counts the header row, so the
            // first data row on the first page is row 2.
            const tr = el('tr', { 'aria-rowindex': String(start + offset + 2) });
            for (const column of this.columns) {
                const { text, className } = formatCell(row[column]);
                const td = el('td', { class: className, title: text });
                td.textContent = text;
                tr.append(td);
            }
            fragment.append(tr);
        });
        this.tbody.replaceChildren(fragment);

        this.renderedRange = { start, end, total };
    }

    _renderFoot(visibleCount) {
        const { start, end, total } = this.renderedRange || { start: 0, end: 0, total: 0 };

        const parts = [];

        if (total > visibleCount) {
            parts.push(
                `Showing ${(start + 1).toLocaleString()}–${end.toLocaleString()} of ${total.toLocaleString()}`,
            );
        } else {
            parts.push(`${total.toLocaleString()} row${total === 1 ? '' : 's'}`);
        }

        if (this.truncated) {
            parts.push('result was truncated by the server');
        }

        const nav = el('div', { class: 'grid__foot' });

        if (total > visibleCount) {
            nav.append(
                el(
                    'button',
                    {
                        class: 'btn btn--ghost btn--sm',
                        onclick: () => this._goPage(0),
                        disabled: start === 0,
                        'aria-label': 'First page',
                    },
                    'First',
                ),
                el(
                    'button',
                    {
                        class: 'btn btn--ghost btn--sm',
                        onclick: () => this._goPage(this.page - 1),
                        disabled: start === 0,
                        'aria-label': 'Previous page',
                    },
                    'Previous',
                ),
                el(
                    'button',
                    {
                        class: 'btn btn--ghost btn--sm',
                        onclick: () => this._goPage(this.page + 1),
                        disabled: end >= total,
                        'aria-label': 'Next page',
                    },
                    'Next',
                ),
            );
        }

        nav.append(el('span', { text: parts.join(' · ') }));

        this.foot.replaceChildren(nav);
    }

    _goPage(page) {
        const totalPages = Math.ceil(this.filteredRows.length / this.pageSize);
        this.page = Math.max(0, Math.min(page, totalPages - 1));
        this._renderRows();
        this._renderFoot(this.filteredRows.length);
        this.scroll.scrollTop = 0;
    }

    // --- Export --------------------------------------------------------------

    exportCsv() {
        if (!this.rows.length) {
            toast('There are no rows to export.', 'warning');
            return;
        }
        const csv = toCsv(this.sortedRows, this.columns);
        downloadText('query-results.csv', csv, 'text/csv;charset=utf-8');
        toast(`Exported ${this.sortedRows.length.toLocaleString()} rows to CSV.`, 'success');
    }

    exportJson() {
        if (!this.rows.length) {
            toast('There are no rows to export.', 'warning');
            return;
        }
        const payload = this.sortedRows.map((row) => {
            const out = {};
            for (const column of this.columns) out[column] = row[column];
            return out;
        });
        downloadText('query-results.json', JSON.stringify(payload, null, 2), 'application/json');
        toast(`Exported ${this.sortedRows.length.toLocaleString()} rows to JSON.`, 'success');
    }
}
