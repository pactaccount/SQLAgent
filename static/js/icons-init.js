/**
 * Fills the icon-only buttons in the HTML shell.
 *
 * The markup declares the buttons with an accessible name; this module puts
 * the matching SVG inside them. Doing it here keeps the HTML readable and
 * means the icon set lives in one place.
 */

import { icon } from './ui.js';

const BUTTON_ICONS = [
    ['theme-btn', 'sun'],
    ['rail-explorer', 'explorer'],
    ['rail-chat', 'chat'],
    ['explorer-refresh', 'refresh'],
    ['export-conversation', 'download'],
    ['wizard-close', 'x'],
];

export function initIcons() {
    for (const [id, name] of BUTTON_ICONS) {
        const button = document.getElementById(id);
        if (!button) continue;
        button.replaceChildren(icon(name, 16));
    }

    // The theme button shows the theme you would switch TO.
    const themeButton = document.getElementById('theme-btn');
    const syncThemeIcon = () => {
        const current = document.documentElement.getAttribute('data-theme') || 'dark';
        themeButton?.replaceChildren(icon(current === 'dark' ? 'sun' : 'moon', 16));
    };
    syncThemeIcon();
    document.addEventListener('themechange', syncThemeIcon);
}
