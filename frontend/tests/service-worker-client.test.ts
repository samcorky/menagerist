import { describe, expect, it, vi } from 'vitest';
import {
	RESET_PARAM,
	applyUpdate,
	registerServiceWorker,
	resetIfAsked,
	resetServiceWorker
} from '$lib/service-worker-client';
import { CACHE_PREFIX } from '$lib/service-worker/policy';

type Listener = () => void;

function fakeWorker(state = 'installing') {
	const listeners: Record<string, Listener[]> = {};
	return {
		state,
		postMessage: vi.fn(),
		addEventListener: (type: string, fn: Listener) => (listeners[type] ??= []).push(fn),
		fire: (type: string) => listeners[type]?.forEach((fn) => fn())
	};
}

function fakeRegistration(parts: { waiting?: unknown; installing?: unknown } = {}) {
	const listeners: Record<string, Listener[]> = {};
	return {
		waiting: parts.waiting ?? null,
		installing: parts.installing ?? null,
		addEventListener: (type: string, fn: Listener) => (listeners[type] ??= []).push(fn),
		fire: (type: string) => listeners[type]?.forEach((fn) => fn())
	};
}

function fakeContainer(registration: unknown, controller: unknown = {}) {
	const listeners: Record<string, Listener[]> = {};
	return {
		controller,
		register: vi.fn().mockResolvedValue(registration),
		getRegistrations: vi.fn().mockResolvedValue([]),
		addEventListener: (type: string, fn: Listener) => (listeners[type] ??= []).push(fn),
		fire: (type: string) => listeners[type]?.forEach((fn) => fn())
	};
}

const asContainer = (c: unknown) => c as Parameters<typeof registerServiceWorker>[1];

describe('registerServiceWorker', () => {
	it('registers the worker at the root scope', async () => {
		const container = fakeContainer(fakeRegistration());
		await registerServiceWorker(vi.fn(), asContainer(container));
		expect(container.register).toHaveBeenCalledWith('/service-worker.js', { scope: '/' });
	});

	it('offers an update already waiting when the page opens', async () => {
		const waiting = fakeWorker('installed');
		const offer = vi.fn();
		await registerServiceWorker(offer, asContainer(fakeContainer(fakeRegistration({ waiting }))));
		expect(offer).toHaveBeenCalledOnce();
	});

	it('offers an update once a new worker has installed', async () => {
		const installing = fakeWorker();
		const registration = fakeRegistration({ installing });
		const offer = vi.fn();
		await registerServiceWorker(offer, asContainer(fakeContainer(registration)));

		registration.fire('updatefound');
		installing.state = 'installing';
		installing.fire('statechange');
		expect(offer).not.toHaveBeenCalled();
		installing.state = 'installed';
		installing.fire('statechange');
		expect(offer).toHaveBeenCalledOnce();
	});

	it('does not offer the very first install, which replaces nothing', async () => {
		const installing = fakeWorker();
		const registration = fakeRegistration({ installing });
		const offer = vi.fn();
		await registerServiceWorker(offer, asContainer(fakeContainer(registration, null)));

		registration.fire('updatefound');
		installing.state = 'installed';
		installing.fire('statechange');
		expect(offer).not.toHaveBeenCalled();
	});

	it('does not take over until the offer is accepted, then reloads once it has', async () => {
		const waiting = fakeWorker('installed');
		const container = fakeContainer(fakeRegistration({ waiting }));
		const reload = vi.fn();
		let apply: () => void = () => {};
		await registerServiceWorker((fn) => (apply = fn), asContainer(container), reload);

		expect(waiting.postMessage).not.toHaveBeenCalled();
		apply();
		expect(waiting.postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' });
		expect(reload).not.toHaveBeenCalled();
		container.fire('controllerchange');
		expect(reload).toHaveBeenCalledOnce();
	});

	it('carries on without a worker when registration fails', async () => {
		const container = fakeContainer(null);
		container.register.mockRejectedValue(new Error('blocked'));
		await expect(registerServiceWorker(vi.fn(), asContainer(container))).resolves.toBeUndefined();
	});
});

describe('applyUpdate', () => {
	it('listens for the switch before asking for it', () => {
		const order: string[] = [];
		applyUpdate(
			{ postMessage: () => order.push('message') },
			{ addEventListener: () => order.push('listen') },
			() => {}
		);
		expect(order).toEqual(['listen', 'message']);
	});
});

describe('recovery', () => {
	it('unregisters every worker and deletes only its own caches', async () => {
		const unregister = vi.fn().mockResolvedValue(true);
		const remove = vi.fn().mockResolvedValue(true);
		await resetServiceWorker(
			{ getRegistrations: async () => [{ unregister }, { unregister }] as never },
			{ keys: async () => [CACHE_PREFIX + '1', 'other-app'], delete: remove }
		);
		expect(unregister).toHaveBeenCalledTimes(2);
		expect(remove).toHaveBeenCalledExactlyOnceWith(CACHE_PREFIX + '1');
	});

	it('ignores a page that did not ask for a reset', async () => {
		const go = vi.fn();
		expect(await resetIfAsked(new URL('https://x.example/items?q=a'), go)).toBe(false);
		expect(go).not.toHaveBeenCalled();
	});

	it('never turns a doubled leading slash into another site', async () => {
		vi.stubGlobal('navigator', { serviceWorker: { getRegistrations: async () => [] } });
		vi.stubGlobal('caches', { keys: async () => [], delete: async () => true });
		const go = vi.fn();
		await resetIfAsked(new URL(`https://x.example//evil.example/path?${RESET_PARAM}=1`), go);
		expect(go).toHaveBeenCalledWith('/evil.example/path');
		vi.unstubAllGlobals();
	});

	it('resets, then returns to the same page without the flag', async () => {
		vi.stubGlobal('navigator', { serviceWorker: { getRegistrations: async () => [] } });
		vi.stubGlobal('caches', { keys: async () => [], delete: async () => true });
		const go = vi.fn();
		const url = new URL(`https://x.example/items?q=a&${RESET_PARAM}=1#top`);
		expect(await resetIfAsked(url, go)).toBe(true);
		expect(go).toHaveBeenCalledWith('/items?q=a#top');
		vi.unstubAllGlobals();
	});
});
