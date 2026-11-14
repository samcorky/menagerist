import { describe, expect, it } from 'vitest';
import {
	describeInstall,
	entryNote,
	groupBySection,
	sectionLabel,
	type CatalogueEntry,
	type InstallOutcome
} from '$lib/catalogue';

function entry(over: Partial<CatalogueEntry> = {}): CatalogueEntry {
	return {
		id: 'x',
		title: 'X',
		description: 'd',
		section: 'field',
		installed: false,
		present: 0,
		total: 1,
		contents: ['X'],
		...over
	};
}

function outcome(over: Partial<InstallOutcome> = {}): InstallOutcome {
	return {
		entry_id: 'x',
		presets_created: 0,
		presets_skipped: 0,
		item_types_created: 0,
		item_types_skipped: 0,
		relationship_types_created: 0,
		relationship_types_skipped: 0,
		...over
	};
}

describe('sectionLabel', () => {
	it('uses collector-facing names', () => {
		expect(sectionLabel('choice_list')).toBe('Saved lists');
		expect(sectionLabel('field')).toBe('Saved fields');
		expect(sectionLabel('field_group')).toBe('Saved field groups');
		expect(sectionLabel('starter_types')).toBe('Starter types');
	});
});

describe('groupBySection', () => {
	it('orders sections fixed and drops empty ones', () => {
		const groups = groupBySection([
			entry({ id: 'a', section: 'starter_types' }),
			entry({ id: 'b', section: 'choice_list' }),
			entry({ id: 'c', section: 'choice_list' })
		]);
		expect(groups.map((g) => g.section)).toEqual(['choice_list', 'starter_types']);
		expect(groups[0].entries.map((e) => e.id)).toEqual(['b', 'c']);
	});
});

describe('entryNote', () => {
	it('says installed, partly there, or nothing', () => {
		expect(entryNote(entry({ installed: true, present: 1 }))).toBe('Installed');
		expect(entryNote(entry({ present: 3, total: 10 }))).toBe('3 of 10 already there');
		expect(entryNote(entry())).toBeNull();
	});
});

describe('describeInstall', () => {
	it('describes what was added', () => {
		expect(describeInstall(outcome({ presets_created: 1 }))).toBe('Added 1 saved item.');
		expect(describeInstall(outcome({ presets_created: 2 }))).toBe('Added 2 saved items.');
		expect(describeInstall(outcome({ item_types_created: 5, relationship_types_created: 1 }))).toBe(
			'Added 5 item types, 1 connection type.'
		);
	});
	it('says when everything was already there', () => {
		expect(describeInstall(outcome({ presets_skipped: 1 }))).toBe('You already have this.');
	});
	it('mixes added and skipped', () => {
		expect(describeInstall(outcome({ item_types_created: 5, item_types_skipped: 1 }))).toBe(
			'Added 5 item types. Skipped 1 you already have.'
		);
	});
});
