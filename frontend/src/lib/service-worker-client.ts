// Registers the service worker and turns "a new version is waiting" into a prompt.
//
// An update is never applied by itself: the waiting worker takes over only when the person
// accepts, because the page reloads and anything unsaved in a form is lost. The same goes for
// a long-open tab, which only learns of an update when it is shown again.
import { CACHE_PREFIX } from '$lib/service-worker/policy';

const SCRIPT = '/service-worker.js';
/** Visit any page with this in the query to drop the worker and its caches. */
export const RESET_PARAM = 'reset-app-cache';

export type OfferUpdate = (apply: () => void) => void;

type Container = Pick<
	ServiceWorkerContainer,
	'register' | 'controller' | 'addEventListener' | 'getRegistrations'
>;

/** Whether the worker may be registered: a production build in a browser that supports it. */
export const workerSupported = () =>
	import.meta.env.PROD && typeof navigator !== 'undefined' && 'serviceWorker' in navigator;

/** Asks a waiting worker to take over, and reloads once it has. */
export function applyUpdate(
	waiting: Pick<ServiceWorker, 'postMessage'>,
	container: Pick<ServiceWorkerContainer, 'addEventListener'>,
	reload: () => void
): void {
	container.addEventListener('controllerchange', reload, { once: true });
	waiting.postMessage({ type: 'SKIP_WAITING' });
}

export async function registerServiceWorker(
	offer: OfferUpdate,
	container: Container = navigator.serviceWorker,
	reload: () => void = () => location.reload()
): Promise<ServiceWorkerRegistration | undefined> {
	let registration: ServiceWorkerRegistration;
	try {
		registration = await container.register(SCRIPT, { scope: '/' });
	} catch {
		// The app works without a worker, so a failed registration is not worth interrupting for.
		return undefined;
	}

	// A first install has no controller yet and nothing to replace, so only an update is offered.
	const ready = (worker: ServiceWorker) => {
		if (container.controller) offer(() => applyUpdate(worker, container, reload));
	};
	if (registration.waiting) ready(registration.waiting);
	registration.addEventListener('updatefound', () => {
		const installing = registration.installing;
		installing?.addEventListener('statechange', () => {
			if (installing.state === 'installed') ready(installing);
		});
	});
	return registration;
}

/** Looks for a new version whenever the tab comes back, which a long-open app would miss. */
export function checkWhenShown(registration: Pick<ServiceWorkerRegistration, 'update'>) {
	const check = () => {
		if (document.visibilityState === 'visible') registration.update().catch(() => {});
	};
	document.addEventListener('visibilitychange', check);
	return () => document.removeEventListener('visibilitychange', check);
}

/** The way out of a bad worker: unregister every one and delete the caches this app made. */
export async function resetServiceWorker(
	container: Pick<ServiceWorkerContainer, 'getRegistrations'> = navigator.serviceWorker,
	cacheStorage: Pick<CacheStorage, 'keys' | 'delete'> = caches
): Promise<void> {
	for (const registration of await container.getRegistrations()) await registration.unregister();
	for (const name of await cacheStorage.keys()) {
		if (name.startsWith(CACHE_PREFIX)) await cacheStorage.delete(name);
	}
}

/** Handles `?reset-app-cache`: resets, then reloads the same page without it. */
export async function resetIfAsked(url: URL, go: (to: string) => void): Promise<boolean> {
	if (!url.searchParams.has(RESET_PARAM)) return false;
	await resetServiceWorker();
	url.searchParams.delete(RESET_PARAM);
	go(url.pathname + url.search + url.hash);
	return true;
}
