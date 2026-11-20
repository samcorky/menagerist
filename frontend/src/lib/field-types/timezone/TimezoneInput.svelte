<script lang="ts">
	import Combobox from '$lib/components/ui/combobox/combobox.svelte';
	import { browserZone, currentPrefs, formatTime } from '$lib/format-date';
	import type { JsonSchemaProperty } from '$lib/json-schema';
	import { BROWSER_ZONE, timeZoneItems } from './time-zones';

	let {
		value,
		onChange,
		ariaLabel,
		prop: _prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	const items = timeZoneItems();
	const selected = $derived(typeof value === 'string' && value !== '' ? value : BROWSER_ZONE);
	// The time there now, as a check that the zone is the one meant.
	const zone = $derived(selected === BROWSER_ZONE ? browserZone() : selected);
	const there = $derived(formatTime(new Date(), { ...currentPrefs(), zone }));
</script>

<div class="flex min-w-0 flex-1 flex-col gap-1">
	<Combobox
		{items}
		value={selected}
		aria-label={ariaLabel}
		placeholder="Choose a time zone"
		searchPlaceholder="Search for a city or region…"
		emptyText="No time zone found"
		onValueChange={(next) => onChange(next)}
		class="w-full"
	/>
	<p class="text-xs text-muted-foreground">It's {there} there now.</p>
</div>
