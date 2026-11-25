<script lang="ts">
	import { resolve } from '$app/paths';
	import type { NodeResponse } from '$lib/api/client';
	import type { AttributesSchema } from '$lib/schema-types';
	import type { MatchContext } from '$lib/search-context';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import NodeCover from './node-cover.svelte';
	import { rememberItemPreview } from '$lib/item-preview';
	import TypeIcon from './type-icon.svelte';
	import NodeSummary from './node-summary.svelte';
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
		/** The item type's icon and colour, for the tile shown when there is no cover. */
		typeIcon?: string | null;
		typeColour?: string | null;
		match?: MatchContext | null;
		isExample?: boolean;
		/** Selection mode: the tile becomes a checkbox instead of a link to the item. */
		selectable?: boolean;
		selected?: boolean;
		onselect?: () => void;
		/** A touch hold on the link, which the page uses to enter selection mode. */
		onlongpress?: () => void;
	} = $props();

	const press = $derived(onlongpress ? createLongPress(onlongpress) : null);

	function handleKeydown(e: KeyboardEvent) {
		if (
			e.key !== 'ArrowUp' &&
			e.key !== 'ArrowDown' &&
			e.key !== 'ArrowLeft' &&
			e.key !== 'ArrowRight'
		)
			return;
		const link = e.currentTarget as HTMLElement;
		const container = link.closest<HTMLElement>('[data-slot="node-grid"]');
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
		const nextIndex = nextCardIndex(e.key, currentIndex, rects, 'grid');
		if (nextIndex === null) return;
		e.preventDefault();
		const next = links[nextIndex];
		(next?.matches('a')
			? next
			: next?.querySelector<HTMLElement>('[data-slot="checkbox"]')
		)?.focus();
	}

	function handleCardClick(e: MouseEvent) {
		// The checkbox reports its own change; a click anywhere else on the tile toggles it too.
		if ((e.target as HTMLElement).closest('[data-slot="checkbox"]')) return;
		onselect?.();
	}
</script>

{#snippet tile()}
	<div
		class={[
			'flex aspect-[3/4] flex-col overflow-hidden rounded-xl border bg-muted/30 transition-colors group-hover:bg-muted/60',
			selected && 'border-primary ring-2 ring-primary'
		]}
	>
		<!-- Cover image, or the item type's icon and colour (§7b) -->
		<div class="min-h-0 flex-1 overflow-hidden">
			<NodeCover
				nodeId={item.id}
				thumbnailUrl={item.cover_thumbnail_url ?? null}
				class="h-full w-full"
			>
				<div class="flex h-full w-full items-center justify-center bg-muted">
					<TypeIcon
						icon={typeIcon}
						colour={typeColour}
						boxed
						class="size-14 rounded-2xl text-3xl"
					/>
				</div>
			</NodeCover>
		</div>
		<div class="border-t bg-background/80 px-2.5 py-2">
			<div class="flex items-center gap-1.5">
				<p class="min-w-0 truncate text-sm leading-tight font-medium">{item.name}</p>
				{#if isExample}
					<Badge variant="outline" class="shrink-0 px-1.5 py-0 text-xs text-muted-foreground">
						Example
					</Badge>
				{/if}
			</div>
			{#if categoryLabel}
				<p
					class="mt-0.5 truncate text-xs text-muted-foreground"
					title={categoryParent ? `${categoryParent} › ${categoryLabel}` : undefined}
				>
					{categoryLabel}{#if categoryParent}<span class="sr-only">
							, a subtype of {categoryParent}
						</span>{/if}
				</p>
			{/if}
			{#if item.tags.length > 0}
				<div class="mt-1">
					<TagList tags={item.tags} max={2} compact />
				</div>
			{/if}
			<div class="mt-1 empty:hidden">
				<NodeSummary attributes={item.attributes} {schema} surface="grid" size="sm" />
			</div>
			{#if match}
				<p
					class="mt-1 truncate text-xs text-muted-foreground"
					title="Matched in {match.label}: {match.text}"
				>
					Matched in {match.label}: {match.text}
				</p>
			{/if}
		</div>
	</div>
{/snippet}

{#if selectable}
	<!-- The checkbox is the keyboard control; a click anywhere on the tile is a convenience. -->
	<div
		role="presentation"
		data-selectable-card
		class="group relative block cursor-pointer"
		onclick={handleCardClick}
		onkeydown={handleKeydown}
	>
		{@render tile()}
		<div
			class="absolute top-0 left-0 flex size-8 items-center justify-center pointer-coarse:size-11"
		>
			<Checkbox
				checked={selected}
				onCheckedChange={() => onselect?.()}
				aria-label="Select {item.name}"
				class="size-5 bg-background shadow"
			/>
		</div>
	</div>
{:else}
	<a
		href={resolve('/items/[id]', { id: item.id })}
		class={['group block', onlongpress && 'select-none [-webkit-touch-callout:none]']}
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
		{@render tile()}
	</a>
{/if}
