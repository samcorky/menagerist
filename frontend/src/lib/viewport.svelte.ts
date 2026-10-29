import { MediaQuery } from 'svelte/reactivity';

/**
 * True from Tailwind's `md` breakpoint up. Pages use it to render one layout (a table on desktop,
 * cards on mobile) instead of both, so each row's controls exist in the DOM only once.
 */
export const wide = new MediaQuery('min-width: 768px');
