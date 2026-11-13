// Stand-in for SvelteKit's `$app/state`: component tests import components without a router.
export const page = { url: new URL('http://localhost/'), state: {} as App.PageState };
export const navigating = { to: null };
