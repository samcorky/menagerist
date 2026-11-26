<script lang="ts">
	import { resolve } from '$app/paths';
	import type { NodeResponse } from '$lib/api/client';
	import type { AttributesSchema } from '$lib/schema-types';
	import type { MatchContext } from '$lib/search-context';
	import * as Item from '$lib/components/ui/item/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import NodeCover from './node-cover.svelte';
	import { rememberItemPreview } from '$lib/item-preview';
	import NodeSummary from './node-summary.svelte';
	import TypeIcon from './type-icon.svelte';
	import TagList from './tag-list.svelte';
	import { nextCardIndex } from './card-grid-nav';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import { createLongPress } from '$lib/long-press';

	let {
		item,
		schema,
		categoryLabel,
		categoryParent,
		typeIcon,
		typeColour,
		match,
		isExample = false,
		selectable = false,
		selected = false,
		onselect,
		onlongpress
	}: {
		item: NodeResponse;
		schema: AttributesSchema | null;
		categoryLabel?: string | null;
		/** The parent type's name when the item's type is a subtype; the card shows only its own. */
		categoryParent?: string | null;
		/** The item type's icon and colour, shown when the item has no cover. */
		typeIcon?: string | null;
		typeColour?: string | null;
		match?: MatchContext | null;
		isExample?: boolean;
		/** Selection mode: the card becomes a checkbox row instead of a link to the item. */
		selectable?: boolean;
		selected?: boolean;
		onselect?: () => void;
		/** A touch hold on the link, which the page uses to enter selection mode. */
		onlongpress?: () => void;
	} = $props();

	const press = $derived(onlongpress ? createLongPress(onlongpress) : null);

	// Falls back to the raw type slug so a category that's since been deleted still shows something.
	const categoryText = $derived(categoryLabel ?? item.type ?? undefined);

	function handleKeydown(e: KeyboardEvent) {
		if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
		const link = e.currentTarget as HTMLElement;
		const container = link.closest<HTMLElement>('[role="list"]');
		if (!container) return;
		const links = Array.from(
			container.querySelectorAll<HTMLElement>('a[href], [data-selectable-card]')
		);
		const currentIndex = links.indexOf(link);
		if (currentIndex === -1) return;
		const rects = links.map((el) => {
			const rect = el.getBoundingClientRect();
			return { top: rect.top, left: rect.left };
		});
		const nextIndex = nextCardIndex(e.key, currentIndex, rects, 'list');
		if (nextIndex === null) return;
		e.preventDefault();
		const next = links[nextIndex];
		(next?.matches('a')
			? next
			: next?.querySelector<HTMLElement>('[data-slot="checkbox"]')
		)?.focus();
	}

	function handleCardClick(e: MouseEvent) {
		// The checkbox reports its own change; a click anywhere else on the row toggles it too.
		if ((e.target as HTMLElement).closest('[data-slot="checkbox"]')) return;
		onselect?.();
	}
</script>

{#snippet body()}
	<!-- A small cover, or the item type's icon and colour when there is none. -->
	<div class="size-12 shrink-0 overflow-hidden rounded-lg">
		<NodeCover nodeId={item.id} thumbnailUrl={item.cover_thumbnail_url ?? null} class="size-12">
			<TypeIcon icon={typeIcon} colour={typeColour} boxed class="size-12 rounded-lg text-2xl" />
		</NodeCover>
	</div>
	<Item.Content class="min-w-0 gap-1.5">
		<Item.Title class="font-heading text-base [overflow-wrap:anywhere]">
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
			<Badge
				variant="secondary"
				class="shrink-0"
				title={categoryParent ? `${categoryParent} › ${categoryText}` : undefined}
			>
				{categoryText}{#if categoryParent}<span class="sr-only">
						, a subtype of {categoryParent}
					</span>{/if}
			</Badge>
		</Item.Actions>
	{/if}
{/snippet}

{#if selectable}
	<Item.Root variant="outline" class={selected ? 'border-primary bg-primary/5' : ''}>
		{#snippet child({ props })}
			<!-- The checkbox is the keyboard control; a click on the rest of the row is a convenience. -->
			<div
				{...props}
				role="presentation"
				data-selectable-card
				class={[props.class, 'cursor-pointer']}
				onclick={handleCardClick}
				onkeydown={handleKeydown}
			>
				<div
					class="-my-2 -ml-2 flex size-8 shrink-0 items-center justify-center pointer-coarse:size-11"
				>
					<Checkbox
						checked={selected}
						onCheckedChange={() => onselect?.()}
						aria-label="Select {item.name}"
					/>
				</div>
				{@render body()}
			</div>
		{/snippet}
	</Item.Root>
{:else}
	<Item.Root variant="outline">
		{#snippet child({ props })}
			<a
				{...props}
				class={[props.class, onlongpress && 'select-none [-webkit-touch-callout:none]']}
				href={resolve('/items/[id]', { id: item.id })}
				onclick={() => rememberItemPreview(item)}
				onclickcapture={(e) => {
					if (press?.swallowClick()) {
						e.preventDefault();
						e.stopPropagation();
					}
				}}
				onpointerdown={press?.onpointerdown}
				onpointermove={press?.onpointermove}
				onpointerup={press?.onpointerup}
				onpointercancel={press?.onpointercancel}
				oncontextmenu={(e) => {
					if (press?.suppressContextMenu(e)) e.preventDefault();
				}}
				onkeydown={handleKeydown}
			>
				{@render body()}
			</a>
		{/snippet}
	</Item.Root>
{/if}
