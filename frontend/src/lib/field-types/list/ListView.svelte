<script lang="ts">
	import { readPropMeta } from '$lib/schema-meta';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let { value, prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	let items = $derived(Array.isArray(value) ? value.map(String) : []);
	let bulleted = $derived(readPropMeta(prop).display === 'bulleted');
</script>

{#if items.length === 0}
	<span class="text-muted-foreground">—</span>
{:else if bulleted}
	<ul class="list-inside list-disc space-y-0.5 text-sm">
		{#each items as item, i (i)}
			<li class="whitespace-pre-wrap">{item}</li>
		{/each}
	</ul>
{:else}
	<ol class="list-inside list-decimal space-y-0.5 text-sm">
		{#each items as item, i (i)}
			<li class="whitespace-pre-wrap">{item}</li>
		{/each}
	</ol>
{/if}
