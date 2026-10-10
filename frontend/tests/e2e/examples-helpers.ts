import { expect, type APIRequestContext, type Page } from './fixtures';
import { ownedData, removeExamplePacks } from './helpers';

export const MUSIC = /^Music/;
export const MOVIES = /^Movies/;
export const GAMES = /^Board games/;
export const GAMES_EXTRAS = /^Extra board games/;
export const SOUNDTRACKS = /^Film soundtracks/;
export const GAME_COLLECTIONS = [
	{ name: 'Wishlist', count: '2 items' },
	{ name: 'Games for two', count: '2 items' },
	{ name: 'Family game night', count: '4 items' },
	{ name: 'Still to try', count: '3 items' }
];
export const FAMILY_NIGHT_ITEMS = [
	'Slow Parcel Panic',
	'Tea Clipper Race',
	'Ministry of Mild Mischief',
	'Lantern Harbour'
];

/**
 * Per-spec bookkeeping for the example-pack specs: owned collections plus the names of items
 * created or renamed by a test, and a `cleanUp` that leaves the server free of examples.
 */
export function exampleData() {
	const owned = ownedData();
	// Names of items a spec created or renamed, deleted again in cleanup.
	const ownNames: string[] = [];
	const ownTypeLabels: string[] = [];

	async function cleanUp(request: APIRequestContext) {
		await removeExamplePacks(request);
		// Collections made here, including a kept example collection that was edited.
		await owned.cleanUp(request);
		const nodes = await request.get('/api/v1/node?limit=500');
		for (const node of (await nodes.json()) as { id: string; name: string }[]) {
			if (ownNames.includes(node.name)) await request.delete(`/api/v1/node/${node.id}`);
		}
		ownNames.length = 0;
	}

	return { ...owned, ownNames, ownTypeLabels, cleanUp };
}

export async function install(page: Page, pack: RegExp) {
	await page.goto('/settings/examples');
	await page.getByRole('button', { name: new RegExp(`^Add ${pack.source.slice(1)}`) }).click();
	await expect(page.getByText('Examples added')).toBeVisible();
	await expect(
		page.getByRole('button', { name: new RegExp(`^Remove ${pack.source.slice(1)}`) })
	).toBeVisible();
}

export async function remove(page: Page, pack: RegExp) {
	await page.goto('/settings/examples');
	await page.getByRole('button', { name: new RegExp(`^Remove ${pack.source.slice(1)}`) }).click();
	await page
		.getByRole('dialog', { name: 'Remove these examples?' })
		.getByRole('button', { name: 'Remove', exact: true })
		.click();
}

export async function openItem(page: Page, name: string) {
	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(name);
	await page.getByRole('link', { name }).first().click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);
	await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
}

export const collectionCard = (page: Page, name: string) =>
	page.getByRole('link').filter({ hasText: new RegExp(`^\\s*${name}(\\s|$)`) });

export const OWN_COVER = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
	'base64'
);

export type ApiNode = { id: string; name: string; type: string | null };
export type ApiMedia = { id: string; filename: string; attribute_key: string | null };

export async function nodesNamed(request: APIRequestContext, name: string): Promise<ApiNode[]> {
	const nodes = (await (await request.get('/api/v1/node?limit=500')).json()) as ApiNode[];
	return nodes.filter((n) => n.name === name);
}

export async function nodeNamed(request: APIRequestContext, name: string): Promise<ApiNode> {
	const found = await nodesNamed(request, name);
	expect(found).toHaveLength(1);
	return found[0];
}

export async function mediaOf(request: APIRequestContext, nodeId: string): Promise<ApiMedia[]> {
	const res = await request.get(`/api/v1/media/for-node/${nodeId}`);
	return res.ok() ? ((await res.json()) as ApiMedia[]) : [];
}

export const coverOf = async (request: APIRequestContext, nodeId: string) =>
	(await mediaOf(request, nodeId)).find((m) => m.attribute_key === 'cover');

/** Uploads an image and makes it the node's cover, replacing any current one (as the UI does). */
export async function setOwnCover(request: APIRequestContext, nodeId: string) {
	const res = await request.post('/api/v1/media/attached', {
		multipart: {
			file: { name: 'mine.png', mimeType: 'image/png', buffer: OWN_COVER },
			target_type: 'node',
			target_id: nodeId
		}
	});
	expect(res.ok(), await res.text()).toBeTruthy();
	const asset = (await res.json()) as { media_id?: string; asset_id?: string; id?: string };
	const assetId = asset.media_id ?? asset.asset_id ?? asset.id;
	const cover = await request.post(`/api/v1/media/${assetId}/attachments/cover`, {
		data: { target_type: 'node', target_id: nodeId }
	});
	expect(cover.ok(), await cover.text()).toBeTruthy();
}

export async function installViaApi(request: APIRequestContext, pack: string) {
	const res = await request.put(`/api/v1/example/${pack}/installation`);
	expect(res.ok()).toBeTruthy();
}

export async function removeViaApi(request: APIRequestContext, pack: string) {
	const res = await request.delete(`/api/v1/example/${pack}/installation`);
	expect(res.ok()).toBeTruthy();
}

export const packCard = (page: Page, title: string) =>
	page.locator('[data-slot="card"]').filter({ has: page.getByText(title, { exact: true }) });

export async function installViaApiMany(request: APIRequestContext, packs: string[]) {
	for (const pack of packs) {
		const res = await request.put(`/api/v1/example/${pack}/installation`);
		expect(res.ok(), await res.text()).toBeTruthy();
	}
}
