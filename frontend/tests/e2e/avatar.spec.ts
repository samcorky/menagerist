import { expect, request, apiSessionOptions, test } from './fixtures';
import { asUser, createUserViaApi } from './helpers';

/**
 * Account pictures: upload with a crop, go back to initials, and Random cat falling back to a
 * cat drawn in the browser when the server's cat service is unavailable. Each test uses its own
 * member, so parallel workers never share a picture.
 */

// A 1×1 red PNG: small, but a real image for both the browser and the server to decode.
const RED_PIXEL = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==',
	'base64'
);

async function member(browser: Parameters<typeof asUser>[0], baseURL: string, session: never) {
	const adminApi = await request.newContext(apiSessionOptions(baseURL, session));
	const user = await createUserViaApi(adminApi, baseURL, { prefix: 'picture' });
	await adminApi.dispose();
	return { user, signedIn: await asUser(browser, user) };
}

test('a member uploads a cropped picture, then goes back to initials', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const { user, signedIn } = await member(browser, workerBaseURL, workerSession as never);
	const page = signedIn.page;
	const trigger = page.getByRole('button', { name: `Account menu for ${user.displayName}` });

	await page.goto('/settings/account');
	await expect(page.getByRole('heading', { name: 'Picture' })).toBeVisible();
	await expect(trigger.locator('img')).toHaveCount(0);

	await page
		.locator('input[type="file"]')
		.setInputFiles({ name: 'me.png', mimeType: 'image/png', buffer: RED_PIXEL });
	const dialog = page.getByRole('dialog', { name: 'Crop your picture' });
	await expect(dialog.getByRole('button', { name: /Picture crop area/ })).toBeVisible();
	await dialog.getByRole('button', { name: 'Save' }).click();

	await expect(page.getByText('Picture updated')).toBeVisible();
	await expect(dialog).toBeHidden();
	await expect(trigger.locator('img')).toHaveAttribute('src', /\/avatar\/64\?v=[0-9a-f]{16}$/);

	await page.getByRole('button', { name: 'Use initials' }).click();
	await expect(page.getByText('Showing your initials')).toBeVisible();
	await expect(trigger.locator('img')).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Use initials' })).toBeHidden();
	await expect(page.getByRole('button', { name: 'Upload picture' })).toBeFocused();

	await signedIn.context.close();
});

test('Random cat draws a cat in the browser when the cat service is unavailable', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const { user, signedIn } = await member(browser, workerBaseURL, workerSession as never);
	const page = signedIn.page;
	await page.route('**/api/v1/me/avatar/cat', (route) =>
		route.fulfill({
			status: 503,
			contentType: 'application/problem+json',
			body: JSON.stringify({
				type: 'about:blank',
				title: 'CatServiceUnavailableError',
				status: 503,
				detail: 'The cat service is not available.',
				instance: `${workerBaseURL}/api/v1/me/avatar/cat`
			})
		})
	);

	await page.goto('/settings/account');
	await page.getByRole('button', { name: 'Random cat' }).click();

	await expect(
		page.getByText("The cat service isn't available, so here's a drawn cat.")
	).toBeVisible();
	const trigger = page.getByRole('button', { name: `Account menu for ${user.displayName}` });
	await expect(trigger.locator('img')).toHaveAttribute('src', /\/avatar\/64\?v=/);

	await signedIn.context.close();
});

test('an unreadable file closes the crop dialog and explains why', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const { signedIn } = await member(browser, workerBaseURL, workerSession as never);
	const page = signedIn.page;

	await page.goto('/settings/account');
	await page.locator('input[type="file"]').setInputFiles({
		name: 'notes.png',
		mimeType: 'image/png',
		buffer: Buffer.from('not a picture')
	});

	await expect(page.getByText("Couldn't change your picture")).toBeVisible();
	await expect(page.getByRole('dialog', { name: 'Crop your picture' })).toBeHidden();

	await signedIn.context.close();
});

test('Random cat keeps keyboard focus while it works', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const { signedIn } = await member(browser, workerBaseURL, workerSession as never);
	const page = signedIn.page;
	await page.route('**/api/v1/me/avatar/cat', (route) =>
		route.fulfill({ status: 503, contentType: 'application/problem+json', body: '{}' })
	);

	await page.goto('/settings/account');
	const button = page.getByRole('button', { name: 'Random cat' });
	await button.focus();
	await page.keyboard.press('Enter');

	await expect(
		page.getByText("The cat service isn't available, so here's a drawn cat.")
	).toBeVisible();
	await expect(button).toBeFocused();

	await signedIn.context.close();
});
