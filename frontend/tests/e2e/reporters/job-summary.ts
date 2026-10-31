import { appendFileSync } from 'node:fs';
import { basename } from 'node:path';
import type { FullResult, Reporter, Suite, TestCase } from '@playwright/test/reporter';

/**
 * Appends a Markdown summary of the run to the GitHub Actions job summary: counts, then the
 * tests that failed or only passed on a retry. CI runs it on the merged report of every shard.
 */
export default class JobSummaryReporter implements Reporter {
	private suite: Suite | undefined;

	onBegin(_config: unknown, suite: Suite) {
		this.suite = suite;
	}

	onEnd(result: FullResult) {
		const path = process.env.GITHUB_STEP_SUMMARY;
		if (!path || !this.suite) return;
		appendFileSync(path, summarise(this.suite.allTests(), result.duration));
	}

	printsToStdio() {
		return false;
	}
}

const label = (test: TestCase) => {
	const project = test.parent.project()?.name;
	const where = `${basename(test.location.file)}:${test.location.line}`;
	return `\`${project}\` ${test.titlePath().slice(3).join(' › ')} (${where})`;
};

export function summarise(tests: TestCase[], durationMs: number): string {
	const count = (outcome: ReturnType<TestCase['outcome']>) =>
		tests.filter((test) => test.outcome() === outcome);
	const failed = count('unexpected');
	const flaky = count('flaky');
	const lines = [
		'### End-to-end tests',
		'',
		'| Passed | Failed | Flaky | Skipped | Time |',
		'| ---: | ---: | ---: | ---: | ---: |',
		`| ${count('expected').length} | ${failed.length} | ${flaky.length} | ${count('skipped').length} | ${(durationMs / 60_000).toFixed(1)} min |`,
		''
	];
	if (failed.length > 0)
		lines.push('**Failed**', '', ...failed.map((test) => `- ${label(test)}`), '');
	if (flaky.length > 0) {
		lines.push('**Passed only on a retry**', '', ...flaky.map((test) => `- ${label(test)}`), '');
	}
	return lines.join('\n') + '\n';
}
