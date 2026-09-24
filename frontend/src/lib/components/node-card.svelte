<script lang="ts">
	import { resolve } from '$app/paths';
	import type { NodeResponse } from '$lib/api/client';
	import type { AttributesSchema } from '$lib/schema-types';
	import type { MatchContext } from '$lib/search-context';
	import * as Item from '$lib/components/ui/item/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import NodeSummary from './node-summary.svelte';
	import TagList from './tag-list.svelte';

	let {
		item,
		schema,
		categoryLabel,
		match
	}: {
		item: NodeResponse;
		schema: AttributesSchema | null;
		categoryLabel?: string | null;
		match?: MatchContext | null;
	} = $props();

	// Falls back to the raw type slug so a category that's since been deleted still shows something.
	const categoryText = $derived(categoryLabel ?? item.type ?? undefined);
</script>

<Item.Root variant="outline">
	{#snippet child({ props })}
		<a {...props} href={resolve('/collection/[id]', { id: item.id })}>
			<Item.Content class="gap-1.5">
				<Item.Title class="font-heading text-base">{item.name}</Item.Title>
				{#if item.description}
					<p class="line-clamp-1 text-sm text-muted-foreground">{item.description}</p>
				{/if}
				{#if item.tags.length > 0}
					<TagList tags={item.tags} max={4} />
				{/if}
				<NodeSummary attributes={item.attributes} {schema} surface="list" size="sm" />
				{#if match}
					<p
						class="truncate text-xs text-muted-foreground"
						title="Matched in {match.label}: {match.text}"
					>
						Matched in {match.label}: {match.text}
					</p>
				{/if}
			</Item.Content>
			{#if categoryText}
				<Item.Actions>
					<Badge variant="secondary" class="shrink-0">{categoryText}</Badge>
				</Item.Actions>
			{/if}
		</a>
	{/snippet}
</Item.Root>
