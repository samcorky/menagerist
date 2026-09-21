<script lang="ts">
	import { readPropMeta } from '$lib/schema-meta';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let {
		value,
		prop
	}: {
		value: unknown;
		prop: JsonSchemaProperty;
	} = $props();

	let checked = $derived(value === true || value === 'true');
	let yesNo = $derived(readPropMeta(prop).display === 'yes-no');
</script>

{#if value === ''}
	<span class="text-muted-foreground">—</span>
{:else if yesNo}
	<span>{checked ? 'Yes' : 'No'}</span>
{:else}
	<input
		type="checkbox"
		{checked}
		class="pointer-events-none h-4 w-4 cursor-default rounded border-input accent-primary"
	/>
{/if}
