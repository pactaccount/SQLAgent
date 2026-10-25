/**
 * Chart rendering.
 *
 * Chart.js draws the marks; this module decides what to draw. The rules
 * follow the shape of the data:
 *
 *   - a time column plus a measure  -> line   (trend over time)
 *   - a category column plus a measure -> bar  (compare magnitude)
 *   - two numeric columns           -> scatter
 *   - anything else                  -> no chart (the table is the answer)
 *
 * Colour rules that are not negotiable:
 *   - Nominal categories all take the SAME colour (slot 1). Bar length already
 *     encodes the value; colouring by value would spend the identity channel
 *     on information the chart already shows.
 *   - There is never a second y-axis. Two measures of different scale become
 *     two charts, or one chart with the values indexed to a common base.
 *   - Gridlines are solid hairlines, one shade off the surface.
 *   - A tooltip enhances; it never gates. Every value is also in the table
 *     underneath, and the legend is always present for two or more series.
 */

import { el, icon } from './ui.js';

const SERIES_SLOTS = [
    'var(--series-1)',
    'var(--series-2)',
    'var(--series-3)',
    'var(--series-4)',
    'var(--series-5)',
    'var(--series-6)',
    'var(--series-7)',
    'var(--series-8)',
];

const TIME_HINTS = (
    'date time year month day week quarter period created updated released ' +
    'purchased invoiced hired born'
).split(' ');

const CATEGORY_HINTS = (
    'name title category genre type status country state city region ' +
    'department artist album customer product label group kind'
).split(' ');

function isNumeric(value) {
    return typeof value === 'number' && Number.isFinite(value);
}

function isNumericColumn(rows, column) {
    const values = rows.map((r) => r[column]).filter((v) => v !== null && v !== undefined);
    if (!values.length) return false;
    return values.every(isNumeric);
}

function looksTemporal(column) {
    const lower = column.toLowerCase();
    return TIME_HINTS.some((hint) => lower.includes(hint));
}

function looksCategorical(column) {
    const lower = column.toLowerCase();
    return CATEGORY_HINTS.some((hint) => lower.includes(hint));
}

/** Read the current theme's surface colour so the chart matches the panel. */
function surfaceColour() {
    return getComputedStyle(document.documentElement)
        .getPropertyValue('--chart-surface')
        .trim() || '#171c24';
}

function textColour() {
    return getComputedStyle(document.documentElement)
        .getPropertyValue('--chart-label')
        .trim() || '#a3adba';
}

function gridColour() {
    return getComputedStyle(document.documentElement)
        .getPropertyValue('--chart-grid')
        .trim() || '#2c2c2a';
}

/**
 * Work out which columns hold the label and the measure.
 * @returns {{label: string, measure: string}|null}
 */
export function planChart(columns, rows) {
    if (!columns?.length || !rows?.length) return null;

    const numeric = columns.filter((c) => isNumericColumn(rows, c));
    if (!numeric.length) return null;

    // The measure is the numeric column that varies the most - a column of
    // identical values carries no information to plot.
    const spread = (column) => {
        const values = rows.map((r) => r[column]).filter(isNumeric);
        if (values.length < 2) return 0;
        return Math.max(...values) - Math.min(...values);
    };

    // A date-like column may hold numbers (a year, a month index) as well as
    // dates, so the name is the only reliable signal. It is never the measure.
    const timeColumn = columns.find((c) => looksTemporal(c));

    if (timeColumn && columns.length > 1) {
        const measureCandidates = numeric.filter((c) => c !== timeColumn);
        if (measureCandidates.length) {
            const measure = measureCandidates.reduce(
                (best, c) => (spread(c) > spread(best) ? c : best),
                measureCandidates[0],
            );
            return { label: timeColumn, measure, temporal: true };
        }
    }

    const measure = numeric.reduce((best, c) => (spread(c) > spread(best) ? c : best), numeric[0]);
    const candidates = columns.filter((c) => c !== measure);

    // Otherwise a category column.
    const categoryColumn =
        candidates.find((c) => looksCategorical(c) && !isNumericColumn(rows, c)) ||
        candidates.find((c) => !isNumericColumn(rows, c));

    if (categoryColumn) return { label: categoryColumn, measure, temporal: false };

    // A single numeric column with no label: plot the values alone.
    if (columns.length === 1) return { label: null, measure, temporal: false };

    return null;
}

/**
 * Build a chart panel.
 *
 * @param {object} options
 * @param {string[]} options.columns
 * @param {object[]} options.rows
 * @param {string} options.preferredType  'bar' | 'line' | 'scatter' | 'none'
 * @returns {HTMLElement|null}
 */
export function buildChart({ columns, rows, preferredType = 'none' }) {
    const plan = planChart(columns, rows);
    if (!plan) return null;

    const types = plan.temporal
        ? ['line', 'bar']
        : ['bar', 'line'];
    const activeType = types.includes(preferredType) ? preferredType : types[0];

    const canvas = el('canvas', { 'aria-label': 'Chart of the query results' });

    const title = el('span', {
        class: 'chart__title',
        text: `${plan.measure} by ${plan.label ?? 'row'}`,
    });

    const picker = el(
        'div',
        { class: 'chart__type-picker', role: 'group', 'aria-label': 'Chart type' },
        ...types.map((type) =>
            el('button', {
                class: `chart__type-btn${type === activeType ? ' is-active' : ''}`,
                type: 'button',
                'aria-pressed': String(type === activeType),
                onclick: () => {
                    picker.querySelectorAll('.chart__type-btn').forEach((button) => {
                        const on = button.textContent === type;
                        button.classList.toggle('is-active', on);
                        button.setAttribute('aria-pressed', String(on));
                    });
                    render(canvas, columns, rows, type);
                },
            }, type === 'bar' ? 'Bars' : 'Line'),
        ),
    );

    const wrap = el('div', { class: 'chart__canvas-wrap' }, canvas);

    const panel = el(
        'div',
        { class: 'chart' },
        el('div', { class: 'chart__head' }, title, el('div', { class: 'grid__spacer' }), picker),
        wrap,
    );

    // Chart.js is optional: if the CDN is blocked the table still works.
    if (typeof window.Chart === 'undefined') {
        wrap.replaceChildren(
            el('div', {
                class: 'panel__empty-text',
                text: 'Charts are unavailable, but the table below has the same data.',
            }),
        );
        return panel;
    }

    render(canvas, columns, rows, activeType);
    return panel;
}

function render(canvas, columns, rows, type) {
    const plan = planChart(columns, rows);
    if (!plan) return;

    const surface = surfaceColour();
    const text = textColour();
    const grid = gridColour();

    // The single accent hue. Every bar in a nominal chart takes this colour:
    // the bar's length already carries the magnitude.
    const hue = SERIES_SLOTS[0];

    const values = rows.map((row) => row[plan.measure]);
    const labels = rows.map((row, index) => {
        if (plan.label === null) return String(index + 1);
        const value = row[plan.label];
        return value === null || value === undefined ? '(blank)' : String(value);
    });

    const config = {
        type: type === 'line' ? 'line' : 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: plan.measure,
                    data: values,
                    backgroundColor: type === 'line' ? 'transparent' : hue,
                    borderColor: hue,
                    borderWidth: type === 'line' ? 2 : 0,
                    borderRadius: type === 'line' ? 0 : 4,
                    pointRadius: type === 'line' ? 0 : 0,
                    pointHoverRadius: 5,
                    pointHoverBorderWidth: 2,
                    pointHoverBorderColor: surface,
                    pointBackgroundColor: hue,
                    fill: false,
                    tension: 0.25,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 240 },
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                // One series, so no legend box - the title names it.
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'var(--surface-raised)',
                    titleColor: 'var(--text-primary)',
                    bodyColor: 'var(--text-secondary)',
                    borderColor: 'var(--border-strong)',
                    borderWidth: 1,
                    padding: 10,
                    displayColors: false,
                    callbacks: {
                        label: (context) => {
                            const value = context.parsed.y;
                            return typeof value === 'number'
                                ? `${plan.measure}: ${value.toLocaleString()}`
                                : String(value);
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: {
                        display: false,
                        drawBorder: true,
                        color: grid,
                    },
                    ticks: {
                        color: text,
                        maxRotation: 45,
                        autoSkip: true,
                        maxTicksLimit: 24,
                    },
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: grid,
                        drawBorder: false,
                        // Solid hairlines. A dashed grid reads as a threshold.
                        borderDash: [],
                    },
                    ticks: {
                        color: text,
                        maxTicksLimit: 6,
                        callback: (value) => {
                            if (typeof value !== 'number') return value;
                            if (Math.abs(value) >= 1_000_000) {
                                return `${(value / 1_000_000).toFixed(1)}M`;
                            }
                            if (Math.abs(value) >= 1_000) {
                                return `${(value / 1_000).toFixed(1)}K`;
                            }
                            return value.toLocaleString();
                        },
                    },
                },
            },
        },
    };

    if (canvas._chart) {
        canvas._chart.destroy();
    }
    canvas._chart = new window.Chart(canvas.getContext('2d'), config);
}
