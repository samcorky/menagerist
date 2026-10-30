import { describe, expect, it } from 'vitest';
import { lockPageScroll } from '$lib/scroll-lock';

function fakeRoot() {
	const attributes = new Set<string>();
	return {
		setAttribute: (name: string) => void attributes.add(name),
		removeAttribute: (name: string) => void attributes.delete(name),
		locked: () => attributes.has('data-scroll-locked')
	};
}

describe('lockPageScroll', () => {
	it('locks while held and unlocks on release', () => {
		const root = fakeRoot();
		const release = lockPageScroll(root);
		expect(root.locked()).toBe(true);
		release();
		expect(root.locked()).toBe(false);
	});

	it('stays locked until every holder has released', () => {
		const root = fakeRoot();
		const first = lockPageScroll(root);
		const second = lockPageScroll(root);
		first();
		expect(root.locked()).toBe(true);
		second();
		expect(root.locked()).toBe(false);
	});

	it('ignores a second release from the same holder', () => {
		const root = fakeRoot();
		const first = lockPageScroll(root);
		const second = lockPageScroll(root);
		first();
		first();
		expect(root.locked()).toBe(true);
		second();
		expect(root.locked()).toBe(false);
	});
});
