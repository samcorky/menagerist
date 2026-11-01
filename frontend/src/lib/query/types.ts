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
	| DescriptionCondition
	| NameCondition
	| MediaCondition
	| CollectionCondition
	| ConnectionCondition
	| FieldCondition;

/** `~` needs a value (1 to 200 characters); `empty` and `not_empty` take none. */
export type DescriptionCondition = {
	kind: 'description';
	op: '~' | 'empty' | 'not_empty';
	value?: string;
};
/** Both operators need a value (1 to 200 characters). */
export type NameCondition = { kind: 'name'; op: '~' | '='; value: string };
/** Whether the item has media; `type` narrows it to images or documents. */
export type MediaCondition = { kind: 'media'; mode: 'has' | 'none'; type?: MediaType };
/** In (`any`) or in none of (`none`) 1 to 50 collections, by id. */
export type CollectionCondition = { kind: 'collection'; mode: 'any' | 'none'; in: string[] };
/**
 * Has (`exists`), lacks (`none`) or is linked to a given item (`to`). `direction` is `any`
 * when absent; `out` means this item is the source. `exists` and `none` take no `item`,
 * `to` needs one and takes no `where`. `where` filters the linked item and cannot hold
 * another connection.
 */
export type ConnectionCondition = {
	kind: 'connection';
	mode: 'exists' | 'none' | 'to';
	relationship?: string;
	direction?: 'out' | 'in' | 'any';
	item?: string;
	where?: Group;
};
export type MediaType = 'image' | 'document';

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

/**
 * Child indexes from the root group down. `[]` is the root. `FAR_END` steps from a
 * connection condition into its `where` group (the filter on the linked item).
 */
export type Path = number[];
export const FAR_END = -1;

/** Limits the server enforces (backend graph/domain/query.py). */
export const MAX_DEPTH = 4;
export const MAX_CONDITIONS = 50;
export const MAX_SORT_KEYS = 3;
export const MAX_TEXT_LENGTH = 200;
export const MAX_LIST_LENGTH = 50;
/** Collections one condition may name (the server's list limit). */
export const MAX_COLLECTION_IDS = MAX_LIST_LENGTH;

export function isGroup(node: Node): node is Group {
	return !('kind' in node);
}
