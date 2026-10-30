import {
	expect,
	openSession,
	changePasswordViaApi,
	signInViaApi,
	type APIRequestContext,
	type Browser,
	type Page,
	type Session,
	type SignedInUser
} from './fixtures';

/** Shared end-to-end helpers drive the real UI. */

/** A name that's unique per call, so tests never collide with earlier runs against the same db. */
export function uniqueName(prefix: string): string {
	return `${prefix} ${Date.now()}-${Math.floor(Math.random() * 100_000)}`;
}

export type FieldSpec = {
	label: string;
	/** Kind key from the field-types registry (e.g. 'money', 'url'); defaults to 'text'. */
	kind?: string;
};

/** Create an item type and return its label. */
export async function createItemType(
	page: Page,
	options: { label: string; description?: string; fields?: FieldSpec[] }
): Promise<{ label: string }> {
	await page.goto('/settings/item-types');
	await page.getByRole('button', { name: 'New item type', exact: true }).click();

	const form = page
		.locator('form')
		.filter({ has: page.getByRole('button', { name: 'Add item type' }) });
	await form.getByLabel('Name').fill(options.label);
	if (options.description) {
		await form.getByLabel('Description').fill(options.description);
	}

	for (const field of options.fields ?? []) {
		await form.getByRole('button', { name: 'Add field', exact: true }).click();
		await form.getByLabel('Field label').last().fill(field.label);
		if (field.kind && field.kind !== 'text') {
			await form.getByLabel('Field type').last().selectOption(field.kind);
		}
	}

	await form.getByRole('button', { name: 'Add item type' }).click();
	await expect(page.getByText('Item type created')).toBeVisible();
	await expect(page.getByText(options.label, { exact: true }).first()).toBeVisible();

	return { label: options.label };
}

/**
 * Adds a field to an item type through its edit dialog on the Item types page. Must be called
 * right after `createItemType`, with no navigation in between: newly created types are prepended
 * to the top of the (client-only) list, so `.first()` reliably targets the one just created
 * regardless of what other tests are doing to the shared database.
 */
export async function addFieldToItemType(page: Page, field: FieldSpec): Promise<void> {
	await page.getByRole('button', { name: 'Edit item type' }).first().click();

	const editForm = page
		.locator('form')
		.filter({ has: page.getByRole('button', { name: /^Saving…$|^Save$/ }) });
	await editForm.getByRole('button', { name: 'Add field', exact: true }).click();
	await editForm.getByLabel('Field label').last().fill(field.label);
	await editForm.getByRole('button', { name: /^Saving…$|^Save$/ }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();
}

/** Picks an item type in the type picker: opens it, searches, and chooses the matching row. */
export async function chooseItemType(page: Page, label: string): Promise<void> {
	await page.getByRole('combobox', { name: 'Item type' }).click();
	await page.getByPlaceholder('Search item types…').fill(label);
	await page
		.getByRole('option', { name: new RegExp(label) })
		.first()
		.click();
}

/** Creates an item from the full "New item" form and returns the resulting item detail URL. */
export async function createItem(
	page: Page,
	options: { name: string; type?: string }
): Promise<string> {
	await page.goto('/items/new');
	await page.getByLabel('Name').fill(options.name);

	if (options.type) {
		await chooseItemType(page, options.type);
	}

	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);
	return page.url();
}

/** Connects the currently-open item to another item by name via the "Connect item" form. */
export async function connectToItem(
	page: Page,
	options: { connection: string; targetName: string }
): Promise<void> {
	await page.getByLabel('Connection').fill(options.connection);

	const targetSearch = page.getByPlaceholder('Search items…');
	await targetSearch.fill(options.targetName);
	await page
		.getByRole('button', { name: new RegExp(options.targetName) })
		.first()
		.click();

	// Selecting a target keeps the search input focused, so its dropdown stays
	// open (it only closes ~150ms after blur) and would otherwise overlap the
	// submit button below it.
	await targetSearch.blur();
	await page.waitForTimeout(250);

	await page.getByRole('button', { name: /^Connect items?$/ }).click();
}

export type NavEntry = 'Home' | 'Items' | 'Collections' | 'Settings';

/**
 * Follows a main navigation link using whichever navigation is visible for the current viewport
 * (the sidebar on desktop, the bottom bar on a phone). Hidden links are ignored by role queries,
 * so `.first()` picks the visible one.
 */
export async function openNav(page: Page, entry: NavEntry): Promise<void> {
	const link = page.getByRole('link', { name: entry, exact: true }).first();
	await expect(link).toBeVisible();
	await link.click();
}

/** The visible Search button: the bottom-bar one on a phone (and the top-bar one on touch tablets). */
export const searchButton = (page: Page) =>
	page.getByRole('button', { name: 'Search', exact: true });

/** The top-bar search field, which stands in for the button with a mouse. */
export const searchField = (page: Page) =>
	page.getByRole('combobox', { name: 'Search', exact: true });

/**
 * The open search surface: the full-screen sheet on touch devices, or the top-bar field with its
 * results dropdown with a mouse. Hidden while the search is closed.
 */
export const searchPopup = (page: Page) =>
	page
		.getByRole('dialog', { name: 'Search', exact: true })
		.or(page.locator('[data-search-inline][data-state="open"]'));

/** Opens search: a tap on the button on touch devices, a click into the field with a mouse. */
export async function openSearch(page: Page): Promise<void> {
	if (await page.evaluate(() => matchMedia('(pointer: coarse)').matches)) {
		const button = searchButton(page);
		await expect(button).toBeVisible();
		await button.tap();
	} else {
		await expect(searchField(page)).toBeVisible();
		await searchField(page).click();
	}
	await expect(searchPopup(page)).toBeVisible();
}

/**
 * Opens the quick capture dialog via its global keyboard shortcut. Waits for
 * the app shell to hydrate first - this is a client-rendered SPA, so the
 * keydown listener isn't attached until Svelte has mounted.
 */
export async function openQuickCapture(page: Page) {
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
	// On a phone the bottom bar's "New" button opens it; on desktop the shortcut does.
	const phoneButton = page.getByRole('button', { name: 'New', exact: true });
	if (await phoneButton.isVisible()) await phoneButton.tap();
	else await page.keyboard.press('Control+k');
	const dialog = page.getByRole('dialog', { name: 'Quick capture' });
	await expect(dialog).toBeVisible();
	return dialog;
}

/**
 * Creates collections and items through the API and remembers their ids, so a spec can delete
 * exactly what it made (the database is shared, so list-and-match cleanup could miss rows).
 * Call `cleanUp` from `afterEach`.
 */
export function ownedData() {
	let collectionIds: string[] = [];
	let itemIds: string[] = [];
	let typeIds: string[] = [];

	return {
		trackCollection(id: string) {
			collectionIds.push(id);
		},
		/** Tracks the collection whose page the browser is on and returns its id. */
		trackCollectionFromUrl(page: Page): string {
			const id = new URL(page.url()).pathname.split('/').pop()!;
			collectionIds.push(id);
			return id;
		},
		async makeCollection(request: APIRequestContext, name: string, description?: string) {
			const res = await request.post('/api/v1/collection', { data: { name, description } });
			expect(res.status()).toBe(201);
			const created = (await res.json()) as { id: string; name: string };
			collectionIds.push(created.id);
			return created;
		},
		/** Creates an item type through the API; its slug is made unique from the label. */
		async makeItemType(request: APIRequestContext, label: string) {
			const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
			const res = await request.post('/api/v1/node-type', { data: { slug, label } });
			expect(res.status()).toBe(201);
			const created = (await res.json()) as { id: string; slug: string; label: string };
			typeIds.push(created.id);
			return created;
		},
		async makeItem(request: APIRequestContext, name: string, type?: string) {
			const res = await request.post('/api/v1/node', { data: { name, type } });
			expect(res.status()).toBe(201);
			const created = (await res.json()) as { id: string; name: string };
			itemIds.push(created.id);
			return created;
		},
		async addToCollection(request: APIRequestContext, collectionId: string, ids: string[]) {
			const res = await request.put(`/api/v1/collection/${collectionId}/item`, {
				data: { item_ids: ids }
			});
			expect(res.ok()).toBeTruthy();
		},
		async cleanUp(request: APIRequestContext) {
			for (const id of collectionIds) await request.delete(`/api/v1/collection/${id}`);
			for (let i = 0; i < itemIds.length; i += 50) {
				await Promise.all(
					itemIds.slice(i, i + 50).map((id) => request.delete(`/api/v1/node/${id}`))
				);
			}
			for (const id of typeIds) await request.delete(`/api/v1/node-type/${id}`);
			collectionIds = [];
			itemIds = [];
			typeIds = [];
		}
	};
}

// Add-ons first: removing a base pack is refused while an add-on that needs it is installed.
export const EXAMPLE_PACK_IDS = ['games-extras', 'music', 'recipes', 'movies', 'parts', 'games'];
export const EXAMPLE_SLUG_PREFIXES = /^(music|recipes|movies|parts|games)-/;

/**
 * DELETE that retries up to 3 times when the connection drops (`socket hang up` / `ECONNRESET`,
 * seen under load). Any HTTP response, including 404 and 409, is returned and never retried.
 */
async function deleteTolerantOfReset(request: APIRequestContext, url: string) {
	for (let attempt = 1; ; attempt++) {
		try {
			return await request.delete(url);
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			const dropped = message.includes('socket hang up') || message.includes('ECONNRESET');
			if (!dropped || attempt >= 3) throw error;
		}
	}
}

/**
 * Uninstalls every example pack, then deletes what removal keeps (items and item types with a
 * pack slug prefix), so a kept item can't block the next install.
 */
export async function removeExamplePacks(request: APIRequestContext) {
	for (const id of EXAMPLE_PACK_IDS)
		await deleteTolerantOfReset(request, `/api/v1/example/${id}/installation`);
	const nodes = await request.get('/api/v1/node?limit=500');
	for (const node of (await nodes.json()) as { id: string; type: string | null }[]) {
		if (EXAMPLE_SLUG_PREFIXES.test(node.type ?? ''))
			await deleteTolerantOfReset(request, `/api/v1/node/${node.id}`);
	}
	const types = await request.get('/api/v1/node-type?limit=500');
	for (const type of (await types.json()) as { id: string; slug: string }[]) {
		if (EXAMPLE_SLUG_PREFIXES.test(type.slug))
			await deleteTolerantOfReset(request, `/api/v1/node-type/${type.id}`);
	}
}

/**
 * Makes every collections search request (`GET /collection?...`) fail with a 500 until the
 * returned function is called. Single-collection reads are left alone.
 */
export async function failCollectionSearch(page: Page): Promise<() => Promise<void>> {
	const pattern = /\/api\/v1\/collection\?/;
	await page.route(pattern, (route) =>
		route.fulfill({
			status: 500,
			contentType: 'application/json',
			body: JSON.stringify({ detail: 'Forced failure' })
		})
	);
	return () => page.unroute(pattern);
}

export type E2EUser = {
	id: string;
	username: string;
	displayName: string;
	password: string;
	role: 'admin' | 'member';
	session: Session;
	baseURL: string;
};

/**
 * Creates an account through the API as `admin` (an API context signed in as an administrator),
 * then signs in as it and changes the starting password so the account is ready to use. Pass
 * `keepStartingPassword` to leave it needing a password change (the forced-change flow).
 */
export async function createUserViaApi(
	admin: APIRequestContext,
	baseURL: string,
	options: { prefix?: string; role?: 'admin' | 'member'; keepStartingPassword?: boolean } = {}
): Promise<E2EUser> {
	const username = uniqueName(options.prefix ?? 'user')
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-');
	const startingPassword = `start-${username}-pw`;
	const role = options.role ?? 'member';
	const res = await admin.post('/api/v1/user', {
		data: { username, display_name: `Name ${username}`, password: startingPassword, role }
	});
	expect(res.status(), await res.text()).toBe(201);
	const created = (await res.json()) as { id: string };

	let password = startingPassword;
	let session = await signInViaApi(baseURL, username, startingPassword);
	if (!options.keepStartingPassword) {
		password = `final-${username}-pw`;
		session = await changePasswordViaApi(baseURL, session, startingPassword, password);
	}
	return {
		id: created.id,
		username,
		displayName: `Name ${username}`,
		password,
		role,
		session,
		baseURL
	};
}

/** A browser context, page and API context signed in as `user`. Close `context` when done. */
export function asUser(browser: Browser, user: E2EUser): Promise<SignedInUser> {
	return openSession(browser, user.baseURL, user.session);
}
