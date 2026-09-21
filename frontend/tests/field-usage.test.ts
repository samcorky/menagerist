import { describe, it, expect } from 'vitest';
import { purgeWarning, usageLabel } from '../src/lib/field-usage';

describe('usageLabel', () => {
	it('pluralises and names items or connections', () => {
		expect(usageLabel(0, 'node')).toBe('Not used');
		expect(usageLabel(1, 'node')).toBe('Used by 1 item');
		expect(usageLabel(12, 'node')).toBe('Used by 12 items');
		expect(usageLabel(1, 'edge')).toBe('Used by 1 connection');
		expect(usageLabel(2, 'edge')).toBe('Used by 2 connections');
	});
});

describe('purgeWarning', () => {
	it('repeats the count and says it cannot be undone', () => {
		expect(purgeWarning('Director', 3, 'node')).toBe(
			'This permanently deletes “Director” from 3 items. It cannot be undone.'
		);
		expect(purgeWarning('Since', 1, 'edge')).toContain('1 connection.');
	});
});
