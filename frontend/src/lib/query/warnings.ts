import { FAR_END, type Path } from './types';

/** Where a server path points: a node in the condition tree, or a sort key. */
export type QueryTarget = { where: Path } | { sort: number };

// A warning inside a collection row names the id (`.in[n]`) or a rule of a smart collection
// it inlines (`.in[n].children[m]`, nested further the same way, even through a connection's
// `.where`); both belong to the row itself. A connection's own `.where` leads to the rows of
// its far-end filter.
const WHERE =
	/^where((?:\.children\[\d{1,4}\]|\.where)*)(?:\.in\[\d{1,4}\](?:\.(?:in|children)\[\d{1,4}\]|\.where)*)?$/;
const SORT = /^sort\[(\d{1,2})\]$/;

/** Parse a server path such as `where.children[2].children[0]` or `sort[0]`; null when unknown. */
export function parseQueryPath(path: string): QueryTarget | null {
	const sort = SORT.exec(path);
	if (sort) return { sort: Number(sort[1]) };
	const where = WHERE.exec(path);
	if (!where) return null;
	const steps = where[1].matchAll(/\.children\[(\d+)\]|\.where/g);
	return { where: [...steps].map((m) => (m[1] === undefined ? FAR_END : Number(m[1]))) };
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
	/** The server's words for a flagged condition, by the same keys. */
	messages: Map<string, string>;
	/** True when a sort key names a field that no longer exists. */
	sort: boolean;
};

export function mapWarnings(
	warnings: { path: string; message?: string }[],
	prefix: Path = []
): WarningMarks {
	const marks: WarningMarks = { conditions: new Set(), messages: new Map(), sort: false };
	for (const { path, message } of warnings) {
		const target = parseQueryPath(path);
		if (!target) continue;
		if ('sort' in target) {
			marks.sort = true;
			continue;
		}
		const inFilter = toFilterPath(target.where, prefix);
		if (!inFilter) continue;
		marks.conditions.add(pathKey(inFilter));
		if (message && !marks.messages.has(pathKey(inFilter)))
			marks.messages.set(pathKey(inFilter), message);
	}
	return marks;
}

/** Split a 400 detail such as `where.children[1]: That value…` into its path and message. */
export function splitDetail(detail: string): { target: QueryTarget | null; message: string } {
	const match = /^([a-z_.[\]0-9]+): (.+)$/s.exec(detail);
	const target = match ? parseQueryPath(match[1]) : null;
	return target && match ? { target, message: match[2] } : { target: null, message: detail };
}
