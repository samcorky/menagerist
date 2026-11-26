import type { ParentChangePlanResponse } from '$lib/api/client';

/** What the person must be asked before a type's parent changes, if anything. */
export type ParentChangeQuestion =
	| { kind: 'none' }
	/** A field the type and its new parent both define as different kinds: nothing can proceed. */
	| { kind: 'blocked'; fields: string[]; reason: string | null }
	/** Fields both define the same way: merge them into the parent's, or stop. */
	| { kind: 'merge'; fields: string[] }
	/** The type loses its parent: keep the parent's fields on it, or archive them. */
	| { kind: 'detach'; fields: string[]; items: number }
	/** Both: what to do with the old parent's fields, and the merge with the new one's. */
	| { kind: 'move'; fields: string[]; merge: string[]; items: number };

type Plan = Pick<
	ParentChangePlanResponse,
	'parent' | 'previous' | 'clashes' | 'conflicts' | 'kept' | 'reason' | 'items'
> &
	Partial<ParentChangePlanResponse>;

/**
 * What a previewed change of parent comes to, as the question to put to the person. Fields are
 * keys; the caller names them. No question is needed when nothing is shared and nothing is lost.
 * An item's values never change either way, so the answer is only about the type's fields.
 */
export function parentChangeQuestion(plan: Plan): ParentChangeQuestion {
	if (plan.parent === plan.previous) return { kind: 'none' };
	if (plan.conflicts.length > 0) {
		return { kind: 'blocked', fields: plan.conflicts, reason: plan.reason ?? null };
	}
	const leaving = plan.previous !== null && plan.kept.length > 0;
	if (leaving && plan.clashes.length > 0) {
		return { kind: 'move', fields: plan.kept, merge: plan.clashes, items: plan.items };
	}
	if (leaving) return { kind: 'detach', fields: plan.kept, items: plan.items };
	if (plan.clashes.length > 0) return { kind: 'merge', fields: plan.clashes };
	return { kind: 'none' };
}
