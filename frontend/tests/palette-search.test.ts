import { describe, it, expect } from 'vitest';
import {
	GROUP_CAPS,
	PAGES,
	matchRank,
	rankByName,
	matchPages,
	matchItemTypes,
	matchSettings,
	matchTasks,
	paletteLayout,
	settingPath,
	taskPath
} from '../src/lib/palette-search';
import { foldText } from '../src/lib/fold-text';

describe('GROUP_CAPS', () => {
	it('caps each group', () => {
		expect(GROUP_CAPS).toEqual({
			items: 5,
			collections: 3,
			itemTypes: 3,
			pages: 4,
			settings: 4,
			tasks: 3,
			collectionItems: 5
		});
	});
});

describe('matchRank', () => {
	it('orders exact, prefix, word prefix, other', () => {
		expect(matchRank('Film', 'film')).toBe(0);
		expect(matchRank('Filmography', 'film')).toBe(1);
		expect(matchRank('Short film', 'film')).toBe(2);
		expect(matchRank('Telefilm', 'film')).toBe(3);
	});
	it('ignores case and surrounding whitespace in the query', () => {
		expect(matchRank('FILM', '  fILm ')).toBe(0);
	});
	it('treats non-letters and digits as word breaks', () => {
		expect(matchRank('Sci-fi film', 'fi')).toBe(2);
		expect(matchRank('a_b2c', 'b2')).toBe(2);
	});
});

describe('rankByName', () => {
	it('sorts by rank and keeps input order for ties', () => {
		const rows = [
			{ n: 'Telefilm' },
			{ n: 'Film b' },
			{ n: 'Short film' },
			{ n: 'Film a' },
			{ n: 'film' }
		];
		expect(rankByName(rows, 'film', (r) => r.n).map((r) => r.n)).toEqual([
			'film',
			'Film b',
			'Film a',
			'Short film',
			'Telefilm'
		]);
	});
	it('does not mutate the input', () => {
		const rows = ['b film', 'film'];
		rankByName(rows, 'film', (r) => r);
		expect(rows).toEqual(['b film', 'film']);
	});
});

describe('PAGES', () => {
	it('lists the app pages', () => {
		expect(PAGES.map((p) => p.path)).toEqual([
			'/',
			'/items',
			'/collections',
			'/explore',
			'/settings',
			'/settings/item-types',
			'/settings/relationships',
			'/settings/saved-fields',
			'/settings/examples',
			'/status'
		]);
	});
});

describe('matchPages', () => {
	it('matches on label', () => {
		expect(matchPages('explo')).toEqual([{ label: 'Explore', path: '/explore' }]);
	});
	it('matches on keyword', () => {
		expect(matchPages('connections').map((p) => p.label)).toEqual(['Relationships']);
	});
	it('yields nothing for an empty query', () => {
		expect(matchPages('')).toEqual([]);
		expect(matchPages('   ')).toEqual([]);
	});
	it('ranks and caps results', () => {
		const result = matchPages('s');
		expect(result.length).toBeLessThanOrEqual(GROUP_CAPS.pages);
		expect(result.length).toBe(GROUP_CAPS.pages);
		expect(result[0].label).toBe('Settings');
	});
	it('treats regex characters literally', () => {
		expect(matchPages('(')).toEqual([]);
		expect(matchPages('*')).toEqual([]);
	});
});

describe('matchItemTypes', () => {
	const types = [
		{ label: 'Board game', slug: 'board-game' },
		{ label: 'Film', slug: 'film' },
		{ label: 'Short film', slug: 'short-film' },
		{ label: 'Telefilm', slug: 'tv' },
		{ label: 'Album', slug: 'album' },
		{ label: 'Movie', slug: 'film-extra' }
	];
	it('matches label or slug, ranked by label', () => {
		expect(matchItemTypes(types, 'film').map((t) => t.label)).toEqual([
			'Film',
			'Short film',
			'Telefilm'
		]);
	});
	it('matches on slug alone', () => {
		expect(matchItemTypes(types, 'extra').map((t) => t.label)).toEqual(['Movie']);
	});
	it('yields nothing for an empty query', () => {
		expect(matchItemTypes(types, ' ')).toEqual([]);
	});
	it('caps results and matches regex characters literally', () => {
		expect(matchItemTypes(types, 'm')).toHaveLength(GROUP_CAPS.itemTypes);
		expect(matchItemTypes(types, '(')).toEqual([]);
		expect(matchItemTypes(types, '.*')).toEqual([]);
	});
});

describe('accent-insensitive matching', () => {
	it('folds case and accents', () => {
		expect(foldText('Café ÉCOLE')).toBe('cafe ecole');
		expect(foldText('cafe\u0301')).toBe('cafe');
	});
	it('ranks across accents at every level', () => {
		expect(matchRank('Café', 'cafe')).toBe(0);
		expect(matchRank('Cafe', 'café')).toBe(0);
		expect(matchRank('Café noir', 'cafe')).toBe(1);
		expect(matchRank('Le café', 'CAFE')).toBe(2);
		expect(matchRank('Le café-bar', 'cafe')).toBe(2);
		expect(matchRank('Bureau', 'cafe')).toBe(3);
	});
	it('matches item types by label or slug', () => {
		const types = [
			{ label: 'Café', slug: 'cafe-x' },
			{ label: 'Other', slug: 'other' }
		];
		expect(matchItemTypes(types, 'cafe')).toEqual([types[0]]);
		expect(matchItemTypes([{ label: 'Cafe', slug: 'c' }], 'café')).toHaveLength(1);
	});
	it('matches pages by folded query', () => {
		expect(matchPages('ÎTEMS').map((p) => p.path)).toContain('/items');
	});
});

const setting = (key: string, title: string, description: string | null = null) => ({
	key,
	group: key.split('.')[0],
	title,
	description
});

describe('matchSettings', () => {
	const all = [
		setting(
			'backup.keep_last',
			'Backups to keep',
			'How many backups are kept before the oldest goes'
		),
		setting('trash.retention_days', 'Days before deleted items are removed'),
		setting('updates.check', 'Check for updates', 'Looks for a newer release')
	];
	it('matches title, description and section name, ignoring accents and case', () => {
		expect(matchSettings(all, 'KEPT').map((s) => s.key)).toEqual(['backup.keep_last']);
		expect(matchSettings(all, 'úpdates').map((s) => s.key)).toEqual(['updates.check']);
		expect(matchSettings(all, 'backups').map((s) => s.key)).toEqual(['backup.keep_last']);
	});
	it('ranks a title prefix above a description hit and honours the cap', () => {
		const rows = [setting('a.x', 'Other', 'check'), setting('a.y', 'Check it')];
		expect(matchSettings(rows, 'check').map((s) => s.key)).toEqual(['a.y', 'a.x']);
		expect(matchSettings(rows, 'check', 1)).toHaveLength(1);
		expect(matchSettings(rows, '  ')).toEqual([]);
	});
});

describe('matchTasks', () => {
	const tasks = [
		{ job_key: 'backup', title: 'Nightly backup', description: 'Copies everything' },
		{ job_key: 'purge', title: 'Empty the bin', description: 'Removes old deleted items' }
	];
	it('matches title and description', () => {
		expect(matchTasks(tasks, 'backup').map((t) => t.job_key)).toEqual(['backup']);
		expect(matchTasks(tasks, 'deleted').map((t) => t.job_key)).toEqual(['purge']);
		expect(matchTasks(tasks, 'nothing')).toEqual([]);
		expect(matchTasks(tasks, '')).toEqual([]);
	});
});

describe('result links', () => {
	it('points a setting at its section and anchor, and a task at its row', () => {
		expect(settingPath({ key: 'backup.keep_last', group: 'backup' })).toBe(
			'/admin/settings?section=backup#setting-backup.keep_last'
		);
		expect(taskPath({ job_key: 'nightly backup' })).toBe(
			'/admin/scheduled-tasks#job-nightly backup'
		);
	});
});

describe('paletteLayout', () => {
	const first = (path: string) => paletteLayout(path).order[0];
	it('keeps the usual order away from any context', () => {
		expect(paletteLayout('/').order).toEqual([
			'items',
			'collections',
			'itemTypes',
			'pages',
			'settings',
			'tasks'
		]);
		expect(paletteLayout('/').collection).toBeNull();
	});
	it('puts what the person is looking at first and keeps every group', () => {
		expect(first('/collections')).toBe('collections');
		expect(first('/settings/item-types')).toBe('itemTypes');
		expect(paletteLayout('/admin/scheduled-tasks').order.slice(0, 2)).toEqual([
			'tasks',
			'settings'
		]);
		expect(paletteLayout('/admin/settings').order.slice(0, 2)).toEqual(['settings', 'tasks']);
		expect(first('/admin')).toBe('settings');
		expect(first('/items/')).toBe('items');
		expect(paletteLayout('/admin/settings').order).toHaveLength(6);
	});
	it('leads with the collection items on a collection page', () => {
		const layout = paletteLayout('/collections/my%20films');
		expect(layout.collection).toBe('my films');
		expect(layout.order[0]).toBe('collectionItems');
		expect(layout.order).toHaveLength(7);
		expect(paletteLayout('/collections/%E0%A4%A').collection).toBe('%E0%A4%A');
	});
	it('gives only the leading group extra rows', () => {
		const { caps } = paletteLayout('/admin/settings');
		expect(caps.settings).toBe(GROUP_CAPS.settings + 3);
		expect(caps.tasks).toBe(GROUP_CAPS.tasks);
	});
});
