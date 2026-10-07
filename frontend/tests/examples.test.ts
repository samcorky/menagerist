import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	describeCounts,
	describeRemoval,
	dismissExamplesBanner,
	groupKept,
	isExamplesBannerDismissed,
	reasonLabel
} from '$lib/examples';

const zero = { presets: 0, relationship_types: 0, item_types: 0, items: 0, connections: 0 };

describe('describeCounts', () => {
	it('lists non-zero parts and omits zeros', () => {
		expect(describeCounts({ ...zero, item_types: 3, items: 14 })).toBe('3 item types, 14 items');
	});
	it('uses singular for one', () => {
		expect(describeCounts({ ...zero, items: 1, connections: 2 })).toBe('1 item, 2 connections');
	});
	it('is empty for all zeros', () => {
		expect(describeCounts(zero)).toBe('');
	});
});

describe('reasonLabel', () => {
	it('maps known reasons', () => {
		expect(reasonLabel('edited')).toBe('you edited them');
		expect(reasonLabel('has your connections or files')).toBe(
			'they have your connections or files'
		);
		expect(reasonLabel('still in use')).toBe('they are still in use');
	});
	it('falls back for unknown reasons', () => {
		expect(reasonLabel('mystery')).toBe('they are no longer just examples');
	});
});

describe('groupKept', () => {
	it('groups by reason in first-seen order', () => {
		const kept = ['edited', 'still in use', 'edited'].map((reason) => ({
			kind: 'item',
			label: 'x',
			reason
		}));
		expect(groupKept(kept)).toEqual([
			{ reason: 'edited', count: 2 },
			{ reason: 'still in use', count: 1 }
		]);
	});
});

describe('describeRemoval', () => {
	it('gives one sentence when nothing was kept', () => {
		expect(describeRemoval({ pack_id: 'music', removed: { ...zero, items: 17 }, kept: [] })).toBe(
			'Removed 17 items.'
		);
	});
	it('names what was kept and why', () => {
		const kept = [
			{ kind: 'item', label: 'a', reason: 'edited' },
			{ kind: 'item', label: 'b', reason: 'edited' },
			{ kind: 'item', label: 'c', reason: 'still in use' }
		];
		expect(describeRemoval({ pack_id: 'music', removed: { ...zero, items: 5 }, kept })).toBe(
			'Removed 5 items. 2 items were kept because you edited them; 1 item was kept because they are still in use.'
		);
	});
	it('handles nothing removed', () => {
		expect(describeRemoval({ pack_id: 'music', removed: zero, kept: [] })).toBe(
			'Nothing needed removing.'
		);
	});
});

describe('examples banner dismissal', () => {
	afterEach(() => vi.unstubAllGlobals());
	it('starts not dismissed and remembers dismissal', () => {
		const store = new Map<string, string>();
		vi.stubGlobal('localStorage', {
			getItem: (key: string) => store.get(key) ?? null,
			setItem: (key: string, value: string) => store.set(key, value)
		});
		expect(isExamplesBannerDismissed()).toBe(false);
		dismissExamplesBanner();
		expect(isExamplesBannerDismissed()).toBe(true);
	});
	it('does not throw when storage throws', () => {
		vi.stubGlobal('localStorage', {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		});
		expect(isExamplesBannerDismissed()).toBe(false);
		expect(() => dismissExamplesBanner()).not.toThrow();
	});
});
