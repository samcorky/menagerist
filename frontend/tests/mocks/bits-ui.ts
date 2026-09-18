// Stub for bits-ui in tests (aliased in vitest.config.ts). The real package
// pulls in a large internal module graph (floating-ui, melt, etc.) that
// Vitest's Node/SSR pipeline transforms module-by-module - see
// tests/mocks/lucide-svelte.ts for why that's slow here. Tests never mount
// components, only exercise pure logic from component module scripts, so a
// self-referencing proxy stands in for every namespace (e.g. Dialog.Root,
// Dialog.Trigger, ...) without needing to know its real shape.
// Add a name here if a newly-used export makes an import fail.
const proxy: unknown = new Proxy(() => proxy, {
	get: () => proxy
});

export const Dialog = proxy;
export const Label = proxy;
export const Separator = proxy;
export const Toggle = proxy;
