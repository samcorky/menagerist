<script lang="ts">
	import { tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { ArrowRight, Search } from '@lucide/svelte';
	import type { NodeResponse, NodeTypeResponse } from '$lib/api/client';
	import { delayedLoading } from '$lib/delayed-loading.svelte';
	import { loadExampleIds } from '$lib/examples';
	import {
		loadItemTypes,
		searchEverything,
		type AsyncGroupKey,
		type GroupState,
		type Results
	} from '$lib/palette-sources';
	import type { StaticRoute } from '$lib/palette-search';
	import { matchContext } from '$lib/search-context';
	import type { AttributesSchema } from '$lib/schema-types';
	import {
		defaultHighlight,
		firstLiveValue,
		liveMessage,
		paletteView,
		resultSubtitle,
		seeAllSearch
	} from '$lib/search-palette';
	import { searchPaletteController } from '$lib/search-palette.svelte';
	import * as Command from '$lib/components/ui/command/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	const DEBOUNCE_MS = 250;
	const SEE_ALL_VALUE = 'see-all-results';
	const ASYNC_KEYS: AsyncGroupKey[] = ['items', 'collections', 'itemTypes'];
	const GROUP_NOUN: Record<AsyncGroupKey, string> = {
		items: 'items',
		collections: 'collections',
		itemTypes: 'item types'
	};

	const emptyResults = (): Results => ({
		items: { status: 'ok', rows: [] },
		collections: { status: 'ok', rows: [] },
		itemTypes: { status: 'ok', rows: [] },
		pages: []
	});

	let query = $state('');
	let groups = $state<Results>(emptyResults());
	// Sources still waiting on an answer for the current query
	let loading = $state<AsyncGroupKey[]>([]);
	// Sources being re-run from their retry row
	let retrying = $state<AsyncGroupKey[]>([]);
	let itemsAnswered = $state(false);
	let debouncing = $state(false);
	let highlighted = $state('');
	// The row the popup chose itself; an arrow key moves the highlight off it
	let autoHighlight = '';
	let types = $state<NodeTypeResponse[]>([]);
	let exampleIds = $state<ReadonlySet<string>>(new Set());
	let inputEl = $state<HTMLInputElement | null>(null);
	let seq = 0;
	// Set when the popup closes to navigate, so focus is left for the new page.
	let navigating = false;

	// §13a: the 300 ms starts when the request does, not at the keystroke
	const spinner = delayedLoading();

	const pending = $derived(debouncing || loading.length > 0);
	const okRows = <T,>(state: GroupState<T>): T[] => (state.status === 'ok' ? state.rows : []);
	const failedKeys = $derived(
		ASYNC_KEYS.filter((key) => groups[key].status === 'error' && !loading.includes(key))
	);
	const count = $derived(
		okRows(groups.items).length +
			okRows(groups.collections).length +
			okRows(groups.itemTypes).length +
			groups.pages.length
	);
	const view = $derived(
		paletteView({
			query,
			pending,
			showSpinner: spinner.show,
			count,
			failed: failedKeys.length
		})
	);
	const announcement = $derived(liveMessage(view, query, count, failedKeys.length));
	// Rows from an earlier query stay up until their source answers; they cannot be opened
	const staleKeys = $derived(debouncing ? [...ASYNC_KEYS, 'pages' as const] : loading);
	// First row in display order that can be opened
	const firstValue = $derived(
		firstLiveValue([
			{
				values: okRows(groups.items).map((r) => `item:${r.id}`),
				stale: staleKeys.includes('items')
			},
			{
				values: okRows(groups.collections).map((r) => `collection:${r.id}`),
				stale: staleKeys.includes('collections')
			},
			{
				values: okRows(groups.itemTypes).map((r) => `type:${r.slug}`),
				stale: staleKeys.includes('itemTypes')
			},
			{
				values: groups.pages.map((r) => `page:${r.path}`),
				stale: staleKeys.includes('pages')
			}
		])
	);

	function typeOf(item: NodeResponse): NodeTypeResponse | undefined {
		return types.find((t) => t.slug === item.type);
	}

	function subtitle(item: NodeResponse): string {
		const type = typeOf(item);
		const schema = (type?.attributes_schema as AttributesSchema | null | undefined) ?? null;
		return resultSubtitle(type?.label ?? null, matchContext(item, schema, query));
	}

	function countLabel(n: number): string {
		return n === 1 ? '1 item' : `${n} items`;
	}

	function settleHighlight() {
		if (highlighted !== '' && highlighted !== autoHighlight) return;
		highlighted = defaultHighlight(firstValue, itemsAnswered, SEE_ALL_VALUE);
		autoHighlight = highlighted;
	}

	const isStale = (key: AsyncGroupKey | 'pages') => staleKeys.includes(key);
	const retryBusy = (key: AsyncGroupKey) => debouncing || loading.includes(key);
	// An errored group shows its retry row; one hidden while a new query reloads it does not
	const showFailed = (key: AsyncGroupKey) =>
		groups[key].status === 'error' && (!loading.includes(key) || retrying.includes(key));

	function retry(key: AsyncGroupKey) {
		if (retryBusy(key)) return;
		retrying = [...retrying, key];
		run(query.trim(), [key]);
	}

	function run(text: string, only?: AsyncGroupKey[]) {
		const mine = only ? seq : ++seq;
		debouncing = false;
		if (!only) itemsAnswered = false;
		loading = [...new Set([...loading, ...(only ?? ASYNC_KEYS)])];
		spinner.set(true);
		void searchEverything(
			text,
			(partial) => {
				groups = { ...groups, ...partial };
				const settled = Object.keys(partial) as (keyof Results)[];
				loading = loading.filter((key) => !settled.includes(key));
				if (settled.includes('items')) itemsAnswered = true;
				if (retrying.some((key) => settled.includes(key))) {
					retrying = retrying.filter((key) => !settled.includes(key));
					// The retry row may unmount under the focused button
					void tick().then(() => {
						if (!document.activeElement || document.activeElement === document.body) {
							inputEl?.focus();
						}
					});
				}
				if (loading.length === 0) spinner.set(false);
				settleHighlight();
			},
			() => mine === seq,
			only
		);
	}

	// Debounced search; a blank query cancels anything in flight.
	$effect(() => {
		const text = query.trim();
		if (!searchPaletteController.open) return;
		if (!text) {
			seq++;
			debouncing = false;
			loading = [];
			retrying = [];
			spinner.set(false);
			groups = emptyResults();
			highlighted = '';
			autoHighlight = '';
			return;
		}
		const timer = setTimeout(() => run(text), DEBOUNCE_MS);
		debouncing = true;
		retrying = [];
		highlighted = SEE_ALL_VALUE;
		autoHighlight = SEE_ALL_VALUE;
		return () => clearTimeout(timer);
	});

	$effect(() => {
		if (!searchPaletteController.open) return;
		void loadItemTypes()
			.then((loaded) => (types = loaded))
			.catch(() => {});
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
		groups = emptyResults();
		loading = [];
		retrying = [];
		highlighted = '';
		autoHighlight = '';
		debouncing = false;
		spinner.set(false);
	}

	function choose(key: AsyncGroupKey | 'pages', go: () => void) {
		if (isStale(key)) return seeAll();
		navigating = true;
		onOpenChange(false);
		go();
	}

	const openItem = (item: NodeResponse) =>
		choose('items', () => void goto(resolve('/items/[id]', { id: item.id })));
	const openCollection = (id: string) =>
		choose('collections', () => void goto(resolve('/collections/[id]', { id })));
	const openItemType = (slug: string) =>
		choose(
			'itemTypes',
			() => void goto(resolve(`/items?${new URLSearchParams({ type: slug }).toString()}`))
		);
	const openPage = (path: StaticRoute) => choose('pages', () => void goto(resolve(path)));

	function seeAll() {
		const search = seeAllSearch(query);
		navigating = true;
		onOpenChange(false);
		void goto(resolve(`/items?${search}`));
	}
</script>

{#snippet failedRow(key: AsyncGroupKey)}
	<div class="flex min-h-11 items-center justify-between gap-2 px-2 text-sm">
		<span class="text-muted-foreground">Couldn't search {GROUP_NOUN[key]}</span>
		<!-- aria-disabled, not disabled, so focus stays on the button while it reloads -->
		<Button
			variant="outline"
			class={['min-h-11', retryBusy(key) && 'opacity-50']}
			aria-label={`Try searching ${GROUP_NOUN[key]} again`}
			aria-disabled={retryBusy(key)}
			onclick={() => retry(key)}
			onkeydown={(e) => {
				// Command.Root would otherwise treat Enter as selecting the highlighted row
				if (e.key === 'Enter') e.stopPropagation();
			}}
		>
			{retrying.includes(key) ? 'Retrying…' : 'Try again'}
		</Button>
	</div>
{/snippet}

<ResponsiveDialog.Root open={searchPaletteController.open} {onOpenChange}>
	<ResponsiveDialog.Content
		title="Search"
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
				placeholder="Search everything…"
				aria-label="Search"
				class="h-11"
			/>
			<p class="sr-only" role="status" aria-live="polite">{announcement}</p>
			{#if view === 'hint'}
				<p class="py-6 text-center text-sm text-muted-foreground" aria-hidden="true">
					Type to search items, collections, item types and pages
				</p>
			{:else if view === 'loading'}
				<div class="flex justify-center py-6" aria-hidden="true">
					<Spinner class="size-5" />
				</div>
			{:else if view === 'empty'}
				<p class="py-6 text-center text-sm text-muted-foreground" aria-hidden="true">
					Nothing found for "{query.trim()}"
				</p>
			{/if}
			{#if view !== 'hint'}
				<Command.List class="mt-2 max-h-[50dvh]">
					{#if showFailed('items')}
						<Command.Group heading="Items">{@render failedRow('items')}</Command.Group>
					{:else if okRows(groups.items).length > 0}
						<Command.Group heading="Items">
							{#each okRows(groups.items) as item (item.id)}
								{@const sub = subtitle(item)}
								<Command.Item
									disabled={isStale('items')}
									value={`item:${item.id}`}
									class="min-h-11"
									onSelect={() => openItem(item)}
								>
									<div class="min-w-0 flex-1">
										<div class="flex items-center gap-2">
											<span class="truncate font-medium">{item.name}</span>
											{#if exampleIds.has(item.id)}
												<Badge variant="outline" class="shrink-0 text-muted-foreground">
													Example
												</Badge>
											{/if}
										</div>
										{#if sub}
											<p class="truncate text-xs text-muted-foreground">{sub}</p>
										{/if}
									</div>
								</Command.Item>
							{/each}
						</Command.Group>
					{/if}
					{#if showFailed('collections')}
						<Command.Group heading="Collections">{@render failedRow('collections')}</Command.Group>
					{:else if okRows(groups.collections).length > 0}
						<Command.Group heading="Collections">
							{#each okRows(groups.collections) as collection (collection.id)}
								<Command.Item
									disabled={isStale('collections')}
									value={`collection:${collection.id}`}
									class="min-h-11"
									onSelect={() => openCollection(collection.id)}
								>
									<div class="min-w-0 flex-1">
										<span class="block truncate font-medium">{collection.name}</span>
										<p class="truncate text-xs text-muted-foreground">
											{countLabel(collection.item_count)}
										</p>
									</div>
								</Command.Item>
							{/each}
						</Command.Group>
					{/if}
					{#if showFailed('itemTypes')}
						<Command.Group heading="Item types">{@render failedRow('itemTypes')}</Command.Group>
					{:else if okRows(groups.itemTypes).length > 0}
						<Command.Group heading="Item types">
							{#each okRows(groups.itemTypes) as type (type.slug)}
								<Command.Item
									disabled={isStale('itemTypes')}
									value={`type:${type.slug}`}
									class="min-h-11"
									onSelect={() => openItemType(type.slug)}
								>
									<div class="min-w-0 flex-1">
										<span class="block truncate font-medium">{type.label}</span>
										<p class="truncate text-xs text-muted-foreground">Item type</p>
									</div>
								</Command.Item>
							{/each}
						</Command.Group>
					{/if}
					{#if groups.pages.length > 0}
						<Command.Group heading="Pages">
							{#each groups.pages as page (page.path)}
								<Command.Item
									disabled={isStale('pages')}
									value={`page:${page.path}`}
									class="min-h-11"
									onSelect={() => openPage(page.path)}
								>
									<div class="min-w-0 flex-1">
										<span class="block truncate font-medium">{page.label}</span>
										<p class="truncate text-xs text-muted-foreground">Page</p>
									</div>
								</Command.Item>
							{/each}
						</Command.Group>
					{/if}
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
