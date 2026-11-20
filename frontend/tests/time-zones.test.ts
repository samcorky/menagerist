import { describe, expect, it } from 'vitest';

process.env.TZ = 'Europe/London';

import { filterComboboxItems } from '../src/lib/components/ui/combobox/combobox';
import { BROWSER_ZONE, timeZoneItems, zoneLabel } from '../src/lib/field-types/timezone/time-zones';

describe('time zone choices', () => {
	const items = timeZoneItems(['Europe/London', 'America/Argentina/Buenos_Aires', 'UTC']);

	it('offers the browser zone first, by name', () => {
		expect(items[0]).toEqual({ value: BROWSER_ZONE, label: 'Match my browser (Europe/London)' });
	});

	it('groups zones by region, names them by place, and shows the offset', () => {
		expect(items.slice(1).map((i) => [i.group, i.label])).toEqual([
			['Europe', 'London'],
			['America', 'Argentina/Buenos Aires'],
			['Other', 'UTC']
		]);
		expect(items[1].selectedLabel).toBe('Europe/London');
		expect(items[3].description).toBe('GMT');
	});

	it('finds a zone by city or by region and city', () => {
		expect(filterComboboxItems(items, 'buenos').map((i) => i.value)).toEqual([
			'America/Argentina/Buenos_Aires'
		]);
		// The browser's own zone is London here, so its entry matches too.
		expect(filterComboboxItems(items, 'europe lon').map((i) => i.value)).toEqual([
			BROWSER_ZONE,
			'Europe/London'
		]);
	});

	it('finds a zone by its IANA name as typed', () => {
		const zones = timeZoneItems([
			'Europe/Paris',
			'Europe/London',
			'America/Argentina/Buenos_Aires'
		]);
		expect(filterComboboxItems(zones, 'Europe/Paris').map((i) => i.value)).toEqual([
			'Europe/Paris'
		]);
		expect(filterComboboxItems(zones, 'argentina/buenos_aires').map((i) => i.value)).toEqual([
			'America/Argentina/Buenos_Aires'
		]);
	});

	it('labels a stored value', () => {
		expect(zoneLabel('America/Argentina/Buenos_Aires')).toBe('America/Argentina/Buenos Aires');
		expect(zoneLabel(BROWSER_ZONE)).toBe('Match my browser (Europe/London)');
	});
});
