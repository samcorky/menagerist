const ordered = ['=', '!=', '>', '>=', '<', '<=', 'between', 'empty', 'not_empty'] as const;
const text = ['=', '!=', '~', 'in', 'not_in', 'empty', 'not_empty'] as const;

/** Keep in step with shared/contracts/query-operators.json (a test enforces it). */
export const KIND_OPERATORS: Record<string, readonly string[]> = {
	text,
	url: text,
	email: text,
	phone: text,
	longtext: ['~', 'empty', 'not_empty'],
	number: ordered,
	duration: ordered,
	rating: ordered,
	money: ordered,
	date: ordered,
	partialdate: ordered,
	boolean: ['=', '!='],
	choice: ['=', '!=', 'in', 'not_in', 'empty', 'not_empty'],
	multichoice: ['has', 'empty', 'not_empty'],
	checklist: ['incomplete', 'complete', 'empty', 'not_empty']
};

/** Operators of the description and name conditions (backend graph/domain/query.py). */
export const DESCRIPTION_OPERATORS = ['~', 'empty', 'not_empty'] as const;
export const NAME_OPERATORS = ['~', '='] as const;

export function operatorsForCondition(kind: 'description' | 'name'): readonly string[] {
	return kind === 'description' ? DESCRIPTION_OPERATORS : NAME_OPERATORS;
}

export const OPERATOR_LABELS: Record<string, string> = {
	'=': 'is',
	'!=': 'is not',
	'~': 'contains',
	'>': 'is more than',
	'>=': 'is at least',
	'<': 'is less than',
	'<=': 'is at most',
	between: 'is between',
	in: 'is one of',
	not_in: 'is not one of',
	empty: 'is empty',
	not_empty: 'is not empty',
	has: 'includes',
	incomplete: 'has unticked items',
	complete: 'is all ticked'
};

const NO_VALUE = new Set(['empty', 'not_empty', 'incomplete', 'complete']);

/** Operators whose value is a list of options. */
export const LIST_OPERATORS: ReadonlySet<string> = new Set(['in', 'not_in']);

export function operatorTakesValue(op: string): boolean {
	return !NO_VALUE.has(op);
}

export function operatorsForKind(kind: string): readonly string[] {
	return Object.hasOwn(KIND_OPERATORS, kind) ? KIND_OPERATORS[kind] : [];
}
