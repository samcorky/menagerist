import { afterEach, describe, expect, it, vi } from 'vitest';
import { absoluteUrl, shareLink } from '../src/lib/share';

const LINK = { title: 'Alien', url: 'https://menagerist.example.com/items/abc' };

afterEach(() => vi.unstubAllGlobals());

/** A clipboard that records what is copied, or refuses to. */
function stubClipboard(writeText: (text: string) => Promise<void>) {
	vi.stubGlobal('navigator', { clipboard: { writeText } });
}

describe('absoluteUrl', () => {
	it('puts a path on the origin it is given, keeping the base path', () => {
		expect(absoluteUrl('/items/abc', 'https://menagerist.example.com')).toBe(LINK.url);
		expect(absoluteUrl('/app/items/abc', 'https://example.com')).toBe(
			'https://example.com/app/items/abc'
		);
	});
});

describe('shareLink', () => {
	it('hands the title and address to the share sheet where there is one', async () => {
		const share = vi.fn().mockResolvedValue(undefined);

		expect(await shareLink(LINK, { share })).toBe('shared');
		expect(share).toHaveBeenCalledWith(LINK);
	});

	it('leaves it alone when the person backs out of the share sheet', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		stubClipboard(writeText);
		const share = vi.fn().mockRejectedValue(new DOMException('closed', 'AbortError'));

		expect(await shareLink(LINK, { share })).toBe('cancelled');
		expect(writeText).not.toHaveBeenCalled();
	});

	it('copies the address instead when the share sheet refuses', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		stubClipboard(writeText);
		const share = vi.fn().mockRejectedValue(new DOMException('no', 'NotAllowedError'));

		expect(await shareLink(LINK, { share })).toBe('copied');
		expect(writeText).toHaveBeenCalledWith(LINK.url);
	});

	it('copies the address where the browser has no share sheet', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		stubClipboard(writeText);

		expect(await shareLink(LINK, {})).toBe('copied');
		expect(writeText).toHaveBeenCalledWith(LINK.url);
	});

	it('copies the address when the browser says it cannot share this', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		stubClipboard(writeText);
		const share = vi.fn();

		expect(await shareLink(LINK, { share, canShare: () => false })).toBe('copied');
		expect(share).not.toHaveBeenCalled();
	});

	it('says so when the address could be neither shared nor copied', async () => {
		stubClipboard(() => Promise.reject(new Error('denied')));

		expect(await shareLink(LINK, {})).toBe('failed');
	});
});
