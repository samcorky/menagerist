<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/json-schema';
	import { BROWSER_ZONE, zoneLabel } from './time-zones';

	let { value, prop: _prop }: { value: unknown; prop: JsonSchemaProperty } = $props();
</script>

<span>{zoneLabel(typeof value === 'string' && value !== '' ? value : BROWSER_ZONE)}</span>
