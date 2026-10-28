import type { Component } from 'svelte';
import type { JsonSchemaProperty } from '$lib/json-schema';
import { readPropMeta } from '$lib/prop-meta';

/**
 * What any screen needs to show and edit a value of one kind: how to recognise its property
 * shape, a label, and the widgets and formatters. The schema editor layers its own half on top
 * (see `FieldTypeDescriptor` in `registry.ts`); a kind with no editor half, such as a setting's
 * cron schedule, is registered here alone.
 */
export type FieldCore = {
	kind: string;
	/** Human-readable label shown in the kind dropdown. */
	label: string;
	/** Whether a property has this kind's shape. The only place a property is matched. */
	matches: (prop: JsonSchemaProperty) => boolean;
	/**
	 * Match strength for a property with no explicit `kind` (API-authored). Higher wins;
	 * `0` means "does not match". When absent, a match defaults to rank 1. Only needed once two
	 * kinds can match the same shape; ties fall back to registration order. A kind that must only
	 * be chosen by an explicit `kind` returns 0.
	 */
	rank?: (prop: JsonSchemaProperty) => number;
	/**
	 * Friendly wording for a failed validation keyword (for example a `pattern` written by this
	 * type), or null to fall back to the validator's own message. Used for client and server errors.
	 */
	formatError?: (keyword: string, value: unknown) => string | null;
	/** Plain text for a highlighted value; null skips it. Defaults to `String(value)`. */
	formatSummary?: (value: unknown, prop: JsonSchemaProperty) => string | null;
	/** Compact rendering of a highlighted value on a card. Falls back to `formatSummary`. */
	SummaryWidget?: Component<{ value: unknown; prop: JsonSchemaProperty; size: 'sm' | 'md' }>;
	/** Widget rendered for data entry. */
	InputWidget: Component<{
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	}>;
	/** Optional widget for read-mode display. Falls back to String(value) when absent. */
	ViewWidget?: Component<{ value: unknown; prop: JsonSchemaProperty }>;
};

const cores = new Map<string, FieldCore>();

export function registerCore(c: FieldCore): void {
	cores.set(c.kind, c);
}

export function getCore(kind: string): FieldCore | undefined {
	return cores.get(kind);
}

export function allCores(): FieldCore[] {
	return [...cores.values()];
}

/**
 * Pick the kind for a property from `candidates`. An explicit `kind` in the property metadata is
 * a direct lookup (and must still match the property's shape); otherwise the highest-ranked
 * candidate that matches wins, ties broken by registration order.
 */
export function pickCore<T extends FieldCore>(
	candidates: Iterable<T>,
	prop: JsonSchemaProperty
): T | undefined {
	const list = [...candidates];
	const kind = readPropMeta(prop).kind;
	if (kind !== undefined) {
		const found = list.find((c) => c.kind === kind);
		return found?.matches(prop) ? found : undefined;
	}
	let best: T | undefined;
	let bestRank = 0;
	for (const c of list) {
		if (!c.matches(prop)) continue;
		const rank = c.rank ? c.rank(prop) : 1;
		if (rank > bestRank) {
			bestRank = rank;
			best = c;
		}
	}
	return best;
}

/** Find the core for a property; see `pickCore`. */
export function coreForProp(prop: JsonSchemaProperty): FieldCore | undefined {
	return pickCore(cores.values(), prop);
}

/** Remove all core registrations - for use in tests only. */
export function _clearCores(): void {
	cores.clear();
}
