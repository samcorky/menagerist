<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { formatPartialDate } from '$lib/format-date';

	let {
		value,
		prop: _prop
	}: {
		value: unknown;
		prop: JsonSchemaProperty;
	} = $props();

	let display = $derived(
		typeof value !== 'string' || value === '' ? '-' : formatPartialDate(value, 'long')
	);
</script>

<span>{display}</span>
