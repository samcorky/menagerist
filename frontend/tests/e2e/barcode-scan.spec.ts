import { test, expect, type Page } from './fixtures';
import {
	chooseItemType,
	createItem,
	createItemType,
	openQuickCapture,
	uniqueName
} from './helpers';

/** A valid EAN-13 (the check digit is right), so the real detector accepts it. */
const EAN = '4006381333931';

/** The camera is refused, as when the person says no to the permission prompt. */
async function refuseCamera(page: Page) {
	await page.addInitScript(() => {
		navigator.mediaDevices.getUserMedia = () =>
			Promise.reject(new DOMException('Permission denied', 'NotAllowedError'));
	});
}

/**
 * A camera that films a printed EAN-13, and no native `BarcodeDetector`, so the scan goes
 * through the WebAssembly fallback served by the app under its real CSP.
 */
async function filmBarcode(page: Page, digits: string) {
	await page.addInitScript((code) => {
		Object.defineProperty(window, 'BarcodeDetector', { value: undefined, configurable: true });
		const L = [
			'0001101',
			'0011001',
			'0010011',
			'0111101',
			'0100011',
			'0110001',
			'0101111',
			'0111011',
			'0110111',
			'0001011'
		];
		const R = L.map((bits) => [...bits].map((b) => (b === '0' ? '1' : '0')).join(''));
		const G = R.map((bits) => [...bits].reverse().join(''));
		const PARITY = [
			'LLLLLL',
			'LLGLGG',
			'LLGGLG',
			'LLGGGL',
			'LGLLGG',
			'LGGLLG',
			'LGGGLL',
			'LGLGLG',
			'LGLGGL',
			'LGGLGL'
		];
		const d = [...code].map(Number);
		let bars = '101';
		for (let i = 1; i <= 6; i++) bars += (PARITY[d[0]][i - 1] === 'L' ? L : G)[d[i]];
		bars += '01010';
		for (let i = 7; i <= 12; i++) bars += R[d[i]];
		bars += '101';

		const canvas = document.createElement('canvas');
		canvas.width = 640;
		canvas.height = 480;
		const ctx = canvas.getContext('2d')!;
		const draw = () => {
			ctx.fillStyle = '#fff';
			ctx.fillRect(0, 0, canvas.width, canvas.height);
			ctx.fillStyle = '#000';
			const module = 4;
			const left = (canvas.width - bars.length * module) / 2;
			[...bars].forEach((bit, i) => {
				if (bit === '1') ctx.fillRect(left + i * module, 140, module, 200);
			});
		};
		draw();
		// A canvas stream only sends frames when the canvas is painted.
		setInterval(draw, 100);
		navigator.mediaDevices.getUserMedia = async () => canvas.captureStream(10);
	}, digits);
}

/** A camera with (or without) a light: its track reports `torch` and records the switching. */
async function cameraWithLight(page: Page, hasLight: boolean) {
	await page.addInitScript((light) => {
		const lit: boolean[] = [];
		(window as unknown as { lit: boolean[] }).lit = lit;
		navigator.mediaDevices.getUserMedia = async () => {
			const canvas = document.createElement('canvas');
			canvas.width = 64;
			canvas.height = 48;
			const stream = canvas.captureStream(5);
			const track = stream.getVideoTracks()[0];
			Object.assign(track, {
				getCapabilities: () => (light ? { torch: true } : {}),
				applyConstraints: async (c: { advanced?: { torch?: boolean }[] }) => {
					lit.push(Boolean(c.advanced?.[0]?.torch));
				}
			});
			return stream;
		};
	}, hasLight);
}

async function saveAndOpen(page: Page, dialog: ReturnType<Page['getByRole']>, name: string) {
	await dialog.getByPlaceholder('Name…').fill(name);
	await dialog.getByRole('button', { name: /^Saving…$|^Save$/ }).click();
	await expect(dialog).toBeHidden();
	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(name);
	await page.getByText(name, { exact: true }).first().click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);
}

test('types the code when the camera is refused, and keeps it as a Barcode detail', async ({
	page
}) => {
	await refuseCamera(page);
	const name = uniqueName('Typed barcode');

	await page.goto('/');
	const capture = await openQuickCapture(page);
	await capture.getByRole('button', { name: 'Scan barcode' }).click();

	const scanner = page.getByRole('dialog', { name: 'Scan barcode' });
	await expect(scanner.getByText('Camera access is turned off')).toBeVisible();
	await scanner.getByLabel('Or type the code').fill(` ${EAN} `);
	await scanner.getByRole('button', { name: 'Use code' }).click();
	await expect(scanner).toBeHidden();

	await expect(capture.getByText(EAN)).toBeVisible();
	await expect(capture.getByText('Saved as a Barcode detail.')).toBeVisible();

	await saveAndOpen(page, capture, name);
	await expect(page.getByText('Barcode', { exact: true })).toBeVisible();
	await expect(page.getByText(EAN)).toBeVisible();
});

test('scans with the built-in WebAssembly detector into the field the type suggests', async ({
	page
}) => {
	const type = await createItemType(page, {
		label: uniqueName('Scanned book'),
		fields: [{ label: 'Author' }, { label: 'ISBN' }]
	});
	await filmBarcode(page, EAN);
	const name = uniqueName('Scanned item');

	await page.goto('/');
	const capture = await openQuickCapture(page);
	await chooseItemType(page, type.label);
	await capture.getByRole('button', { name: 'Scan barcode' }).click();

	await expect(page.getByRole('dialog', { name: 'Scan barcode' })).toBeHidden({ timeout: 15_000 });
	await expect(capture.getByText(EAN)).toBeVisible();
	await expect(capture.getByLabel('Save in')).toHaveValue('isbn');

	await saveAndOpen(page, capture, name);
	await expect(page.getByText('ISBN', { exact: true })).toBeVisible();
	await expect(page.getByText(EAN)).toBeVisible();
});

test('carries the scanned code into the full form', async ({ page }) => {
	await refuseCamera(page);

	await page.goto('/');
	const capture = await openQuickCapture(page);
	await capture.getByRole('button', { name: 'Scan barcode' }).click();
	const scanner = page.getByRole('dialog', { name: 'Scan barcode' });
	await scanner.getByLabel('Or type the code').fill(EAN);
	await scanner.getByRole('button', { name: 'Use code' }).click();
	await capture.getByRole('button', { name: 'Use full form →' }).click();

	await page.waitForURL(/\/items\/new$/);
	await expect(page.getByLabel('Barcode', { exact: true })).toHaveValue(EAN);
});

test.describe('when the barcode field is shown in quick capture', () => {
	async function typeCode(page: Page, capture: ReturnType<Page['getByRole']>) {
		await capture.getByRole('button', { name: 'Scan barcode' }).click();
		const scanner = page.getByRole('dialog', { name: 'Scan barcode' });
		await scanner.getByLabel('Or type the code').fill(EAN);
		await scanner.getByRole('button', { name: 'Use code' }).click();
	}

	test('a scan fills the field, replacing what was typed, with no Save in choice', async ({
		page
	}) => {
		await refuseCamera(page);
		const type = await createItemType(page, {
			label: uniqueName('Shown book'),
			fields: [{ label: 'ISBN', capture: true }]
		});

		await page.goto('/');
		const capture = await openQuickCapture(page);
		await chooseItemType(page, type.label);
		await capture.getByLabel('ISBN').fill('111');
		await typeCode(page, capture);

		await expect(capture.getByLabel('ISBN')).toHaveValue(EAN);
		await expect(capture.getByLabel('Save in')).toHaveCount(0);
	});

	test('a code scanned before choosing the type moves into the field', async ({ page }) => {
		await refuseCamera(page);
		const type = await createItemType(page, {
			label: uniqueName('Shown book'),
			fields: [{ label: 'ISBN', capture: true }]
		});

		await page.goto('/');
		const capture = await openQuickCapture(page);
		await typeCode(page, capture);
		await chooseItemType(page, type.label);

		await expect(capture.getByLabel('ISBN')).toHaveValue(EAN);
		await expect(capture.getByText('Saved as a Barcode detail.')).toHaveCount(0);
	});
});

test.describe('a field that takes barcodes', () => {
	async function scanInto(page: Page, label: string) {
		await page.getByRole('button', { name: `Scan barcode into ${label}` }).click();
		const scanner = page.getByRole('dialog', { name: 'Scan barcode' });
		await scanner.getByLabel('Or type the code').fill(EAN);
		await scanner.getByRole('button', { name: 'Use code' }).click();
	}

	test('can be scanned into on the new item form', async ({ page }) => {
		await refuseCamera(page);
		const type = await createItemType(page, {
			label: uniqueName('Barcoded'),
			fields: [{ label: 'Author' }, { label: 'ISBN', barcode: true }]
		});

		await page.goto('/items/new');
		await chooseItemType(page, type.label);
		await expect(page.getByRole('button', { name: 'Scan barcode into Author' })).toHaveCount(0);
		await scanInto(page, 'ISBN');
		await expect(page.getByLabel('ISBN', { exact: true })).toHaveValue(EAN);
	});

	test('can be scanned into when editing, replacing the value', async ({ page }) => {
		await refuseCamera(page);
		const type = await createItemType(page, {
			label: uniqueName('Barcoded'),
			fields: [{ label: 'ISBN', barcode: true }]
		});
		await createItem(page, { name: uniqueName('Edited by scan'), type: type.label });

		await page.getByRole('button', { name: 'Edit', exact: true }).filter({ visible: true }).click();
		await page.getByLabel('ISBN', { exact: true }).fill('111');
		await scanInto(page, 'ISBN');
		await expect(page.getByLabel('ISBN', { exact: true })).toHaveValue(EAN);
		await page.getByRole('button', { name: 'Save changes' }).click();
		await expect(page.getByText(EAN)).toBeVisible();
	});

	test('is chosen for a scan in quick capture ahead of a label guess', async ({ page }) => {
		await refuseCamera(page);
		const type = await createItemType(page, {
			label: uniqueName('Shop stock'),
			fields: [{ label: 'ISBN' }, { label: 'Shop code', barcode: true }]
		});

		await page.goto('/');
		const capture = await openQuickCapture(page);
		await chooseItemType(page, type.label);
		await capture.getByRole('button', { name: 'Scan barcode', exact: true }).click();
		const scanner = page.getByRole('dialog', { name: 'Scan barcode' });
		await scanner.getByLabel('Or type the code').fill(EAN);
		await scanner.getByRole('button', { name: 'Use code' }).click();

		await expect(capture.getByLabel('Save in')).toHaveValue('shop_code');
		await expect(capture.getByLabel('Save in').getByRole('option')).toHaveText([
			'Shop code',
			'A new Barcode detail'
		]);
	});
});

test.describe('the light', () => {
	async function openScanner(page: Page) {
		await page.goto('/');
		const capture = await openQuickCapture(page);
		await capture.getByRole('button', { name: 'Scan barcode' }).click();
		return page.getByRole('dialog', { name: 'Scan barcode' });
	}
	const lit = (page: Page) => page.evaluate(() => (window as unknown as { lit: boolean[] }).lit);

	test('is switched on and off from the scanner when the camera has one', async ({ page }) => {
		await cameraWithLight(page, true);
		const scanner = await openScanner(page);

		const light = scanner.getByRole('button', { name: 'Turn the light on' });
		await expect(light).toHaveAttribute('aria-pressed', 'false');
		await light.click();
		const off = scanner.getByRole('button', { name: 'Turn the light off' });
		await expect(off).toHaveAttribute('aria-pressed', 'true');
		await off.click();
		await expect(scanner.getByRole('button', { name: 'Turn the light on' })).toBeVisible();
		expect(await lit(page)).toEqual([true, false]);
	});

	test('is not offered when the camera has none', async ({ page }) => {
		await cameraWithLight(page, false);
		const scanner = await openScanner(page);

		const preview = scanner.getByLabel('Camera preview');
		await expect
			.poll(() => preview.evaluate((video: HTMLVideoElement) => video.srcObject !== null))
			.toBe(true);
		await expect(scanner.getByRole('button', { name: /Turn the light/ })).toHaveCount(0);
	});
});
