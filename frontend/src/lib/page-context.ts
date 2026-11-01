/** Context key a parent sets so non-fluid pages sit against its sidebar instead of centring. */
export const PAGE_ALIGN = 'page-align';
export type PageAlign = 'center' | 'start';
/** A getter object rather than a value, so the layout can change it while pages are mounted. */
export type PageAlignSource = { readonly current: PageAlign };
