import type { PlanBlockerResponse, PlannedEntityResponse } from '$lib/api/client';

/** What an import or install would do, as every preview route returns it. */
export interface ImportPlan {
	ready: boolean;
	blockers: PlanBlockerResponse[];
	entities: PlannedEntityResponse[];
}

/** Kinds in the order a person thinks of them, with collector-facing names (design §24). */
const KINDS: [kind: string, one: string, many: string][] = [
	['preset', 'saved item', 'saved items'],
	['item_type', 'item type', 'item types'],
	['relationship_type', 'connection type', 'connection types'],
	['item', 'item', 'items'],
	['connection', 'connection', 'connections'],
	['collection', 'collection', 'collections'],
	['cover', 'cover', 'covers']
];

// Too many or too plain to list one by one; the count says enough.
const COUNT_ONLY = new Set(['connection', 'cover']);

/** How many names to list under a heading before "and N more". */
export const LISTED = 5;

export function kindName(kind: string, count: number): string {
	const found = KINDS.find(([key]) => key === kind);
	if (!found) return count === 1 ? 'thing' : 'things';
	return count === 1 ? found[1] : found[2];
}

/** "3 item types": a count with its kind's name. */
export function countOf(kind: string, count: number): string {
	return `${count} ${kindName(kind, count)}`;
}

export interface PlanGroup {
	kind: string;
	heading: string;
	/** The names to list; empty for kinds that are only counted. */
	names: string[];
	/** How many more there are than `names` shows. */
	more: number;
}

export interface PlanSummary {
	/** What would be added, by kind. */
	adding: PlanGroup[];
	/** What you already have, with why. */
	have: PlannedEntityResponse[];
	/** What is in the way. */
	conflicts: PlannedEntityResponse[];
	blockers: PlanBlockerResponse[];
	/** Whether going ahead would add anything. */
	canAdd: boolean;
}

function kindOrder(kind: string): number {
	const index = KINDS.findIndex(([key]) => key === kind);
	return index === -1 ? KINDS.length : index;
}

/** Sort a plan into what it adds, what you have, and what stops it. */
export function summarisePlan(plan: ImportPlan): PlanSummary {
	const byKind = new Map<string, PlannedEntityResponse[]>();
	for (const entity of plan.entities.filter((e) => e.action === 'create')) {
		byKind.set(entity.kind, [...(byKind.get(entity.kind) ?? []), entity]);
	}
	const adding = [...byKind]
		.sort(([a], [b]) => kindOrder(a) - kindOrder(b))
		.map(([kind, entities]) => {
			const names = COUNT_ONLY.has(kind) ? [] : entities.slice(0, LISTED).map((e) => e.label);
			return {
				kind,
				heading: countOf(kind, entities.length),
				names,
				more: COUNT_ONLY.has(kind) ? 0 : entities.length - names.length
			};
		});
	return {
		adding,
		have: plan.entities.filter((e) => e.action === 'unchanged'),
		conflicts: plan.entities.filter((e) => e.action === 'conflict'),
		blockers: plan.blockers,
		canAdd: plan.ready && adding.length > 0
	};
}
