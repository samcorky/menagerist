import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const router = vi.hoisted(() => ({
	page: { state: {} as { layers?: string[] }, url: { href: 'http://localhost/items' } },
	gotos: [] as unknown[][],
	navigating: { to: null as unknown },
	pushes: 0
}));

vi.mock('$app/state', () => ({ page: router.page, navigating: router.navigating }));
vi.mock('$app/navigation', () => ({
	pushState: (_url: string, state: { layers?: string[] }) => {
		router.pushes += 1;
		router.page.state = state;
	},
	goto: (...args: unknown[]) => {
		router.gotos.push(args);
		return Promise.resolve();
	},
	replaceState: (_url: string, state: { layers?: string[] }) => {
		router.page.state = state;
	}
}));

import {
	keepLayersThrough,
	popAllLayers,
	popLayer,
	registerLayer,
	resetLayers,
	restoreLayers,
	syncLayers
} from '../src/lib/back-layers';

describe('back layers', () => {
	let popstate: (() => void) | undefined;
	const back = vi.fn();

	// What Back does: the router drops the top entry's state, then popstate reaches us.
	function goBack() {
		back();
		queueMicrotask(() => {
			router.page.state = { layers: (router.page.state.layers ?? []).slice(0, -1) };
			popstate?.();
			// The layers' effect, which runs when the page state changes.
			syncLayers();
		});
	}

	beforeEach(() => {
		vi.useFakeTimers();
		resetLayers();
		router.page.state = {};
		router.page.url.href = 'http://localhost/items';
		router.gotos.length = 0;
		router.navigating.to = null;
		router.pushes = 0;
		back.mockReset();
		popstate = undefined;
		vi.stubGlobal('history', { back: goBack });
		vi.stubGlobal('window', {
			addEventListener: (_: string, handler: () => void) => (popstate = handler)
		});
	});
	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	const settle = () => vi.runAllTimersAsync();

	it('gives an open layer one history entry', async () => {
		registerLayer(() => {});
		await settle();
		expect(router.page.state.layers).toHaveLength(1);
		expect(router.pushes).toBe(1);
	});

	it('removes the entry when the layer closes some other way', async () => {
		const unregister = registerLayer(() => {});
		await settle();
		unregister();
		await settle();
		expect(router.page.state.layers ?? []).toHaveLength(0);
	});

	it('keeps the new layer when one closes as the next opens', async () => {
		const closed = vi.fn();
		const first = registerLayer(() => {});
		await settle();
		first();
		registerLayer(closed);
		await settle();
		syncLayers();
		expect(closed).not.toHaveBeenCalled();
		expect(router.page.state.layers).toHaveLength(1);
	});

	it('closes the top layer when Back removes its entry, and does not push it again', async () => {
		const lower = vi.fn();
		const upper = vi.fn();
		registerLayer(lower);
		registerLayer(upper);
		await settle();
		expect(router.page.state.layers).toHaveLength(2);

		goBack();
		await settle();

		expect(upper).toHaveBeenCalledTimes(1);
		expect(lower).not.toHaveBeenCalled();
		expect(router.page.state.layers).toHaveLength(1);
		expect(router.pushes).toBe(2);
	});

	it('shares one Back between callers asking at the same time', async () => {
		registerLayer(() => {});
		await settle();
		back.mockClear();
		void popLayer();
		void popLayer();
		await settle();
		expect(back).toHaveBeenCalledTimes(1);
	});

	it('pops every open entry before a navigation goes ahead', async () => {
		registerLayer(() => {});
		registerLayer(() => {});
		await settle();
		const done = popAllLayers();
		await settle();
		await done;
		expect(router.page.state.layers ?? []).toHaveLength(0);
	});

	it('keeps an open layer through a navigation that clears the page state', async () => {
		const closed = vi.fn();
		registerLayer(closed);
		await settle();

		keepLayersThrough();
		router.page.state = {}; // what `goto` does to the page state
		syncLayers();
		restoreLayers();
		await settle();

		expect(closed).not.toHaveBeenCalled();
		expect(router.page.state.layers).toHaveLength(1);
	});

	it('restores the layers on its own if the navigation never finishes', async () => {
		registerLayer(() => {});
		await settle();
		keepLayersThrough();
		router.page.state = {};
		await vi.advanceTimersByTimeAsync(2000);
		expect(router.page.state.layers).toHaveLength(1);
	});

	it('puts back an address rewritten while the layer was open, once it closes', async () => {
		const unregister = registerLayer(() => {});
		await settle();
		// A filter written to the query string lands on the layer's own entry...
		router.page.url.href = 'http://localhost/items?f=x';
		// ...and going back returns to the address the layer opened on.
		vi.stubGlobal('history', {
			back: () => {
				goBack();
				router.page.url.href = 'http://localhost/items';
			}
		});

		unregister();
		await settle();

		expect(router.gotos).toEqual([
			['http://localhost/items?f=x', { replaceState: true, noScroll: true, keepFocus: true }]
		]);
	});

	it('goes back past every entry that carries the layer, then puts the address back', async () => {
		const unregister = registerLayer(() => {});
		await settle();
		// The first filter written adds a second entry that also carries the layer.
		router.page.state = { layers: ['layer-1', 'layer-1'] };
		router.page.url.href = 'http://localhost/items?f=x';
		const backs = vi.fn();
		vi.stubGlobal('history', {
			back: () => {
				backs();
				goBack();
				if (backs.mock.calls.length === 2) router.page.url.href = 'http://localhost/items';
			}
		});

		unregister();
		await settle();

		expect(backs).toHaveBeenCalledTimes(2);
		// The address returns as an entry of its own, as writing the first filter made one.
		expect(router.gotos).toEqual([
			['http://localhost/items?f=x', { replaceState: false, noScroll: true, keepFocus: true }]
		]);
	});

	it('leaves the address alone when it was not rewritten', async () => {
		const unregister = registerLayer(() => {});
		await settle();
		unregister();
		await settle();
		expect(router.gotos).toEqual([]);
	});
});
