<script lang="ts">
	import { readPropMeta } from '$lib/schema-meta';
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { durationSeconds, formatDuration } from './format';

	let {
		value,
		prop
	}: {
		value: unknown;
		prop: JsonSchemaProperty;
	} = $props();

	let seconds = $derived(durationSeconds(value));
	let display = $derived(
		seconds === null
			? '-'
			: formatDuration(seconds, readPropMeta(prop).display === 'words' ? 'words' : 'clock')
	);
</script>

<span>{display}</span>
