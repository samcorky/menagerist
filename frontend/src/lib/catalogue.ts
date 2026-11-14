import type { CatalogueEntryResponse, EntrySection, InstallOutcomeResponse } from '$lib/api/client';

export type CatalogueEntry = CatalogueEntryResponse;
export type InstallOutcome = InstallOutcomeResponse;

const SECTIONS: [EntrySection, string][] = [
	['choice_list', 'Saved lists'],
	['field', 'Saved fields'],
	['field_group', 'Saved field groups'],
	['starter_types', 'Starter types']
];

export function sectionLabel(section: EntrySection): string {
	return SECTIONS.find(([key]) => key === section)?.[1] ?? section;
}

/** Entries grouped under their section, in a fixed order; empty sections are left out. */
export function groupBySection(
	entries: CatalogueEntry[]
): { section: EntrySection; label: string; entries: CatalogueEntry[] }[] {
	return SECTIONS.map(([section, label]) => ({
		section,
		label,
		entries: entries.filter((e) => e.section === section)
	})).filter((group) => group.entries.length > 0);
}

/** "Installed", "3 of 10 already there", or nothing when none of it is yours yet. */
export function entryNote(entry: CatalogueEntry): string | null {
	if (entry.installed) return 'Installed';
	if (entry.present > 0) return `${entry.present} of ${entry.total} already there`;
	return null;
}

function plural(n: number, one: string, many: string): string {
	return `${n} ${n === 1 ? one : many}`;
}

/** The toast text after installing: what was added, then what was skipped. */
export function describeInstall(result: InstallOutcome): string {
	const added: string[] = [];
	if (result.presets_created > 0)
		added.push(plural(result.presets_created, 'saved item', 'saved items'));
	if (result.item_types_created > 0)
		added.push(plural(result.item_types_created, 'item type', 'item types'));
	if (result.relationship_types_created > 0)
		added.push(plural(result.relationship_types_created, 'connection type', 'connection types'));
	const skipped =
		result.presets_skipped + result.item_types_skipped + result.relationship_types_skipped;
	if (added.length === 0) return 'You already have this.';
	const first = `Added ${added.join(', ')}.`;
	return skipped > 0 ? `${first.slice(0, -1)}. Skipped ${skipped} you already have.` : first;
}
