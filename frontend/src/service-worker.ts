/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

// A small worker for resilience, not offline data (see lib/service-worker/policy.ts for what
// it may touch). It keeps the build's immutable files so the app starts quickly, and shows one
// offline page when a page load cannot reach the server.
import { build, version } from '$service-worker';
import { SHELL_FILES, cacheName, routeFor, staleCaches } from '$lib/service-worker/policy';

const sw = self as unknown as ServiceWorkerGlobalScope;
const CURRENT = cacheName(version);
const PRECACHED = new Set([...build, ...SHELL_FILES]);

sw.addEventListener('install', (event) => {
	// No skipWaiting() here: a new worker waits until the person chooses to reload, so an update
	// never replaces the code under a form they are still filling in.
	event.waitUntil(caches.open(CURRENT).then((cache) => cache.addAll([...PRECACHED])));
});

sw.addEventListener('message', (event) => {
	if (event.data?.type === 'SKIP_WAITING') void sw.skipWaiting();
});

sw.addEventListener('activate', (event) => {
	event.waitUntil(
		(async () => {
			for (const name of staleCaches(await caches.keys(), CURRENT)) await caches.delete(name);
			await sw.clients.claim();
		})()
	);
});

sw.addEventListener('fetch', (event) => {
	const { request } = event;
	const route = routeFor(request, sw.location.origin, PRECACHED);
	if (route === 'network') return;

	if (route === 'asset') {
		event.respondWith(caches.match(request.url).then((cached) => cached ?? fetch(request)));
		return;
	}

	// Network first, and only a failure to connect shows the offline page: an error status from
	// the server is still the server's answer. The response is never stored.
	event.respondWith(
		fetch(request).catch(async () => {
			const offline = await caches.match(new URL('/offline.html', sw.location.origin).href);
			return offline ?? Response.error();
		})
	);
});
