// Node ids are runtime data, unknown at build time - the crawler can't
// discover concrete URLs for this route, so it can't be prerendered like the
// rest of the app. `adapter-static`'s `fallback: 'index.html'` serves it as
// an SPA route at runtime instead.
export const prerender = false;
