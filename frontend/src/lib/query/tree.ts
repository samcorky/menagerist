import {
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
function editGroup(group: Group, path: Path, edit: (target: Group) => Group | null): Group | null {
	if (path.length === 0) return edit(group);
	const [index, ...rest] = path;
	const child = isIndex(index) ? group.children[index] : undefined;
	if (!child || !isGroup(child)) return null;
	const next = editGroup(child, rest, edit);
	if (!next) return null;
	const children = group.children.slice();
	children[index] = next;
	return { op: group.op, children };
}

/** Drop groups left with no children; null when nothing remains. */
function prune(group: Group): Group | null {
	const children: Node[] = [];
	for (const child of group.children) {
		if (!isGroup(child)) children.push(child);
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
	if (!edited) return query;
	return { ...query, where: keepEmpty ? edited : prune(edited) };
}

export function addCondition(query: Query, groupPath: Path, condition: Condition): Query {
	return append(query, groupPath, condition, false);
}

export function addGroup(query: Query, groupPath: Path, op: GroupOp): Query {
	return append(query, groupPath, { op, children: [] }, true);
}

/** Edit the child at `path` (replace with `node`, or remove when `node` is null). */
function changeAt(query: Query, path: Path, node: Node | null): Query {
	if (path.length === 0) {
		if (node === null) return { ...query, where: null };
		return isGroup(node) ? { ...query, where: prune(node) } : query;
	}
	const index = path[path.length - 1];
	if (!query.where || !isIndex(index)) return query;
	const edited = editGroup(query.where, path.slice(0, -1), (target) => {
		if (index >= target.children.length) return null;
		const children = target.children.slice();
		if (node === null) children.splice(index, 1);
		else children[index] = node;
		return { op: target.op, children };
	});
	return edited ? { ...query, where: prune(edited) } : query;
}

export function removeAt(query: Query, path: Path): Query {
	return changeAt(query, path, null);
}

export function replaceAt(query: Query, path: Path, node: Node): Query {
	return changeAt(query, path, node);
}

export function countConditions(query: Query): number {
	const count = (g: Group): number =>
		g.children.reduce((n, c) => n + (isGroup(c) ? count(c) : 1), 0);
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
export function combine(
	query: Query,
	basics: { type?: string | null; q?: string; favourite?: boolean }
): Query {
	const extra: Condition[] = [];
	if (basics.type && basics.type.length <= MAX_TEXT_LENGTH)
		extra.push({ kind: 'type', in: [basics.type] });
	const q = basics.q?.trim();
	if (q && q.length <= MAX_TEXT_LENGTH) extra.push({ kind: 'text', q });
	if (basics.favourite) extra.push({ kind: 'favourite', value: true });
	const filter = prune(rootOf(query));
	if (extra.length === 0) return { ...query, where: filter };
	const head: Node[] = !filter ? [] : filter.op === 'and' ? filter.children : [filter];
	return { ...query, where: { op: 'and', children: [...head, ...extra] } };
}
