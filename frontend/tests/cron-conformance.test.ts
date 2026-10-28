import { describe, it, expect } from 'vitest';
import contract from '$shared/contracts/cron-conformance.json';
import { explainCron } from '../src/lib/field-types/cron/explain';
import { buildCron, parseCron, type Sentence } from '../src/lib/field-types/cron/builder';

// The same file is read by backend/tests/platform/test_cron_contract.py: the server decides
// what a schedule is, and the browser only explains it.

describe('cron conformance fixture', () => {
	it.each(contract.valid)('explains $expression', ({ expression, explained }) => {
		expect(explainCron(expression)).toEqual({ ok: true, text: explained });
	});

	it.each(contract.invalid)(
		'refuses to explain %j, which the server also refuses',
		(expression) => {
			expect(explainCron(expression).ok).toBe(false);
		}
	);

	// Known limit: the browser cannot tell that these never fire or are backwards.
	it.each(contract.server_rejects_only)(
		'cannot see why the server refuses %j, so the server says',
		(expression) => {
			expect(explainCron(expression).ok).toBe(true);
		}
	);

	it.each(contract.sentences)('says $cron as a sentence and back', ({ sentence, cron }) => {
		expect(buildCron(sentence as Sentence)).toBe(cron);
		expect(parseCron(cron)).toEqual(sentence);
	});

	it.each(contract.custom)('leaves %j as a custom schedule', (expression) => {
		expect(parseCron(expression)).toBeNull();
		expect(explainCron(expression).ok).toBe(true);
	});

	it('only offers sentences the server accepts, which the backend contract test checks', () => {
		for (const { cron } of contract.sentences) expect(explainCron(cron).ok).toBe(true);
	});
});
