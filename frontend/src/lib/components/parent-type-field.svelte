<script lang="ts">
	import type { NodeTypeResponse } from '$lib/api/client';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import { inheritedFieldRows, parentChoices } from '$lib/type-inheritance';

	// The "Subtype of" part of the item type editor: pick the type this one is a subtype of, or none.
	// A subtype uses its parent's fields as well as its own, so they are listed here, read-only.
	let {
		parent = $bindable(null as string | null),
		types,
		editing = null
	}: {
		/** The slug of the parent type, or null for a top-level type. */
		parent?: string | null;
		/** Every item type the person has. */
		types: NodeTypeResponse[];
		/** The type being edited; null while a new one is created. */
		editing?: NodeTypeResponse | null;
	} = $props();

	const id = $props.id();
	const choices = $derived(parentChoices(types, editing));
	const parentType = $derived(parent ? types.find((t) => t.slug === parent) : undefined);
	const rows = $derived(inheritedFieldRows(parentType));
	const locked = $derived(choices.lockedBy.length > 0);
</script>

<div class="space-y-1.5">
	<Label for="{id}-select">Subtype of</Label>
	<NativeSelect.Root
		id="{id}-select"
		class="w-full sm:max-w-sm"
		value={parent ?? ''}
		disabled={locked}
		aria-describedby="{id}-hint"
		onchange={(e) => (parent = e.currentTarget.value || null)}
	>
		<NativeSelect.Option value="">None (a top-level item type)</NativeSelect.Option>
		{#each choices.options as option (option.slug)}
			<NativeSelect.Option value={option.slug}>{option.label}</NativeSelect.Option>
		{/each}
		<!-- A parent that has gone stays in the list so the choice is not silently lost. -->
		{#if parent && !parentType}
			<NativeSelect.Option value={parent}>{parent} (no longer an item type)</NativeSelect.Option>
		{/if}
	</NativeSelect.Root>
	<p id="{id}-hint" class="text-xs text-muted-foreground">
		{#if locked}
			{editing?.label} has subtypes ({choices.lockedBy.map((t) => t.label).join(', ')}), so it
			cannot be a subtype itself. Move or delete them first.
		{:else if parentType}
			Uses {parentType.label}'s fields as well as its own, and {parentType.label}'s icon and colour
			until it sets its own. Items of {parentType.label} are found together with this type's.
		{:else}
			Make this a subtype of another item type, such as Poster under Memorabilia. A subtype uses its
			parent's fields as well as its own.
		{/if}
	</p>
</div>

{#if parentType && rows.length > 0}
	<div class="space-y-1.5" data-testid="inherited-fields">
		<p class="text-sm font-medium">Fields from {parentType.label}</p>
		<ul class="divide-y rounded-xl border bg-muted/30">
			{#each rows as row (row.key)}
				<li class="flex items-center justify-between gap-3 px-3 py-2 text-sm">
					<span class="min-w-0 truncate">{row.label}</span>
					<span class="shrink-0 text-xs text-muted-foreground">From {parentType.label}</span>
				</li>
			{/each}
		</ul>
		<p class="text-xs text-muted-foreground">
			These are read-only here. Change them on {parentType.label}.
		</p>
	</div>
{/if}
