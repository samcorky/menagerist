import { describe, expect, it } from 'vitest';

process.env.TZ = 'Europe/London';

import { automaticExample, withAutomaticExample } from '../src/lib/automatic-labels';
import type { JsonSchemaProperty } from '../src/lib/json-schema';

const at = new Date(2026, 10, 20, 14, 30);

describe('what Automatic comes to', () => {
	it('names the first day of the week for the region', () => {
		expect(automaticExample('datetime.first_day', at, 'en-GB')).toBe('Monday');
		expect(automaticExample('datetime.first_day', at, 'en-US')).toBe('Sunday');
	});

	it("shows today's date in the language's usual order", () => {
		expect(automaticExample('datetime.date_order', at, 'en-GB')).toBe('20 Nov 2026');
		expect(automaticExample('datetime.date_order', at, 'en-US')).toBe('Nov 20, 2026');
	});

	it("shows the time on the language's usual clock", () => {
		expect(automaticExample('datetime.clock', at, 'en-GB')).toBe('14:30');
		expect(automaticExample('datetime.clock', at, 'en-US')).toMatch(/^2:30\sPM$/);
	});

	it('has nothing to say for other settings', () => {
		expect(automaticExample('datetime.time_zone', at, 'en-GB')).toBeNull();
	});

	it('relabels only the automatic option', () => {
		const prop = {
			type: 'string',
			enum: ['automatic', 'monday'],
			'x-menagerist': { labels: { automatic: 'Automatic (from your region)', monday: 'Monday' } }
		} as unknown as JsonSchemaProperty;

		const labels = (withAutomaticExample('datetime.first_day', prop) as Record<string, unknown>)[
			'x-menagerist'
		] as { labels: Record<string, string> };

		expect(labels.labels.monday).toBe('Monday');
		expect(labels.labels.automatic).toMatch(/^Automatic \(\w+day\)$/);
	});
});
