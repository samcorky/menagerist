import { MediaQuery } from 'svelte/reactivity';

/**
 * True from Tailwind's `md` breakpoint up. Pages use it to render one layout (a table on desktop,
 * cards on mobile) instead of both, so each row's controls exist in the DOM only once.
 */
export const wide = new MediaQuery('min-width: 768px');

/** True from Tailwind's `lg` breakpoint up, where the settings and admin pages gain a sidebar. */
export const desktop = new MediaQuery('min-width: 1024px');

/** A mouse on a wide enough screen: global search lives in the top bar instead of a full-screen sheet. */
export const inlineSearch = new MediaQuery('(min-width: 768px) and (pointer: fine)');
