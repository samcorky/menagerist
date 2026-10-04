<script lang="ts">
	import type { PresetResponse } from '$lib/api/client';
	import AttributesEditor from '$lib/components/attributes-editor.svelte';
	import { attributesToRows, rowsToAttributes, type AttributeRow } from '$lib/attribute-rows';
	import { descriptorForProp } from '$lib/field-types';
	import { normalise, orderedKeys } from '$lib/layout';
	import { presetExampleSchema } from '$lib/preset-packs';
	import { readSchemaMeta } from '$lib/schema-meta';

	let { preset }: { preset: PresetResponse } = $props();

	let schema = $derived(presetExampleSchema(preset));
	let rows = $state<AttributeRow[]>(attributesToRows({}));
	// Typed as an item would store them, so the preview matches a saved item.
	let previewValues = $derived(rowsToAttributes(rows, schema));
	let previewKeys = $derived(
		orderedKeys(normalise(readSchemaMeta(schema).layout, schema.properties)).filter(
			(key) => key in schema.properties
		)
	);
</script>

<section class="space-y-3 rounded-md border border-dashed p-3">
	<div>
		<h3 class="text-sm font-medium">Try it</h3>
		<p class="text-xs text-muted-foreground">Nothing you enter here is saved.</p>
	</div>
	<AttributesEditor bind:rows {schema} />

	<div class="space-y-2 border-t pt-3">
		<h3 class="text-sm font-medium">Read-only view</h3>
		{#each previewKeys as key (key)}
			{@const prop = schema.properties[key]}
			{@const value = previewValues[key] ?? ''}
			{@const ViewWidget = descriptorForProp(prop)?.ViewWidget}
			<div class="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-2">
				<span class="pt-0.5 text-sm text-muted-foreground sm:w-32 sm:shrink-0">
					{prop.title || key}
				</span>
				<div class="min-w-0 flex-1 text-sm break-words">
					{#if ViewWidget}
						<ViewWidget {value} {prop} />
					{:else}
						{value === '' ? '-' : String(value)}
					{/if}
				</div>
			</div>
		{/each}
	</div>
</section>
