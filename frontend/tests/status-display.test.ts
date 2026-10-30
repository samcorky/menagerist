import { describe, expect, it } from 'vitest';
import contract from '$shared/contracts/status-checks.json';
import { formatObservedValue } from '$lib/status';
import {
	FALLBACK_GROUP_ICON,
	FALLBACK_METRIC_ICON,
	formatGroup,
	formatLabel,
	groupIconName,
	metricIconName
} from '$lib/status-display';

/**
 * Every readiness check the backend can report comes from the shared contract, which a
 * backend test checks against the real checks. A new backend check therefore lands here
 * as a failing test until the page can label it, give it an icon and format its value.
 * `*` stands for the storage area name the backend fills in.
 */
const KNOWN_CHECKS: ReadonlyArray<{ key: string; unit: string; sample: number | string }> =
	contract.checks;

/** Units whose value is shown exactly as sent, on purpose. */
const PLAIN_UNITS = new Set(contract.plain_units);

/** Every state string the backend sends with the `state` unit. */
const STATES: readonly string[] = contract.states;

const parts = (key: string) => {
	const [group, metric] = key.replace('*', 'media').split(':');
	return { group, metric };
};

describe('every known check can be shown', () => {
	it.each(KNOWN_CHECKS)('$key has a readable label', ({ key }) => {
		const label = formatLabel(parts(key).metric);
		expect(label).toMatch(/^[A-Z][a-z]+( [A-Z][A-Za-z]*)* ?$|^CORS /);
	});

	it.each(KNOWN_CHECKS)('$key has its own metric icon', ({ key }) => {
		expect(metricIconName(parts(key).metric)).not.toBe(FALLBACK_METRIC_ICON);
	});

	it.each([...new Set(KNOWN_CHECKS.map(({ key }) => parts(key).group))])(
		'the %s group has its own icon and a title',
		(group) => {
			expect(groupIconName(group)).not.toBe(FALLBACK_GROUP_ICON);
			expect(formatGroup(group)).toMatch(/^[A-Z]/);
		}
	);

	it.each(KNOWN_CHECKS.filter(({ unit }) => !PLAIN_UNITS.has(unit)))(
		'$key ($unit) formats its value instead of echoing it',
		({ unit, sample }) => {
			const shown = formatObservedValue(sample, unit);
			expect(shown).not.toBe(String(sample));
			expect(shown).not.toMatch(/^(undefined|null|NaN)/);
		}
	);

	it.each(KNOWN_CHECKS.filter(({ unit }) => PLAIN_UNITS.has(unit)))(
		'$key ($unit) is shown as sent',
		({ unit, sample }) => {
			expect(formatObservedValue(sample, unit)).toBe(String(sample));
		}
	);

	it.each(STATES)('the state "%s" has wording', (state) => {
		const shown = formatObservedValue(state, 'state');
		expect(shown).not.toBe(state);
		expect(shown).toMatch(/^[A-Z]/);
	});

	it.each(KNOWN_CHECKS)('$key says "Unknown" when its check failed', ({ unit }) => {
		// A failed check reports the word `unknown` in the check's own unit.
		expect(formatObservedValue('unknown', unit)).toBe('Unknown');
	});
});

describe('the lists stay honest', () => {
	it('has no repeated check key', () => {
		const keys = KNOWN_CHECKS.map(({ key }) => key);
		expect(new Set(keys).size).toBe(keys.length);
	});

	it('gives an unrecognised check the fallback icon, not a wrong one', () => {
		expect(metricIconName('somethingNew')).toBe(FALLBACK_METRIC_ICON);
		expect(groupIconName('somethingNew')).toBe(FALLBACK_GROUP_ICON);
	});
});
