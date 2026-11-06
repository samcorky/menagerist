import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	changesPage,
	jumpsToFragment,
	clearPositions,
	restoreScroll,
	savePosition,
	savedPosition,
	scrollToFragment
} from '$lib/scroll-restore';

const url = (path: string) => new URL(path, 'http://localhost');

function scroller(scrollHeight: number, clientHeight = 500) {
	return { scrollTop: 0, scrollHeight, clientHeight } as HTMLElement;
}

beforeEach(() => {
	clearPositions();
	vi.useFakeTimers();
	vi.stubGlobal('requestAnimationFrame', (cb: () => void) => setTimeout(cb, 16));
	vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
});

afterEach(() => {
	vi.useRealTimers();
	vi.unstubAllGlobals();
});

describe('positions', () => {
	it('keys by path and query, ignoring the fragment', () => {
		savePosition(url('/items?q=a#top'), 300);
		expect(savedPosition(url('/items?q=a'))).toBe(300);
		expect(savedPosition(url('/items?q=b'))).toBeUndefined();
	});
});

describe('changesPage', () => {
	it('is false for a query rewrite on the same path', () => {
		expect(changesPage(url('/items'), url('/items?q=a'))).toBe(false);
		expect(changesPage(url('/items'), url('/home'))).toBe(true);
		expect(changesPage(undefined, url('/home'))).toBe(true);
	});
});

describe('jumpsToFragment', () => {
	it('jumps when the fragment is new or the page changes', () => {
		expect(jumpsToFragment(url('/a'), url('/a#x'))).toBe(true);
		expect(jumpsToFragment(url('/a#x'), url('/a#y'))).toBe(true);
		expect(jumpsToFragment(url('/a#x'), url('/b#x'))).toBe(true);
		expect(jumpsToFragment(undefined, url('/a#x'))).toBe(true);
	});

	it('stays put when a query rewrite carries the same fragment', () => {
		expect(jumpsToFragment(url('/a#x'), url('/a?q=1#x'))).toBe(false);
	});

	it('never jumps without a fragment', () => {
		expect(jumpsToFragment(url('/a#x'), url('/a'))).toBe(false);
	});
});

describe('restoreScroll', () => {
	it('scrolls at once when the content is tall enough', () => {
		const el = scroller(2000);
		restoreScroll(el, 400);
		expect(el.scrollTop).toBe(400);
	});

	it('keeps retrying until late content makes the position reachable', () => {
		const el = scroller(600);
		// A real element clamps scrollTop to the content; mimic that.
		let top = 0;
		Object.defineProperty(el, 'scrollTop', {
			get: () => top,
			set: (v: number) => (top = Math.min(v, el.scrollHeight - el.clientHeight))
		});
		restoreScroll(el, 400);
		expect(top).toBe(100);
		Object.defineProperty(el, 'scrollHeight', { value: 2000 });
		vi.advanceTimersByTime(50);
		expect(top).toBe(400);
	});

	it('stops once the person scrolls themselves', () => {
		const el = scroller(600);
		let top = 0;
		Object.defineProperty(el, 'scrollTop', {
			get: () => top,
			set: (v: number) => (top = Math.min(v, el.scrollHeight - el.clientHeight))
		});
		restoreScroll(el, 400);
		top = 10;
		Object.defineProperty(el, 'scrollHeight', { value: 2000 });
		vi.advanceTimersByTime(50);
		expect(top).toBe(10);
	});

	it('can be cancelled', () => {
		const el = scroller(600);
		let top = 0;
		Object.defineProperty(el, 'scrollTop', {
			get: () => top,
			set: (v: number) => (top = Math.min(v, el.scrollHeight - el.clientHeight))
		});
		const cancel = restoreScroll(el, 400);
		cancel();
		Object.defineProperty(el, 'scrollHeight', { value: 2000 });
		vi.advanceTimersByTime(50);
		expect(top).toBe(100);
	});
});

describe('scrollToFragment', () => {
	it('scrolls the target into view', () => {
		const target = { scrollIntoView: vi.fn() };
		const el = {
			scrollTop: 50,
			ownerDocument: { getElementById: (id: string) => (id === 'a b' ? target : null) }
		} as unknown as HTMLElement;
		scrollToFragment(el, '#a%20b');
		expect(target.scrollIntoView).toHaveBeenCalled();
	});

	it('goes to the top when the fragment names nothing', () => {
		const el = {
			scrollTop: 50,
			ownerDocument: { getElementById: () => null }
		} as unknown as HTMLElement;
		scrollToFragment(el, '#missing');
		expect(el.scrollTop).toBe(0);
	});
});
