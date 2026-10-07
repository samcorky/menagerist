<script lang="ts">
	import { resolve } from '$app/paths';
	import type { NodeResponse } from '$lib/api/client';
	import type { AttributesSchema } from '$lib/schema-types';
	import type { MatchContext } from '$lib/search-context';
	import * as Item from '$lib/components/ui/item/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import NodeSummary from './node-summary.svelte';
	import TagList from './tag-list.svelte';
	import { nextCardIndex } from './card-grid-nav';

	let {
		item,
		schema,
		categoryLabel,
		match,
		isExample = false
	}: {
		item: NodeResponse;
		schema: AttributesSchema | null;
		categoryLabel?: string | null;
		match?: MatchContext | null;
		isExample?: boolean;
	} = $props();

	// Falls back to the raw type slug so a category that's since been deleted still shows something.
	const categoryText = $derived(categoryLabel ?? item.type ?? undefined);

	function handleKeydown(e: KeyboardEvent) {
		if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
		const link = e.currentTarget as HTMLAnchorElement;
		const container = link.closest<HTMLElement>('[role="list"]');
		if (!container) return;
		const links = Array.from(container.querySelectorAll<HTMLAnchorElement>('a[href]'));
		const currentIndex = links.indexOf(link);
		if (currentIndex === -1) return;
		const rects = links.map((el) => {
			const rect = el.getBoundingClientRect();
			return { top: rect.top, left: rect.left };
		});
		const nextIndex = nextCardIndex(e.key, currentIndex, rects, 'list');
		if (nextIndex === null) return;
		e.preventDefault();
		links[nextIndex]?.focus();
	}
</script>

<Item.Root variant="outline">
	{#snippet child({ props })}
		<a {...props} href={resolve('/items/[id]', { id: item.id })} onkeydown={handleKeydown}>
			<Item.Content class="gap-1.5">
				<Item.Title class="font-heading text-base">
					{item.name}
					{#if isExample}
						<Badge variant="outline" class="shrink-0 text-muted-foreground">Example</Badge>
					{/if}
				</Item.Title>
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
