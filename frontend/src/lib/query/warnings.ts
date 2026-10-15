import type { Path } from './types';

/** Where a server path points: a node in the condition tree, or a sort key. */
export type QueryTarget = { where: Path } | { sort: number };

const WHERE = /^where((?:\.children\[\d{1,4}\])*)$/;
const SORT = /^sort\[(\d{1,2})\]$/;

/** Parse a server path such as `where.children[2].children[0]` or `sort[0]`; null when unknown. */
export function parseQueryPath(path: string): QueryTarget | null {
	const sort = SORT.exec(path);
	if (sort) return { sort: Number(sort[1]) };
	const where = WHERE.exec(path);
	if (!where) return null;
	return { where: [...where[1].matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1])) };
}

export function pathKey(path: Path): string {
	return path.join('.');
}

/**
 * Translate a path in the tree sent to the server back to the filter's own tree.
 * `prefix` is where the filter sits in the sent tree (see `combinePrefix`); null when
 * the path points outside it.
 */
export function toFilterPath(path: Path, prefix: Path): Path | null {
	if (path.length <= prefix.length) return null;
	return prefix.every((index, i) => path[i] === index) ? path.slice(prefix.length) : null;
}

export type WarningMarks = {
	/** Filter paths (as `pathKey`) of conditions the server could not match. */
	conditions: Set<string>;
	/** True when a sort key names a field that no longer exists. */
	sort: boolean;
};

export function mapWarnings(warnings: { path: string }[], prefix: Path = []): WarningMarks {
	const marks: WarningMarks = { conditions: new Set(), sort: false };
	for (const { path } of warnings) {
		const target = parseQueryPath(path);
		if (!target) continue;
		if ('sort' in target) {
			marks.sort = true;
			continue;
		}
		const inFilter = toFilterPath(target.where, prefix);
		if (inFilter) marks.conditions.add(pathKey(inFilter));
	}
	return marks;
}

/** Split a 400 detail such as `where.children[1]: That value…` into its path and message. */
export function splitDetail(detail: string): { target: QueryTarget | null; message: string } {
	const match = /^([a-z_.[\]0-9]+): (.+)$/s.exec(detail);
	const target = match ? parseQueryPath(match[1]) : null;
	return target && match ? { target, message: match[2] } : { target: null, message: detail };
}
