import { countConditions } from './tree';
import {
	isGroup,
	MAX_CONDITIONS,
	MAX_DEPTH,
	MAX_SORT_KEYS,
	MAX_TEXT_LENGTH,
	type Group,
	type Path,
	type Query
} from './types';

export { MAX_CONDITIONS, MAX_DEPTH, MAX_SORT_KEYS, MAX_TEXT_LENGTH };

/** Depth of the group at `groupPath`; the root group is 1. */
export function groupDepthAt(groupPath: Path): number {
	return groupPath.length + 1;
}

function treeDepth(group: Group): number {
	let deepest = 0;
	for (const child of group.children)
		if (isGroup(child)) deepest = Math.max(deepest, treeDepth(child));
	return deepest + 1;
}

export function canAddCondition(query: Query): boolean {
	return countConditions(query) < MAX_CONDITIONS;
}

/** False when a group added inside `groupPath` would sit deeper than the server allows. */
export function canAddGroup(query: Query, groupPath: Path): boolean {
	return groupDepthAt(groupPath) + 1 <= MAX_DEPTH;
}

export function fitsLimits(query: Query): boolean {
	return (
		countConditions(query) <= MAX_CONDITIONS &&
		(!query.where || treeDepth(query.where) <= MAX_DEPTH)
	);
}
