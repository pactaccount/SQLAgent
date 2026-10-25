/**
 * The schema explorer.
 *
 * A searchable tree of the connected database's tables and columns. Clicking
 * a table asks the agent about it, so the tree is a way in, not just a
 * reference.
 */

import { el, icon, debounce } from './ui.js';

export class SchemaExplorer {
    /**
     * @param {HTMLElement} root
     * @param {{onAskAbout: (question: string) => void}} handlers
     */
    constructor(root, handlers = {}) {
        this.root = root;
        this.handlers = handlers;
        this.tables = [];
        this.expanded = new Set();

        this.search = el('input', {
            class: 'input',
            type: 'search',
            placeholder: 'Search tables and columns…',
            'aria-label': 'Search tables and columns',
        });

        this.list = el('ul', { class: 'tree', role: 'tree', 'aria-label': 'Database tables' });

        const onSearch = debounce((value) => this._filter(value), 140);
        this.search.addEventListener('input', (e) => onSearch(e.target.value));

        this.root.replaceChildren(
            el('div', { class: 'explorer__search' }, this.search),
            el('div', { class: 'explorer' }, this.list),
        );

        this._renderEmpty('Connect a database to see its tables.');
    }

    _renderEmpty(message) {
        this.list.replaceChildren(
            el(
                'li',
                { class: 'panel__empty' },
                icon('database', 24),
                el('div', { class: 'panel__empty-title', text: 'No database connected' }),
                el('div', { class: 'panel__empty-text', text: message }),
            ),
        );
    }

    /**
     * Set the schema to display.
     * @param {{name: string, columns: {name: string, type: string}[]}[]} tables
     */
    setTables(tables) {
        this.tables = tables || [];
        this._render();
    }

    _filter(term) {
        this.term = term.trim().toLowerCase();
        this._render();
    }

    _matches(table) {
        if (!this.term) return true;
        if (table.name.toLowerCase().includes(this.term)) return true;
        return table.columns.some((col) => col.name.toLowerCase().includes(this.term));
    }

    _render() {
        if (!this.tables.length) {
            this._renderEmpty('Connect a database to see its tables.');
            return;
        }

        const visible = this.tables.filter((t) => this._matches(t));

        if (!visible.length) {
            this.list.replaceChildren(
                el(
                    'li',
                    { class: 'panel__empty' },
                    icon('search', 22),
                    el('div', { class: 'panel__empty-title', text: 'No matches' }),
                    el('div', {
                        class: 'panel__empty-text',
                        text: `Nothing in the schema matches "${this.term}".`,
                    }),
                ),
            );
            return;
        }

        const items = visible.map((table) => this._tableNode(table));
        this.list.replaceChildren(...items);
    }

    _tableNode(table) {
        const isOpen = this.expanded.has(table.name) || Boolean(this.term);
        const columns = el('ul', {
            class: `tree__cols${isOpen ? ' is-open' : ''}`,
            role: 'group',
        });

        for (const column of table.columns) {
            const columnNode = el(
                'li',
                {
                    class: 'tree__col',
                    role: 'treeitem',
                    'aria-label': `${column.name}, ${column.type}`,
                    title: 'Click to ask the agent about this column',
                    onclick: () =>
                        this.handlers.onAskAbout?.(
                            `What can you tell me about the "${column.name}" column in ${table.name}?`,
                        ),
                },
                el('span', { class: 'tree__col-name', text: column.name }),
                el('span', { class: 'tree__col-type', text: column.type }),
            );
            columns.append(columnNode);
        }

        const node = el(
            'button',
            {
                class: 'tree__node',
                type: 'button',
                role: 'treeitem',
                'aria-expanded': String(isOpen),
                onclick: () => {
                    if (this.expanded.has(table.name)) {
                        this.expanded.delete(table.name);
                    } else {
                        this.expanded.add(table.name);
                    }
                    this._render();
                },
                ondblclick: () => this.handlers.onAskAbout?.(`Show me a sample of rows from ${table.name}`),
            },
            icon('chevronRight', 12, 'tree__chevron'),
            icon('table2', 14, 'tree__icon'),
            el('span', { class: 'tree__label', text: table.name }),
            el('span', { class: 'tree__count', text: String(table.columns.length) }),
        );

        const group = el('li', { class: 'tree__group', role: 'none' }, node, columns);
        return group;
    }
}
