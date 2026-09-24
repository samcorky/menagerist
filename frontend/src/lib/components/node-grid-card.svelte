<script lang="ts">
	import { resolve } from '$app/paths';
	import { Package } from '@lucide/svelte';
	import type { NodeResponse } from '$lib/api/client';
	import type { AttributesSchema } from '$lib/schema-types';
	import type { MatchContext } from '$lib/search-context';
	import NodeCover from './node-cover.svelte';
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
</script>

<a href={resolve('/collection/[id]', { id: item.id })} class="group block">
	<div
		class="flex aspect-[3/4] flex-col overflow-hidden rounded-xl border bg-muted/30 transition-colors group-hover:bg-muted/60"
	>
		<!-- Cover image or generic placeholder (§7b: muted background + category icon) -->
		<div class="min-h-0 flex-1 overflow-hidden">
			<NodeCover nodeId={item.id} class="h-full w-full">
				<div class="flex h-full w-full items-center justify-center bg-muted">
					<Package class="size-8 text-muted-foreground/40" />
				</div>
			</NodeCover>
		</div>
		<div class="border-t bg-background/80 px-2.5 py-2">
			<p class="truncate text-sm leading-tight font-medium">{item.name}</p>
			{#if categoryLabel}
				<p class="mt-0.5 truncate text-xs text-muted-foreground">{categoryLabel}</p>
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
</a>
