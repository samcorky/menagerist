export type Operand =
	| string
	| number
	| boolean
	| { rel: string }
	| { ref: string }
	| { value: number; currency: string };

export type Value = Operand | Operand[];

export type Condition =
	| { kind: 'text'; q: string }
	| { kind: 'type'; in: string[] }
	| { kind: 'favourite'; value: boolean }
	| { kind: 'tag'; mode: 'any' | 'all' | 'none'; tags: string[] }
	| { kind: 'date'; on: 'created' | 'updated'; op: string; value: Value }
	| FieldCondition;

/**
 * Names an item type (`type`) or, for a field an individual item carries, its kind
 * (`field_kind`): exactly one of the two. A per-item condition has no `sub_key` or `ref`.
 */
export type FieldCondition = {
	kind: 'field';
	type?: string;
	field_kind?: string;
	key: string;
	sub_key?: string;
	op: string;
	value?: Value;
};

export type GroupOp = 'and' | 'or' | 'not';
export type Group = { op: GroupOp; children: (Group | Condition)[] };
export type Node = Group | Condition;

export type SortKey = {
	by: 'name' | 'created' | 'updated' | 'field';
	dir?: 'asc' | 'desc';
	type?: string;
	key?: string;
};

export type Query = { v: 1; where: Group | null; sort: SortKey[] };

/** Child indexes from the root group down. `[]` is the root. */
export type Path = number[];

/** Limits the server enforces (backend graph/domain/query.py). */
export const MAX_DEPTH = 4;
export const MAX_CONDITIONS = 50;
export const MAX_SORT_KEYS = 3;
export const MAX_TEXT_LENGTH = 200;
export const MAX_LIST_LENGTH = 50;

export function isGroup(node: Node): node is Group {
	return !('kind' in node);
}
