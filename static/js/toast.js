/**
 * Toast notifications.
 *
 * Errors and successes that are not tied to a specific message bubble appear
 * here. The container is announced politely so a screen reader hears it
 * without the focus being stolen.
 */

import { el, icon, iconFilled } from './ui.js';

let container = null;

function ensureContainer() {
    if (container && document.body.contains(container)) return container;

    container = el('div', {
        class: 'toasts',
        role: 'status',
        'aria-live': 'polite',
        'aria-atomic': 'false',
    });
    document.body.append(container);
    return container;
}

const ICONS = {
    error: 'alert',
    success: 'check',
    warning: 'alert',
    info: 'info',
};

/**
 * Show a toast.
 * @param {string} message
 * @param {'info'|'success'|'warning'|'error'} kind
 * @param {number} duration  milliseconds before it fades out
 */
export function toast(message, kind = 'info', duration = 4500) {
    const host = ensureContainer();

    const node = el(
        'div',
        { class: `toast toast--${kind}` },
        icon(ICONS[kind] || 'info', 16),
        el('span', { text: message }),
    );

    host.append(node);

    const remove = () => {
        node.style.opacity = '0';
        node.style.transform = 'translateX(12px)';
        setTimeout(() => node.remove(), 180);
    };

    const timer = setTimeout(remove, duration);
    node.addEventListener('click', () => {
        clearTimeout(timer);
        remove();
    });

    return node;
}
