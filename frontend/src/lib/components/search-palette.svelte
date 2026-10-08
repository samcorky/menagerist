<script lang="ts" module>
	import { listNodeTypes, type NodeTypeResponse } from '$lib/api/client';

	let typesPromise: Promise<NodeTypeResponse[]> | null = null;

	// Item types are loaded once per page lifetime; a failed load is retried on the next open.
	function loadTypes(): Promise<NodeTypeResponse[]> {
		typesPromise ??= listNodeTypes({ query: { limit: 100 } })
			.then((result) => {
				if (!result.data) typesPromise = null;
				return result.data ?? [];
			})
			.catch(() => {
				typesPromise = null;
				return [];
			});
		return typesPromise;
	}
</script>

<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { ArrowRight, Search } from '@lucide/svelte';
	import { listNodes, type NodeResponse } from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import { delayedLoading } from '$lib/delayed-loading.svelte';
	import { loadExampleIds } from '$lib/examples';
	import { matchContext } from '$lib/search-context';
	import type { AttributesSchema } from '$lib/schema-types';
	import {
		SEARCH_RESULT_LIMIT,
		paletteView,
		resultSubtitle,
		seeAllSearch,
		liveMessage
	} from '$lib/search-palette';
	import { searchPaletteController } from '$lib/search-palette.svelte';
	import * as Command from '$lib/components/ui/command/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	const DEBOUNCE_MS = 250;
	const SEE_ALL_VALUE = 'see-all-results';

	let query = $state('');
	let results = $state<NodeResponse[]>([]);
	let pending = $state(false);
	let failure = $state<string | null>(null);
	let highlighted = $state('');
	let types = $state<NodeTypeResponse[]>([]);
	let exampleIds = $state<ReadonlySet<string>>(new Set());
	let inputEl = $state<HTMLInputElement | null>(null);
	let seq = 0;
	// Set when the popup closes to navigate, so focus is left for the new page.
	let navigating = false;

	// §13a: the 300 ms starts when the request does, not at the keystroke
	const spinner = delayedLoading();

	const view = $derived(
		paletteView({
			query,
			error: failure !== null,
			pending,
			showSpinner: spinner.show,
			count: results.length
		})
	);
	const announcement = $derived(liveMessage(view, query, results.length, failure));

	function typeOf(item: NodeResponse): NodeTypeResponse | undefined {
		return types.find((t) => t.slug === item.type);
	}

	function subtitle(item: NodeResponse): string {
		const type = typeOf(item);
		const schema = (type?.attributes_schema as AttributesSchema | null | undefined) ?? null;
		return resultSubtitle(type?.label ?? null, matchContext(item, schema, query));
	}

	async function search(text: string) {
		const mine = ++seq;
		pending = true;
		failure = null;
		spinner.set(true);
		const result = await listNodes({ query: { q: text, limit: SEARCH_RESULT_LIMIT } });
		if (mine !== seq) return;
		pending = false;
		spinner.set(false);
		if (result.error || !result.data) {
			const { title, description } = networkAwareError(result);
			failure = description ?? title;
			results = [];
			highlighted = '';
			return;
		}
		results = result.data;
		highlighted = result.data[0]?.id ?? SEE_ALL_VALUE;
	}

	// Debounced search; a blank query cancels anything in flight.
	$effect(() => {
		const text = query.trim();
		if (!searchPaletteController.open) return;
		if (!text) {
			seq++;
			pending = false;
			spinner.set(false);
			failure = null;
			results = [];
			highlighted = '';
			return;
		}
		const timer = setTimeout(() => void search(text), DEBOUNCE_MS);
		pending = true;
		highlighted = '';
		return () => clearTimeout(timer);
	});

	$effect(() => {
		if (!searchPaletteController.open) return;
		void loadTypes().then((loaded) => (types = loaded));
		void loadExampleIds().then((ids) => (exampleIds = ids.items));
	});

	function onOpenChange(open: boolean) {
		if (open) {
			searchPaletteController.show();
			return;
		}
		searchPaletteController.hide();
		seq++;
		query = '';
		results = [];
		highlighted = '';
		pending = false;
		spinner.set(false);
		failure = null;
	}

	function openItem(item: NodeResponse) {
		if (pending) return;
		navigating = true;
		onOpenChange(false);
		void goto(resolve('/items/[id]', { id: item.id }));
	}

	function seeAll() {
		const search = seeAllSearch(query);
		navigating = true;
		onOpenChange(false);
		void goto(resolve(`/items?${search}`));
	}
</script>

<ResponsiveDialog.Root open={searchPaletteController.open} {onOpenChange}>
	<ResponsiveDialog.Content
		title="Search items"
		size="lg"
		onOpenAutoFocus={(e) => {
			e.preventDefault();
			inputEl?.focus();
		}}
		onCloseAutoFocus={(e) => {
			if (!navigating) return;
			navigating = false;
			e.preventDefault();
		}}
	>
		<Command.Root
			shouldFilter={false}
			loop
			bind:value={highlighted}
			class="mt-3 bg-transparent p-0"
		>
			<Command.Input
				bind:ref={inputEl}
				bind:value={query}
				placeholder="Search your items…"
				aria-label="Search your items"
				class="h-11"
			/>
			<p class="sr-only" role="status" aria-live="polite">{announcement}</p>
			{#if view === 'hint'}
				<p class="py-6 text-center text-sm text-muted-foreground" aria-hidden="true">
					Type to search your items
				</p>
			{:else if view === 'error'}
				<div class="flex flex-col items-center gap-2 py-6 text-center text-sm">
					<p class="text-muted-foreground" aria-hidden="true">{failure}</p>
					<Button variant="outline" class="min-h-11" onclick={() => void search(query.trim())}>
						Try again
					</Button>
				</div>
			{:else if view === 'loading'}
				<div class="flex justify-center py-6" aria-hidden="true">
					<Spinner class="size-5" />
				</div>
			{:else if view === 'empty'}
				<p class="py-6 text-center text-sm text-muted-foreground" aria-hidden="true">
					No items match "{query.trim()}"
				</p>
			{/if}
			{#if view !== 'hint' && view !== 'error'}
				<Command.List class="mt-2 max-h-[50dvh]">
					{#each results as item (item.id)}
						{@const sub = subtitle(item)}
						<Command.Item value={item.id} class="min-h-11" onSelect={() => openItem(item)}>
							<div class="min-w-0 flex-1">
								<div class="flex items-center gap-2">
									<span class="truncate font-medium">{item.name}</span>
									{#if exampleIds.has(item.id)}
										<Badge variant="outline" class="shrink-0 text-muted-foreground">Example</Badge>
									{/if}
								</div>
								{#if sub}
									<p class="truncate text-xs text-muted-foreground">{sub}</p>
								{/if}
							</div>
						</Command.Item>
					{/each}
					<Command.Item value={SEE_ALL_VALUE} class="min-h-11" onSelect={seeAll}>
						<Search class="size-4" />
						<span class="flex-1">See all results in Items</span>
						<ArrowRight class="size-4" />
					</Command.Item>
				</Command.List>
			{/if}
		</Command.Root>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
