/**
 * API client.
 *
 * Every network call in the app goes through here, so error handling, JSON
 * parsing and the "did it time out" case live in one place.
 */

const JSON_HEADERS = { 'Content-Type': 'application/json' };

/** An error carrying the server's human-readable message. */
export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
    }
}

async function request(path, options = {}) {
    let response;
    try {
        response = await fetch(path, options);
    } catch (err) {
        // fetch only rejects on a network failure, never on a 4xx/5xx.
        throw new ApiError(
            'Could not reach the server. Check your connection and try again.',
            0,
        );
    }

    let payload = null;
    const raw = await response.text();
    if (raw) {
        try {
            payload = JSON.parse(raw);
        } catch {
            payload = null;
        }
    }

    if (!response.ok) {
        throw new ApiError(
            payload?.detail || payload?.error || `Request failed (${response.status})`,
            response.status,
        );
    }

    return payload;
}

export const api = {
    /** Connect a database and index its schema. */
    connect(tenantId, dbUri) {
        return request('/connect', {
            method: 'POST',
            headers: JSON_HEADERS,
            body: JSON.stringify({ tenant_id: tenantId, db_uri: dbUri }),
        });
    },

    /** Fetch the table/column structure of a database. */
    schema(tenantId, dbUri) {
        return request('/schema', {
            method: 'POST',
            headers: JSON_HEADERS,
            body: JSON.stringify({ tenant_id: tenantId, db_uri: dbUri }),
        });
    },

    /** Fetch starter questions generated from a database's own schema. */
    starterQuestions(tenantId, dbUri) {
        return request('/starter_questions', {
            method: 'POST',
            headers: JSON_HEADERS,
            body: JSON.stringify({ tenant_id: tenantId, db_uri: dbUri }),
        });
    },

    /** Ask a natural-language question. */
    chat(query, tenantId, dbUri) {
        return request('/chat', {
            method: 'POST',
            headers: JSON_HEADERS,
            body: JSON.stringify({ query, tenant_id: tenantId, db_uri: dbUri }),
        });
    },

    /** Classify a statement and estimate its impact without running it. */
    previewSql(sql, dbUri) {
        return request('/preview_sql', {
            method: 'POST',
            headers: JSON_HEADERS,
            body: JSON.stringify({ sql, db_uri: dbUri }),
        });
    },

    /** Run a read-only statement the user typed. */
    runSql(sql, dbUri, limit = 200) {
        return request('/run_sql', {
            method: 'POST',
            headers: JSON_HEADERS,
            body: JSON.stringify({ sql, db_uri: dbUri, limit }),
        });
    },

    /** Execute a statement the user explicitly approved. */
    executeApproved(approvalId) {
        return request('/execute_approved', {
            method: 'POST',
            headers: JSON_HEADERS,
            body: JSON.stringify({ approval_id: approvalId }),
        });
    },

    rejectApproved(approvalId) {
        return request('/reject_approved', { method: 'POST', headers: JSON_HEADERS,
            body: JSON.stringify({ approval_id: approvalId }) });
    },

    /** Upload a SQLite database or CSV table. */
    async uploadDb(file) {
        const form = new FormData();
        form.append('file', file);

        const response = await fetch('/upload_db', { method: 'POST', body: form });
        const payload = await response.json().catch(() => null);

        if (!response.ok) {
            throw new ApiError(payload?.detail || 'Upload failed.', response.status);
        }
        return payload;
    },
};
