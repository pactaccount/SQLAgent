/**
 * The connection wizard.
 *
 * Three steps, in plain language, with the jargon moved out of the way:
 *   1. Pick the kind of database
 *   2. Give the details (or upload a file)
 *   3. Confirm and connect
 *
 * The point of the wizard is that a user who has never seen a connection
 * string can still get to a working database.
 */

import { el, icon } from './ui.js';
import { api, ApiError } from './api.js';
import { toast } from './toast.js';

const DB_TYPES = [
    {
        id: 'sqlite',
        name: 'A database file on my computer',
        desc: 'Upload a CSV or SQLite file',
        icon: 'file',
    },
    {
        id: 'postgresql',
        name: 'PostgreSQL',
        desc: 'A hosted Postgres database',
        icon: 'database',
    },
    {
        id: 'mysql',
        name: 'MySQL',
        desc: 'A hosted MySQL database',
        icon: 'database',
    },
    {
        id: 'snowflake',
        name: 'Snowflake',
        desc: 'A Snowflake data warehouse',
        icon: 'chart',
    },
];

export class ConnectionWizard {
    /**
     * @param {HTMLElement} modal  the modal element
     * @param {{onConnected: (info: object) => void}} handlers
     */
    constructor(modal, handlers = {}) {
        this.modal = modal;
        this.handlers = handlers;
        this.step = 0;
        this.type = 'sqlite';
        this.uploadedUri = '';
        this.uploadedName = '';
        this.busy = false;

        this.body = this.modal.querySelector('.modal__body');
        this.foot = this.modal.querySelector('.modal__foot');
        this.titleNode = this.modal.querySelector('.modal__title');
        this.subtitleNode = this.modal.querySelector('.modal__subtitle');

        this.modal.addEventListener('mousedown', (event) => {
            if (event.target === this.modal) this.close();
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && this.modal.classList.contains('is-open')) {
                this.close();
            }
        });

        this.render();
    }

    open(prefill = {}) {
        if (prefill.type) this.type = prefill.type;
        if (prefill.tenantId) this.tenantId = prefill.tenantId;
        this.step = 0;
        this.modal.classList.add('is-open');
        this.render();
        // Move focus into the dialog so keyboard users are not left behind it.
        requestAnimationFrame(() => {
            this.body.querySelector('input, select, button')?.focus();
        });
    }

    close() {
        this.modal.classList.remove('is-open');
    }

    get isOpen() {
        return this.modal.classList.contains('is-open');
    }

    // --- Rendering ------------------------------------------------------------

    render() {
        this._renderStepIndicator();
        this._renderBody();
        this._renderFooter();
    }

    _renderStepIndicator() {
        const labels = ['Database', 'Details', 'Connect'];
        const indicator = el(
            'div',
            { class: 'steps' },
            ...labels.flatMap((label, index) => {
                const step = el(
                    'div',
                    {
                        class: `step${index === this.step ? ' is-active' : ''}${index < this.step ? ' is-done' : ''}`,
                    },
                    el('span', { class: 'step__num', text: index < this.step ? '✓' : String(index + 1) }),
                    el('span', { text: label }),
                );
                return index < labels.length - 1 ? [step, el('span', { class: 'step__line' })] : [step];
            }),
        );
        this.indicator = indicator;
    }

    _renderBody() {
        if (this.step === 0) this._renderTypeStep();
        else if (this.step === 1) this._renderDetailsStep();
        else this._renderConfirmStep();
    }

    _renderTypeStep() {
        this.titleNode.textContent = 'Connect a database';
        this.subtitleNode.textContent =
            'Start with the kind of database you want to explore. You can change this later.';

        const grid = el(
            'div',
            { class: 'db-types' },
            ...DB_TYPES.map((type) =>
                el(
                    'button',
                    {
                        class: `db-type${this.type === type.id ? ' is-active' : ''}`,
                        type: 'button',
                        onclick: () => {
                            this.type = type.id;
                            this._renderBody();
                        },
                    },
                    icon(type.icon, 18),
                    el(
                        'span',
                        {},
                        el('span', { class: 'db-type__name', text: type.name }),
                        el('span', { class: 'db-type__desc', text: type.desc }),
                    ),
                ),
            ),
        );

        this.body.replaceChildren(this.indicator, grid);
    }

    _renderDetailsStep() {
        this.titleNode.textContent = 'Add the details';
        this.subtitleNode.textContent =
            this.type === 'sqlite'
                ? 'Upload your database file, or give the path to one already on this machine.'
                : 'Enter the connection details for your database.';

        const content = [this.indicator];

        // The tenant is a namespace for the schema index. Almost every user
        // should leave it alone, so it is optional and explained.
        content.push(
            el(
                'div',
                { class: 'field', style: 'margin-bottom: 16px' },
                el('label', { class: 'field__label', for: 'wizard-tenant' }, 'Workspace name (optional)'),
                el('input', {
                    class: 'input',
                    id: 'wizard-tenant',
                    type: 'text',
                    placeholder: 'default_tenant',
                    value: this.tenantId || '',
                }),
                el('span', {
                    class: 'field__hint',
                    text: 'Keeps your database separate from anyone else using this instance. Leave it blank unless you were given a name.',
                }),
            ),
        );

        if (this.type === 'sqlite') {
            content.push(this._sqliteFields());
        } else if (this.type === 'snowflake') {
            content.push(this._snowflakeFields());
        } else {
            content.push(this._standardFields());
        }

        this.body.replaceChildren(...content);
    }

    _sqliteFields() {
        const fileInput = el('input', {
            type: 'file',
            id: 'wizard-file',
            // Do not let native OS type filtering disable valid CSV files.
            // The upload endpoint validates supported extensions and file contents.
            class: 'visually-hidden',
            onchange: (event) => this._handleUpload(event.target.files[0]),
        });

        const dropzone = el(
            'div',
            {
                class: 'dropzone',
                role: 'button',
                tabindex: '0',
                onclick: () => fileInput.click(),
                onkeydown: (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        fileInput.click();
                    }
                },
                ondragover: (event) => {
                    event.preventDefault();
                    dropzone.classList.add('is-over');
                },
                ondragleave: () => dropzone.classList.remove('is-over'),
                ondrop: (event) => {
                    event.preventDefault();
                    dropzone.classList.remove('is-over');
                    const file = event.dataTransfer.files[0];
                    if (file) this._handleUpload(file);
                },
            },
            icon('upload', 22),
            el('div', { class: 'dropzone__title', text: 'Choose a CSV or database file' }),
            el('div', {
                class: 'dropzone__hint',
                text: 'Drag one here, or click to browse. Accepts .csv, .db, .sqlite and .sqlite3 files.',
            }),
            fileInput,
        );

        this.uploadStatus = el('div', { style: 'margin-top: 12px' });

        const pathInput = el('input', {
            class: 'input',
            id: 'wizard-path',
            type: 'text',
            placeholder: '/path/to/your/database.db',
            value: this.uploadedUri || '',
            oninput: (event) => {
                this.uploadedUri = event.target.value;
                this._updateFooter();
            },
        });

        const sampleBtn = el(
            'button',
            {
                type: 'button',
                class: 'btn btn--secondary',
                id: 'btn-load-sample-db',
                style: 'display: inline-flex; align-items: center; gap: 8px; width: 100%; justify-content: center; margin-top: 10px; padding: 10px; font-weight: 500;',
                onclick: () => {
                    pathInput.value = 'chinook.db';
                    this.uploadedUri = 'chinook.db';
                    this.uploadStatus.replaceChildren(
                        el(
                            'div',
                            { style: 'padding: 8px 12px; border-radius: 6px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: #10b981; font-size: 13px; display: flex; align-items: center; gap: 6px;' },
                            icon('check', 16),
                            el('span', { text: 'Loaded bundled sample: Chinook Music Store (11 tables, ready to explore)' })
                        )
                    );
                    this._updateFooter();
                },
            },
            icon('sparkle', 16),
            el('span', { text: 'Load bundled sample database (Chinook Music Store)' })
        );

        return el(
            'div',
            {},
            dropzone,
            sampleBtn,
            this.uploadStatus,
            el(
                'div',
                { class: 'field', style: 'margin-top: 16px' },
                el('label', { class: 'field__label', for: 'wizard-path' }, 'Or enter a file path'),
                pathInput,
                el('span', {
                    class: 'field__hint',
                    text: 'Use the full path on the machine running the server, or "chinook.db".',
                }),
            ),
        );
    }

    _standardFields() {
        const isPostgres = this.type === 'postgresql';
        const defaultPort = isPostgres ? '5432' : '3306';

        this.inputs = {
            host: this._input('wizard-host', 'Host', 'db.example.com'),
            port: this._input('wizard-port', 'Port', defaultPort),
            user: this._input('wizard-user', 'Username', 'admin'),
            pass: this._input('wizard-pass', 'Password', '', 'password'),
            dbname: this._input('wizard-dbname', 'Database name', 'my_database'),
        };

        return el(
            'div',
            { style: 'display:flex; flex-direction:column; gap:14px' },
            el(
                'div',
                { style: 'display:flex; gap:12px' },
                el('div', { class: 'field', style: 'flex:2' }, this.inputs.host.field, this.inputs.host.input),
                el('div', { class: 'field', style: 'flex:1' }, this.inputs.port.field, this.inputs.port.input),
            ),
            el(
                'div',
                { style: 'display:flex; gap:12px' },
                el('div', { class: 'field', style: 'flex:1' }, this.inputs.user.field, this.inputs.user.input),
                el('div', { class: 'field', style: 'flex:1' }, this.inputs.pass.field, this.inputs.pass.input),
            ),
            el('div', { class: 'field' }, this.inputs.dbname.field, this.inputs.dbname.input),
            el(
                'div',
                { class: 'callout callout--info' },
                icon('lock', 15),
                el('span', {
                    text: 'Your password is used to open the connection and is sent to the server that runs this app. It is never shown again.',
                }),
            ),
        );
    }

    _snowflakeFields() {
        this.inputs = {
            account: this._input('wizard-account', 'Account', 'myorg-myaccount'),
            user: this._input('wizard-user', 'Username', 'admin'),
            pass: this._input('wizard-pass', 'Password', '', 'password'),
            dbname: this._input('wizard-db', 'Database', 'REVENUE_DB'),
            schema: this._input('wizard-schema', 'Schema', 'PUBLIC'),
            warehouse: this._input('wizard-wh', 'Warehouse', 'COMPUTE_WH'),
        };

        return el(
            'div',
            { style: 'display:flex; flex-direction:column; gap:14px' },
            el('div', { class: 'field' }, this.inputs.account.field, this.inputs.account.input),
            el(
                'div',
                { style: 'display:flex; gap:12px' },
                el('div', { class: 'field', style: 'flex:1' }, this.inputs.user.field, this.inputs.user.input),
                el('div', { class: 'field', style: 'flex:1' }, this.inputs.pass.field, this.inputs.pass.input),
            ),
            el(
                'div',
                { style: 'display:flex; gap:12px' },
                el('div', { class: 'field', style: 'flex:1' }, this.inputs.dbname.field, this.inputs.dbname.input),
                el('div', { class: 'field', style: 'flex:1' }, this.inputs.schema.field, this.inputs.schema.input),
            ),
            el('div', { class: 'field' }, this.inputs.warehouse.field, this.inputs.warehouse.input),
        );
    }

    _input(id, label, placeholder, type = 'text') {
        const input = el('input', {
            class: 'input',
            id,
            type,
            placeholder,
            autocomplete: 'off',
        });

        input.addEventListener('input', () => this._updateFooter());

        return {
            input,
            field: el('label', { class: 'field__label', for: id, text: label }),
        };
    }

    _renderConfirmStep() {
        this.titleNode.textContent = 'Ready to connect';
        this.subtitleNode.textContent =
            'We will read the table structure so the agent knows what is in your database. Your data itself is never changed.';

        const summary = el(
            'div',
            { class: 'approval__impact' },
            el(
                'dl',
                {},
                el('dt', { text: 'Database type' }),
                el('dd', { text: DB_TYPES.find((t) => t.id === this.type)?.name || this.type }),
                el('dt', { text: 'Workspace' }),
                el('dd', { text: this.tenantId || 'default_tenant' }),
            ),
        );

        this.body.replaceChildren(
            this.indicator,
            summary,
            el(
                'div',
                { class: 'callout', style: 'margin-top: 12px' },
                icon('shield', 15),
                el('span', {
                    text: 'The agent can only read your data unless you explicitly approve a change. Every change is shown to you first.',
                }),
            ),
        );
    }

    _renderFooter() {
        const buttons = [];

        if (this.step > 0) {
            buttons.push(
                el(
                    'button',
                    {
                        class: 'btn',
                        type: 'button',
                        onclick: () => {
                            this.step -= 1;
                            this.render();
                        },
                    },
                    'Back',
                ),
            );
        }

        buttons.push(el('div', { class: 'modal__foot-spacer' }));

        if (this.step < 2) {
            buttons.push(
                el(
                    'button',
                    {
                        class: 'btn btn--primary',
                        type: 'button',
                        onclick: () => this._next(),
                    },
                    this.step === 0 ? 'Continue' : 'Review',
                    icon('chevronRight', 14),
                ),
            );
        } else {
            buttons.push(
                el(
                    'button',
                    {
                        class: 'btn btn--primary',
                        type: 'button',
                        id: 'wizard-connect',
                        onclick: () => this._connect(),
                    },
                    'Connect',
                ),
            );
        }

        this.foot.replaceChildren(...buttons);
        this._updateFooter();
    }

    /** Disable the forward button until the current step has what it needs. */
    _updateFooter() {
        const forward = this.foot.querySelector('.btn--primary');
        if (!forward || this.step !== 1) return;

        if (this.type === 'sqlite') {
            forward.disabled = !this.uploadedUri;
        } else if (this.inputs) {
            const required = ['user', 'pass', 'dbname'];
            if (this.type === 'postgresql' || this.type === 'mysql') required.push('host');
            if (this.type === 'snowflake') required.push('account', 'warehouse');
            forward.disabled = required.some((key) => !this.inputs[key]?.input.value.trim());
        }
    }

    // --- Behaviour -------------------------------------------------------------

    _next() {
        if (this.step === 1) {
            const tenant = this.body.querySelector('#wizard-tenant');
            this.tenantId = tenant?.value.trim() || '';
        }
        this.step = Math.min(2, this.step + 1);
        this.render();
    }

    async _handleUpload(file) {
        if (!file) return;

        this.uploadStatus.replaceChildren(
            el(
                'div',
                { class: 'callout callout--info' },
                icon('clock', 15),
                el('span', { text: `Uploading ${file.name}…` }),
            ),
        );

        try {
            const result = await api.uploadDb(file);
            this.uploadedUri = result.db_uri;
            this.uploadedName = result.filename;

            // Reflect the upload in the path field so the value is visible.
            const pathInput = this.body.querySelector('#wizard-path');
            if (pathInput) pathInput.value = result.db_uri;

            this.uploadStatus.replaceChildren(
                el(
                    'div',
                    { class: 'dropzone__file' },
                    icon('check', 14),
                    el('span', { text: result.table_name ? `${result.filename}: ${result.row_count} rows imported into ${result.table_name}` : `${result.filename} uploaded` }),
                ),
            );
            this._updateFooter();
        } catch (err) {
            this.uploadStatus.replaceChildren(
                el(
                    'div',
                    { class: 'callout callout--error' },
                    icon('alert', 15),
                    el('span', { text: err instanceof ApiError ? err.message : 'Upload failed.' }),
                ),
            );
        }
    }

    /** Build the connection URI from the collected details. */
    _buildUri() {
        const value = (key) => this.inputs?.[key]?.input.value.trim() || '';

        if (this.type === 'sqlite') {
            const path = this.uploadedUri.trim();
            if (!path) return '';
            if (path.startsWith('sqlite:///')) return path;
            // An absolute path needs the extra slash: "sqlite:///" + "/tmp/x.db"
            // is "sqlite:////tmp/x.db". Stripping it would point at a relative
            // path and fail to open the file.
            return `sqlite:///${path}`;
        }

        if (this.type === 'postgresql' || this.type === 'mysql') {
            const port = value('port') || (this.type === 'postgresql' ? '5432' : '3306');
            return `${this.type}://${encodeURIComponent(value('user'))}:${encodeURIComponent(value('pass'))}@${value('host')}:${port}/${value('dbname')}`;
        }

        // Snowflake accounts are often pasted as a full URL, so normalise it.
        const account = value('account')
            .replace(/^https?:\/\//, '')
            .replace(/\.snowflakecomputing\.com.*$/, '')
            .replace(/\/$/, '');

        const schema = value('schema');
        const schemaPart = schema ? `/${schema}` : '';

        return `snowflake://${encodeURIComponent(value('user'))}:${encodeURIComponent(value('pass'))}@${account}/${value('dbname')}${schemaPart}?warehouse=${encodeURIComponent(value('warehouse'))}`;
    }

    async _connect() {
        const uri = this._buildUri();
        if (!uri) {
            toast('Fill in the connection details first.', 'warning');
            return;
        }

        const connectBtn = this.foot.querySelector('#wizard-connect');
        if (connectBtn) {
            connectBtn.disabled = true;
            connectBtn.textContent = 'Connecting…';
        }

        const tenantId = this.tenantId || 'default_tenant';

        try {
            await api.connect(tenantId, uri);
            this.close();
            this.handlers.onConnected?.({
                tenantId,
                dbUri: uri,
                dbType: this.type,
            });
            toast('Database connected. Its table structure is ready.', 'success');
        } catch (err) {
            const message = err instanceof ApiError ? err.message : 'Could not connect.';
            toast(message, 'error', 7000);
            if (connectBtn) {
                connectBtn.disabled = false;
                connectBtn.textContent = 'Connect';
            }
        }
    }
}
