import {
	FAR_END,
	isGroup,
	MAX_TEXT_LENGTH,
	type Condition,
	type Group,
	type GroupOp,
	type Node,
	type Path,
	type Query
} from './types';

/*
 * All helpers are immutable and address nodes by Path (child indexes from the
 * root). A path that does not exist returns the query unchanged (same object).
 * addGroup is the only operation that does not prune: it leaves the new empty
 * group so the builder can show it. Every other edit prunes groups left empty,
 * and an empty root becomes `where: null`. A `not` group holds one child, so
 * adding to a `not` that already has one is a no-op.
 */

export function emptyQuery(): Query {
	return { v: 1, where: null, sort: [] };
}

function isIndex(value: number): boolean {
	return Number.isInteger(value) && value >= 0;
}

/** Apply `edit` to the group at `path`; null when the path is not a group. */
function editGroup(node: Node, path: Path, edit: (target: Group) => Group | null): Node | null {
	if (path.length === 0) return isGroup(node) ? edit(node) : null;
	const [index, ...rest] = path;
	if (isGroup(node)) {
		const child = isIndex(index) ? node.children[index] : undefined;
		if (!child) return null;
		const next = editGroup(child, rest, edit);
		if (!next) return null;
		const children = node.children.slice();
		children[index] = next;
		return { op: node.op, children };
	}
	if (node.kind !== 'connection' || index !== FAR_END || !node.where) return null;
	const where = editGroup(node.where, rest, edit);
	return where && isGroup(where) ? { ...node, where } : null;
}

/** A connection with its far-end filter pruned; the filter goes when nothing is left. */
function pruneCondition(condition: Condition): Condition {
	if (condition.kind !== 'connection' || !condition.where) return condition;
	const where = prune(condition.where);
	if (where) return { ...condition, where };
	const { where: _gone, ...bare } = condition;
	return bare;
}

/** Drop groups left with no children; null when nothing remains. */
function prune(group: Group): Group | null {
	const children: Node[] = [];
	for (const child of group.children) {
		if (!isGroup(child)) children.push(pruneCondition(child));
		else {
			const pruned = prune(child);
			if (pruned) children.push(pruned);
		}
	}
	return children.length ? { op: group.op, children } : null;
}

const rootOf = (query: Query): Group => query.where ?? { op: 'and', children: [] };

function append(query: Query, groupPath: Path, node: Node, keepEmpty: boolean): Query {
	const edited = editGroup(rootOf(query), groupPath, (target) =>
		target.op === 'not' && target.children.length > 0
			? null
			: { op: target.op, children: [...target.children, node] }
	);
	if (!edited || !isGroup(edited)) return query;
	return { ...query, where: keepEmpty ? edited : prune(edited) };
}

export function addCondition(query: Query, groupPath: Path, condition: Condition): Query {
	return append(query, groupPath, condition, false);
}

export function addGroup(query: Query, groupPath: Path, op: GroupOp): Query {
	return append(query, groupPath, { op, children: [] }, true);
}

/**
 * Replace (or, with null, remove) the node at `path` inside `node`; undefined when the path
 * leads nowhere. A far-end filter is replaced by a group and removed by null.
 */
function changeIn(node: Node, path: Path, next: Node | null): Node | undefined {
	const [index, ...rest] = path;
	if (isGroup(node)) {
		if (!isIndex(index) || index >= node.children.length) return undefined;
		const children = node.children.slice();
		if (rest.length === 0) {
			if (next === null) children.splice(index, 1);
			else children[index] = next;
		} else {
			const inner = changeIn(children[index], rest, next);
			if (!inner) return undefined;
			children[index] = inner;
		}
		return { op: node.op, children };
	}
	if (node.kind !== 'connection' || index !== FAR_END || !node.where) return undefined;
	if (rest.length === 0) {
		const { where: _old, ...bare } = node;
		return next !== null && isGroup(next) ? { ...bare, where: next } : bare;
	}
	const inner = changeIn(node.where, rest, next);
	return inner && isGroup(inner) ? { ...node, where: inner } : undefined;
}

/** Edit the child at `path` (replace with `node`, or remove when `node` is null). */
function changeAt(query: Query, path: Path, node: Node | null): Query {
	if (path.length === 0) {
		if (node === null) return { ...query, where: null };
		return isGroup(node) ? { ...query, where: prune(node) } : query;
	}
	if (!query.where) return query;
	const edited = changeIn(query.where, path, node);
	return edited && isGroup(edited) ? { ...query, where: prune(edited) } : query;
}

export function removeAt(query: Query, path: Path): Query {
	return changeAt(query, path, null);
}

export function replaceAt(query: Query, path: Path, node: Node): Query {
	return changeAt(query, path, node);
}

/** Every condition counts, a connection's far-end filter ones included (the server's limit). */
export function countConditions(query: Query): number {
	const count = (g: Group): number =>
		g.children.reduce(
			(n, c) =>
				n + (isGroup(c) ? count(c) : c.kind === 'connection' && c.where ? 1 + count(c.where) : 1),
			0
		);
	return query.where ? count(query.where) : 0;
}

export function isFilterEmpty(query: Query): boolean {
	return countConditions(query) === 0;
}

/**
 * AND the page's own type, text and favourite controls into the advanced filter.
 * Text over the server's 200-character limit is left out of the tree (never
 * truncated); the caller should send it another way. An `and` filter is merged
 * flat so combining never adds a nesting level.
 */
export type PageBasics = { type?: string | null; q?: string; favourite?: boolean };

/** Counted in characters (code points), as the server counts them, not UTF-16 units. */
function fitsTextLimit(text: string): boolean {
	return [...text].length <= MAX_TEXT_LENGTH;
}

/** The conditions `combine` adds for the page's own controls (the one inclusion rule). */
export function pageConditions(basics: PageBasics): Condition[] {
	const extra: Condition[] = [];
	if (basics.type && fitsTextLimit(basics.type)) extra.push({ kind: 'type', in: [basics.type] });
	const q = basics.q?.trim();
	if (q && fitsTextLimit(q)) extra.push({ kind: 'text', q });
	if (basics.favourite) extra.push({ kind: 'favourite', value: true });
	return extra;
}

/** True when the search text is too long to add to a filter, so `combine` leaves it out. */
export function searchTextTooLong(q: string | undefined): boolean {
	return !fitsTextLimit(q?.trim() ?? '');
}

export function combine(query: Query, basics: PageBasics): Query {
	const extra = pageConditions(basics);
	const filter = prune(rootOf(query));
	if (extra.length === 0) return { ...query, where: filter };
	const head: Node[] = !filter ? [] : filter.op === 'and' ? filter.children : [filter];
	return { ...query, where: { op: 'and', children: [...head, ...extra] } };
}
