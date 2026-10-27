/**
 * Application state.
 *
 * A tiny observable store. Views subscribe to the slices they care about and
 * re-render when those change. State that belongs to a single chat tab (the
 * SQL text, the last result) lives on the tab, not here.
 */

const STORAGE_KEYS = {
    tenant: 'sqlagent.tenant',
    dbUri: 'sqlagent.dbUri',
    dbType: 'sqlagent.dbType',
    theme: 'sqlagent.theme',
    leftPanel: 'sqlagent.leftPanelOpen',
    rightPanel: 'sqlagent.rightPanelOpen',
};

function readStored(key, fallback) {
    try {
        const value = localStorage.getItem(key);
        return value === null ? fallback : value;
    } catch {
        // Private browsing can make localStorage throw on access.
        return fallback;
    }
}

function writeStored(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch {
        /* Storage is a convenience, never a requirement. */
    }
}

class Store {
    constructor() {
        this.state = {
            connection: {
                tenantId: readStored(STORAGE_KEYS.tenant, ''),
                dbUri: readStored(STORAGE_KEYS.dbUri, ''),
                dbType: readStored(STORAGE_KEYS.dbType, 'sqlite'),
                connected: Boolean(readStored(STORAGE_KEYS.dbUri, '')),
            },
            theme: readStored(STORAGE_KEYS.theme, 'dark'),
            panels: {
                left: (typeof window !== 'undefined' && window.innerWidth <= 860)
                    ? false
                    : readStored(STORAGE_KEYS.leftPanel, '1') !== '0',
                right: readStored(STORAGE_KEYS.rightPanel, '1') !== '0',
            },
            schema: null,
            starters: [],
            sessions: [],
            activeSessionId: null,
            busy: false,
        };

        this.listeners = new Set();
        this.nextSessionNumber = 1;
    }

    subscribe(listener) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }

    emit(changed = {}) {
        for (const listener of this.listeners) {
            listener(this.state, changed);
        }
    }

    set(patch, changed) {
        this.state = { ...this.state, ...patch };
        this.emit(changed || Object.keys(patch));
    }

    // --- Connection ---------------------------------------------------------

    setConnection({ tenantId, dbUri, dbType }) {
        writeStored(STORAGE_KEYS.tenant, tenantId);
        writeStored(STORAGE_KEYS.dbUri, dbUri);
        writeStored(STORAGE_KEYS.dbType, dbType);

        this.set(
            {
                connection: {
                    tenantId,
                    dbUri,
                    dbType,
                    connected: Boolean(dbUri),
                },
            },
            ['connection'],
        );
    }

    // --- Theme ---------------------------------------------------------------

    setTheme(theme) {
        writeStored(STORAGE_KEYS.theme, theme);
        document.documentElement.setAttribute('data-theme', theme);
        // Lets the theme button swap its icon without knowing about the store.
        document.dispatchEvent(new CustomEvent('themechange', { detail: theme }));
        this.set({ theme }, ['theme']);
    }

    toggleTheme() {
        this.setTheme(this.state.theme === 'dark' ? 'light' : 'dark');
    }

    // --- Panels --------------------------------------------------------------

    togglePanel(side) {
        const next = { ...this.state.panels, [side]: !this.state.panels[side] };
        writeStored(STORAGE_KEYS.leftPanel, next.left ? '1' : '0');
        writeStored(STORAGE_KEYS.rightPanel, next.right ? '1' : '0');
        this.set({ panels: next }, ['panels']);
    }

    // --- Sessions (chat tabs) -------------------------------------------------

    createSession() {
        const id = `s${this.nextSessionNumber++}`;
        const session = {
            id,
            title: `Query ${this.nextSessionNumber - 1}`,
            messages: [],
            sql: '',
            columns: [],
            rows: [],
            rowCount: 0,
            truncated: false,
            chartType: 'none',
            insight: '',
            explanation: '',
            analysis: null,
            loading: false,
        };

        this.state.sessions = [...this.state.sessions, session];
        this.state.activeSessionId = id;
        this.emit(['sessions', 'activeSessionId']);
        return session;
    }

    getSession(id = this.state.activeSessionId) {
        return this.state.sessions.find((s) => s.id === id) || null;
    }

    get activeSession() {
        return this.getSession();
    }

    setActiveSession(id) {
        if (this.state.activeSessionId === id) return;
        this.state.activeSessionId = id;
        this.emit(['activeSessionId']);
    }

    updateSession(id, patch) {
        this.state.sessions = this.state.sessions.map((session) =>
            session.id === id ? { ...session, ...patch } : session,
        );
        this.emit(['sessions']);
    }

    /**
     * Append a message to a session's transcript.
     *
     * The transcript lives on the session, not on the chat panel, so
     * switching tabs restores the conversation instead of wiping it.
     *
     * This deliberately does not emit: a new message does not change the
     * tab bar, and re-rendering it on every keystroke of the agent's
     * answer would make the bar flicker and swallow clicks.
     */
    addMessage(sessionId, message) {
        this.state.sessions = this.state.sessions.map((session) =>
            session.id === sessionId
                ? { ...session, messages: [...session.messages, message] }
                : session,
        );
    }

    /** Clear every session's transcript, for when the database changes. */
    clearMessages() {
        this.state.sessions = this.state.sessions.map((session) => ({
            ...session,
            messages: [],
        }));
    }

    removeSession(id) {
        if (this.state.sessions.length <= 1) return false;

        const index = this.state.sessions.findIndex((s) => s.id === id);
        if (index === -1) return false;

        const remaining = this.state.sessions.filter((s) => s.id !== id);
        this.state.sessions = remaining;

        // If the closed tab was active, move to a neighbour rather than
        // jumping to the far end of the list.
        if (this.state.activeSessionId === id) {
            const next = remaining[Math.min(index, remaining.length - 1)];
            this.state.activeSessionId = next.id;
        }

        this.emit(['sessions', 'activeSessionId']);
        return true;
    }

    // --- Schema ---------------------------------------------------------------

    setSchema(schema) {
        this.set({ schema }, ['schema']);
    }

    setStarters(starters) {
        this.set({ starters }, ['starters']);
    }

    setBusy(busy) {
        this.set({ busy }, ['busy']);
    }
}

export const store = new Store();
