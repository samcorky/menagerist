import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const router = vi.hoisted(() => ({
	page: { state: {} as { layers?: string[] } },
	navigating: { to: null as unknown },
	pushes: 0
}));

vi.mock('$app/state', () => ({ page: router.page, navigating: router.navigating }));
vi.mock('$app/navigation', () => ({
	pushState: (_url: string, state: { layers?: string[] }) => {
		router.pushes += 1;
		router.page.state = state;
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
});
