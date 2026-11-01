import { describe, it, expect } from 'vitest';
import { normalise, orderedKeys, isSectionItem } from '../src/lib/layout';

const props = (keys: string[]) => Object.fromEntries(keys.map((k) => [k, {}]));

describe('normalise', () => {
	it('returns flat list in schema key order when no layout given', () => {
		const result = normalise(undefined, props(['year', 'director', 'genre']));
		expect(orderedKeys(result)).toEqual(['year', 'director', 'genre']);
	});

	it('returns flat list in schema key order when layout is empty', () => {
		const result = normalise([], props(['year', 'director']));
		expect(orderedKeys(result)).toEqual(['year', 'director']);
	});

	it('respects the order defined in the layout', () => {
		const layout = [{ key: 'genre' }, { key: 'director' }, { key: 'year' }];
		const result = normalise(layout, props(['year', 'director', 'genre']));
		expect(orderedKeys(result)).toEqual(['genre', 'director', 'year']);
	});

	it('drops dangling keys that no longer exist in properties', () => {
		const layout = [{ key: 'year' }, { key: 'removed' }, { key: 'director' }];
		const result = normalise(layout, props(['year', 'director']));
		expect(orderedKeys(result)).toEqual(['year', 'director']);
	});

	it('appends unplaced keys (added after layout was saved) at the end', () => {
		const layout = [{ key: 'year' }];
		const result = normalise(layout, props(['year', 'director', 'genre']));
		expect(orderedKeys(result)).toEqual(['year', 'director', 'genre']);
	});

	it('does not duplicate keys that appear twice in a malformed layout', () => {
		const layout = [{ key: 'year' }, { key: 'year' }, { key: 'director' }];
		const result = normalise(layout, props(['year', 'director']));
		expect(orderedKeys(result)).toEqual(['year', 'director']);
	});

	it('flattens section items into the ordered key list', () => {
		const layout = [
			{ key: 'title' },
			{ id: 's1', section: 'Details', items: [{ key: 'year' }, { key: 'director' }] }
		];
		const result = normalise(layout, props(['title', 'year', 'director']));
		expect(orderedKeys(result)).toEqual(['title', 'year', 'director']);
	});

	it('drops empty sections after dangling-key filtering', () => {
		const layout = [{ id: 's1', section: 'Old', items: [{ key: 'removed' }] }, { key: 'year' }];
		const result = normalise(layout, props(['year']));
		expect(result.every((item) => !isSectionItem(item))).toBe(true);
		expect(orderedKeys(result)).toEqual(['year']);
	});
});

describe('orderedKeys', () => {
	it('extracts keys from flat items', () => {
		expect(orderedKeys([{ key: 'a' }, { key: 'b' }])).toEqual(['a', 'b']);
	});

	it('flattens section items', () => {
		expect(
			orderedKeys([{ key: 'a' }, { id: 's1', section: 'S', items: [{ key: 'b' }, { key: 'c' }] }])
		).toEqual(['a', 'b', 'c']);
	});
});

describe('normalise with archived properties', () => {
	const archivedProps = {
		year: {},
		old: { 'x-menagerist': { archived: true } },
		director: {}
	};

	it('leaves archived properties out of a layout-less schema', () => {
		expect(orderedKeys(normalise(undefined, archivedProps))).toEqual(['year', 'director']);
	});

	it('drops an archived key even when the saved layout still lists it', () => {
		const layout = [{ key: 'old' }, { key: 'year' }];
		expect(orderedKeys(normalise(layout, archivedProps))).toEqual(['year', 'director']);
	});

	it('drops archived keys from inside sections', () => {
		const layout = [{ id: 's', section: 'S', items: [{ key: 'old' }, { key: 'year' }] }];
		expect(orderedKeys(normalise(layout, archivedProps))).toEqual(['year', 'director']);
	});
});
