import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createLongPress } from '../src/lib/long-press';

const touch = (x = 0, y = 0) => ({ pointerType: 'touch', isPrimary: true, clientX: x, clientY: y });

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('createLongPress', () => {
	it('fires once after 500 ms and swallows the following click', () => {
		const onlongpress = vi.fn();
		const press = createLongPress(onlongpress);
		press.onpointerdown(touch());
		vi.advanceTimersByTime(499);
		expect(onlongpress).not.toHaveBeenCalled();
		vi.advanceTimersByTime(1);
		expect(onlongpress).toHaveBeenCalledTimes(1);
		press.onpointerup();
		expect(press.swallowClick()).toBe(true);
		expect(press.swallowClick()).toBe(false);
	});

	it('does not fire when released early, and the click goes through', () => {
		const onlongpress = vi.fn();
		const press = createLongPress(onlongpress);
		press.onpointerdown(touch());
		vi.advanceTimersByTime(200);
		press.onpointerup();
		vi.advanceTimersByTime(1000);
		expect(onlongpress).not.toHaveBeenCalled();
		expect(press.swallowClick()).toBe(false);
	});

	it('does not fire while the page scrolls under the finger', () => {
		const onlongpress = vi.fn();
		const press = createLongPress(onlongpress);
		press.onpointerdown(touch(0, 0));
		press.onpointermove(touch(0, 30));
		vi.advanceTimersByTime(1000);
		expect(onlongpress).not.toHaveBeenCalled();
	});

	it('ignores a mouse', () => {
		const onlongpress = vi.fn();
		const press = createLongPress(onlongpress);
		press.onpointerdown({ ...touch(), pointerType: 'mouse' });
		vi.advanceTimersByTime(1000);
		expect(onlongpress).not.toHaveBeenCalled();
	});
});
