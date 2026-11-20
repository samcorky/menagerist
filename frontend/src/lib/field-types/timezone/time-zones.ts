import type { ComboboxItem } from '$lib/components/ui/combobox/combobox';
import { browserZone, knownZones, zoneOffset } from '$lib/format-date';

/** The stored value that leaves the zone to the device. */
export const BROWSER_ZONE = 'browser';

/** How a zone reads: "Match my browser (Europe/London)", or the zone's own name. */
export function zoneLabel(value: string): string {
	if (value === BROWSER_ZONE) return `Match my browser (${browserZone()})`;
	return value.replaceAll('_', ' ');
}

/**
 * The choices: "Match my browser" first, then each zone under its region ("Europe"), named by
 * the rest of its path ("London") with its current offset, so a city or a region finds it.
 */
export function timeZoneItems(zones: readonly string[] = knownZones()): ComboboxItem[] {
	const now = new Date();
	return [
		{ value: BROWSER_ZONE, label: zoneLabel(BROWSER_ZONE) },
		...zones.map((zone) => {
			const slash = zone.indexOf('/');
			return {
				value: zone,
				label: (slash === -1 ? zone : zone.slice(slash + 1)).replaceAll('_', ' '),
				group: slash === -1 ? 'Other' : zone.slice(0, slash),
				selectedLabel: zoneLabel(zone),
				description: zoneOffset(zone, now)
			};
		})
	];
}
