import { describe, expect, it } from 'vitest';
import type { TestCase } from '@playwright/test/reporter';
import { summarise } from './e2e/reporters/job-summary';

function fakeTest(
	outcome: ReturnType<TestCase['outcome']>,
	title: string,
	project = 'chromium'
): TestCase {
	return {
		outcome: () => outcome,
		parent: { project: () => ({ name: project }) },
		location: { file: '/work/frontend/tests/e2e/status.spec.ts', line: 12 },
		titlePath: () => ['', project, 'status.spec.ts', title]
	} as unknown as TestCase;
}

describe('e2e job summary', () => {
	it('counts each outcome and the time taken', () => {
		const text = summarise(
			[
				fakeTest('expected', 'a'),
				fakeTest('expected', 'b'),
				fakeTest('unexpected', 'c'),
				fakeTest('flaky', 'd'),
				fakeTest('skipped', 'e')
			],
			150_000
		);

		expect(text).toContain('| 2 | 1 | 1 | 1 | 2.5 min |');
	});

	it('lists failed and retried tests with their project and place', () => {
		const text = summarise(
			[fakeTest('unexpected', 'shows the checks', 'mobile'), fakeTest('flaky', 'wraps a name')],
			1000
		);

		expect(text).toContain('**Failed**');
		expect(text).toContain('- `mobile` shows the checks (status.spec.ts:12)');
		expect(text).toContain('**Passed only on a retry**');
		expect(text).toContain('- `chromium` wraps a name (status.spec.ts:12)');
	});

	it('leaves out the lists when everything passed', () => {
		const text = summarise([fakeTest('expected', 'a')], 1000);

		expect(text).not.toContain('**Failed**');
		expect(text).not.toContain('**Passed only on a retry**');
	});
});
