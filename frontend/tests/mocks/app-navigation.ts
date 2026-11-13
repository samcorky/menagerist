// Stand-in for SvelteKit's `$app/navigation`: there is no router in the component tests.
export const goto = async () => {};
export const pushState = () => {};
export const replaceState = () => {};
export const beforeNavigate = () => {};
export const afterNavigate = () => {};
export const onNavigate = () => {};
export const invalidate = async () => {};
export const invalidateAll = async () => {};
