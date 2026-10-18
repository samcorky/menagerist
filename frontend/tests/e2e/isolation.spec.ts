import { expect, request, sessionOptions, test, type APIRequestContext } from './fixtures';
import {
	asUser,
	createUserViaApi,
	openSearch,
	removeExamplePacks,
	uniqueName,
	type E2EUser
} from './helpers';
import { OWN_COVER } from './examples-helpers';

/**
 * Two members of one installation must never see each other's content. Users are created through
 * the API by the worker's administrator; each test then drives the app as one of them.
 */
test.describe.configure({ mode: 'serial' });

const token = uniqueName('Isolation').replace(/\s+/g, '-');

type Made = { itemId: string; itemName: string; collectionId: string; collectionName: string };

let admin: APIRequestContext;
let userA: E2EUser;
let userB: E2EUser;
let aContent: Made;
let aMediaId: string;

async function json<T>(res: Awaited<ReturnType<APIRequestContext['get']>>): Promise<T> {
	expect(res.ok(), await res.text()).toBeTruthy();
	return (await res.json()) as T;
}

async function makeContent(api: APIRequestContext, label: string): Promise<Made> {
	const itemName = `${token} ${label} item`;
	const collectionName = `${token} ${label} collection`;
	const item = await json<{ id: string }>(
		await api.post('/api/v1/node', { data: { name: itemName } })
	);
	const collection = await json<{ id: string }>(
		await api.post('/api/v1/collection', { data: { name: collectionName } })
	);
	const added = await api.put(`/api/v1/collection/${collection.id}/item`, {
		data: { item_ids: [item.id] }
	});
	expect(added.ok(), await added.text()).toBeTruthy();
	return { itemId: item.id, itemName, collectionId: collection.id, collectionName };
}

test.beforeAll(async ({ workerBaseURL, workerSession }) => {
	admin = await request.newContext(sessionOptions(workerBaseURL, workerSession));
	userA = await createUserViaApi(admin, workerBaseURL, { prefix: 'iso-a' });
	userB = await createUserViaApi(admin, workerBaseURL, { prefix: 'iso-b' });
});

test.afterAll(async () => {
	await admin.dispose();
});

test('user A creates content that only A can reach', async ({ browser }) => {
	const a = await asUser(browser, userA);
	aContent = await makeContent(a.request, 'alpha');

	const upload = await a.request.post('/api/v1/media/attached', {
		multipart: {
			file: { name: 'alpha.png', mimeType: 'image/png', buffer: OWN_COVER },
			target_type: 'node',
			target_id: aContent.itemId
		}
	});
	const media = await json<{ media_id?: string; asset_id?: string; id?: string }>(upload);
	aMediaId = (media.media_id ?? media.asset_id ?? media.id)!;
	expect(aMediaId).toBeTruthy();

	// Positive control: A reaches all of it.
	await a.page.goto(`/items/${aContent.itemId}`);
	await expect(a.page.getByText(aContent.itemName, { exact: true }).first()).toBeVisible();
	expect((await a.request.get(`/api/v1/media/${aMediaId}/content`)).status()).toBe(200);
	await a.context.close();
});

test("B's lists, collection list and API searches do not include A's content", async ({
	browser
}) => {
	const b = await asUser(browser, userB);
	const own = await makeContent(b.request, 'bravo');

	await b.page.goto('/items');
	await b.page.getByPlaceholder('Search your items…').fill(token);
	await expect(b.page.getByRole('link', { name: own.itemName })).toBeVisible();
	await expect(b.page.getByText(aContent.itemName)).toHaveCount(0);

	await b.page.goto('/collections');
	await expect(b.page.getByText(own.collectionName).first()).toBeVisible();
	await expect(b.page.getByText(aContent.collectionName)).toHaveCount(0);

	// The same through the API: lists, search, and one collection's items.
	const nodes = await json<{ id: string }[]>(
		await b.request.get(`/api/v1/node?q=${token}&limit=100`)
	);
	expect(nodes.map((n) => n.id)).toEqual([own.itemId]);
	const collections = await json<{ id: string }[]>(await b.request.get('/api/v1/collection'));
	expect(collections.map((c) => c.id)).not.toContain(aContent.collectionId);
	expect((await b.request.get(`/api/v1/collection/${aContent.collectionId}/item`)).status()).toBe(
		404
	);
	await b.context.close();
});

test("B's search palette finds B's content but never A's", async ({ browser }) => {
	const b = await asUser(browser, userB);
	await b.page.goto('/');
	await openSearch(b.page);
	const dialog = b.page.getByRole('dialog', { name: 'Search', exact: true });
	await dialog.getByRole('combobox').fill(token);
	await expect(dialog.getByText(`${token} bravo item`)).toBeVisible();
	await expect(dialog.getByText(`${token} bravo collection`)).toBeVisible();
	await expect(dialog.getByText(`${token} alpha`)).toHaveCount(0);
	await b.context.close();
});

test("A's item, collection and media are not found by direct URL for B", async ({ browser }) => {
	const b = await asUser(browser, userB);

	await b.page.goto(`/items/${aContent.itemId}`);
	await expect(b.page.getByRole('heading', { name: 'Item not found' })).toBeVisible();
	await expect(b.page.getByText(aContent.itemName)).toHaveCount(0);

	await b.page.goto(`/collections/${aContent.collectionId}`);
	await expect(b.page.getByRole('heading', { name: 'Collection not found' })).toBeVisible();
	await expect(b.page.getByText(aContent.collectionName)).toHaveCount(0);

	// 404 (not 403) for everything that exists but is not B's, media included.
	for (const path of [
		`/api/v1/node/${aContent.itemId}`,
		`/api/v1/collection/${aContent.collectionId}`,
		`/api/v1/media/${aMediaId}`,
		`/api/v1/media/${aMediaId}/content`,
		`/api/v1/media/${aMediaId}/thumbnail`
	]) {
		const res = await b.request.get(path);
		expect(res.status(), path).toBe(404);
	}
	// A list, not a single thing: B gets an empty one rather than A's attachments.
	const attached = await b.request.get(`/api/v1/media/for-node/${aContent.itemId}`);
	expect(await json<unknown[]>(attached)).toEqual([]);
	await b.context.close();
});

test('an administrator can add a member who then has to choose a password at first sign-in', async ({
	page,
	browser,
	workerBaseURL
}) => {
	const username = uniqueName('made')
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-');
	const startingPassword = `start-${username}-pw`;

	await page.goto('/admin/users');
	await page.getByRole('button', { name: 'Add user' }).first().click();
	const form = page.locator('form').filter({ has: page.getByLabel('Starting password') });
	await form.getByLabel('Name', { exact: true }).fill('Made Member');
	await form.getByLabel('Username').fill(username);
	await form.getByLabel('Starting password').fill(startingPassword);
	await form.getByRole('button', { name: 'Add user' }).click();
	await expect(page.getByRole('list', { name: 'Users' })).toContainText(username);

	// The new account signs in (and has to choose its own password first).
	// Explicit empty state: new contexts otherwise inherit the worker administrator's session.
	const member = await browser.newContext({
		baseURL: workerBaseURL,
		storageState: { cookies: [], origins: [] },
		extraHTTPHeaders: {}
	});
	const memberPage = await member.newPage();
	await memberPage.goto('/login');
	await memberPage.getByLabel('Username').fill(username);
	await memberPage.getByLabel('Password', { exact: true }).fill(startingPassword);
	await memberPage.getByRole('button', { name: 'Sign in', exact: true }).click();
	await expect(memberPage).toHaveURL(/\/settings\/account$/);
	await member.close();
});

test('a member cannot open the Users page or call its API', async ({ browser }) => {
	const b = await asUser(browser, userB);
	await b.page.goto('/');
	await b.page.getByRole('button', { name: /^Account menu for / }).click();
	await expect(b.page.getByRole('menuitem', { name: 'Account' })).toBeVisible();
	await expect(b.page.getByRole('menuitem', { name: 'Administration' })).toHaveCount(0);
	await b.page.keyboard.press('Escape');

	await b.page.goto('/admin/users');
	await expect(b.page.getByText('Only administrators can manage users.')).toBeVisible();
	expect((await b.request.get('/api/v1/user')).status()).toBe(403);
	await b.context.close();
});

test('each user installs the same example pack and sees only their own copy', async ({
	browser
}) => {
	const a = await asUser(browser, userA);
	const b = await asUser(browser, userB);
	const pack = 'recipes';
	const slugPrefix = /^recipes-/;

	try {
		for (const user of [a, b]) {
			const res = await user.request.put(`/api/v1/example/${pack}/installation`);
			expect(res.ok(), await res.text()).toBeTruthy();
		}

		const idsOf = async (api: APIRequestContext) => {
			const nodes = await json<{ id: string; type: string | null }[]>(
				await api.get('/api/v1/node?limit=500')
			);
			return nodes.filter((n) => slugPrefix.test(n.type ?? '')).map((n) => n.id);
		};
		const idsA = await idsOf(a.request);
		const idsB = await idsOf(b.request);
		expect(idsA.length).toBeGreaterThan(0);
		expect(idsB).toHaveLength(idsA.length);
		expect(idsB.filter((id) => idsA.includes(id))).toEqual([]);

		// Each sees their own installation on the page, and A removing theirs leaves B's alone.
		await b.page.goto('/settings/examples');
		await expect(b.page.getByRole('button', { name: /^Remove Recipes/ })).toBeVisible();

		const removed = await a.request.delete(`/api/v1/example/${pack}/installation`);
		expect(removed.ok(), await removed.text()).toBeTruthy();
		expect(await idsOf(b.request)).toEqual(idsB);
	} finally {
		// Items first (as their owners), then the shared item types (administrators only).
		await removeExamplePacks(a.request);
		await removeExamplePacks(b.request);
		await removeExamplePacks(admin);
		await a.context.close();
		await b.context.close();
	}
});

test('a member cannot delete an item type: no control, and the API refuses', async ({
	browser,
	page
}) => {
	const label = uniqueName('Iso type');
	const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const made = await json<{ id: string }>(
		await admin.post('/api/v1/node-type', { data: { slug, label } })
	);

	try {
		const b = await asUser(browser, userB);
		await b.page.goto('/settings/item-types');
		await expect(b.page.getByText(label, { exact: true }).first()).toBeVisible();
		await expect(b.page.getByRole('button', { name: 'Edit item type' }).first()).toBeVisible();
		await expect(b.page.getByRole('button', { name: 'Delete item type' })).toHaveCount(0);

		const denied = await b.request.delete(`/api/v1/node-type/${made.id}`);
		expect(denied.status()).toBe(403);
		await b.context.close();

		// An administrator does get the control.
		await page.goto('/settings/item-types');
		await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
		await expect(page.getByRole('button', { name: 'Delete item type' }).first()).toBeVisible();
	} finally {
		await admin.delete(`/api/v1/node-type/${made.id}`);
	}
});
