import { describe, expect, it } from 'vitest';
import { selectionSummary, visibleCheckState } from '../src/lib/selection-summary';

describe('selectionSummary', () => {
	it('counts the selection', () => {
		expect(selectionSummary(3, 0, 200)).toBe('3 selected');
	});

	it('says how many selected items the current view hides', () => {
		expect(selectionSummary(3, 2, 200)).toBe('3 selected, 2 not shown by this search');
	});

	it('names the limit when it is reached', () => {
		expect(selectionSummary(200, 0, 200)).toBe('200 selected, the most one action takes');
	});
});

describe('visibleCheckState', () => {
	it('is unchecked when none of the rows in view is selected', () => {
		expect(visibleCheckState(0, 5)).toBe('unchecked');
		expect(visibleCheckState(0, 0)).toBe('unchecked');
	});

	it('is indeterminate when some are', () => {
		expect(visibleCheckState(2, 5)).toBe('indeterminate');
	});

	it('is checked when all are', () => {
		expect(visibleCheckState(5, 5)).toBe('checked');
	});
});
