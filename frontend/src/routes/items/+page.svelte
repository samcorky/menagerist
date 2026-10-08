<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { beforeNavigate, afterNavigate, goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import { untrack } from 'svelte';
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import { EyeOff, List, Plus, SearchX, LayoutGrid } from '@lucide/svelte';
	import { captureController } from '$lib/capture.svelte.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { toast } from 'svelte-sonner';
	import {
		listNodes,
		listNodeTypes,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Item from '$lib/components/ui/item/index.js';
	import NodeCard from '$lib/components/node-card.svelte';
	import NodeGridCard from '$lib/components/node-grid-card.svelte';
	import type { AttributesSchema } from '$lib/schema-types';
	import {
		EXAMPLE_FILTER_LABELS,
		loadExampleIds,
		readExampleFilter,
		visibleItems,
		writeExampleFilter,
		type ExampleFilter
	} from '$lib/examples';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import { matchContext } from '$lib/search-context';
	import { normaliseQuery } from '$lib/search-palette';
	import { registerShortcut } from '$lib/shortcuts.svelte';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3, 4, 5];

	// Persisted outside component so scroll position survives navigation
	let savedScrollTop = 0;

	let items = $state<NodeResponse[]>([]);
	let allCategories = $state<NodeTypeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(true);
	let selectedType = $state<string | null>(null);
	let fetchSeq = 0;
	let searchInput = $state('');
	let q = $state('');
	let searchEl = $state<HTMLInputElement | null>(null);
	let searchFocused = $state(false);
	let viewMode = $state<'list' | 'grid'>('list');
	let exampleItemIds = $state<ReadonlySet<string>>(new Set());
	let exampleFilter = $state<ExampleFilter>(readExampleFilter());
	const showExampleFilter = $derived(exampleItemIds.size > 0 || exampleFilter !== 'all');
	const shownItems = $derived(visibleItems(items, exampleItemIds, exampleFilter));
	const exampleFilters = Object.keys(EXAMPLE_FILTER_LABELS) as ExampleFilter[];

	function setExampleFilter(filter: ExampleFilter) {
		exampleFilter = filter;
		writeExampleFilter(filter);
	}

	$effect(() => {
		void loadExampleIds().then((ids) => (exampleItemIds = ids.items));
	});

	// §13a: don't flash a skeleton for loads under 300ms
	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading);
	});

	let selectedTypeLabel = $derived(
		allCategories.find((c) => c.slug === selectedType)?.label ?? selectedType
	);

	// Initialise view mode from localStorage
	$effect(() => {
		if (browser) {
			const stored = localStorage.getItem('items-view');
			if (stored === 'grid' || stored === 'list') viewMode = stored;
		}
	});

	$effect(() => {
		if (browser) localStorage.setItem('items-view', viewMode);
	});

	// Pick up ?q= from the URL (the search popup's "See all results"), then drop it so the same
	// link works again after the box has been cleared.
	$effect(() => {
		const urlQ = normaliseQuery(page.url.searchParams.get('q'));
		if (!urlQ) return;
		if (urlQ !== untrack(() => q)) {
			items = [];
			hasMore = true;
			q = urlQ;
		}
		searchInput = urlQ;
		const params = new SvelteURLSearchParams(page.url.searchParams);
		params.delete('q');
		const rest = params.toString();
		void goto(resolve(rest ? `/items?${rest}` : '/items'), {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	});

	// Pick up ?type= from URL (from dashboard category chips)
	$effect(() => {
		const typeParam = page.url.searchParams.get('type');
		if (typeParam && typeParam !== selectedType) {
			selectedType = typeParam;
		}
	});

	$effect(() => {
		const value = searchInput;
		const timer = setTimeout(() => {
			if (value === q) return;
			items = [];
			hasMore = true;
			q = value;
		}, 300);
		return () => clearTimeout(timer);
	});

	async function fetchPage(after?: string) {
		const seq = ++fetchSeq;
		loading = true;
		const result = await listNodes({
			query: { after, limit: PAGE_SIZE, type: selectedType ?? undefined, q: q || undefined }
		});
		if (seq !== fetchSeq) return;
		if (result.error || !result.data) {
			const { title, description } = networkAwareError(result);
			toast.error(title, { description });
			hasMore = false;
		} else {
			items = after ? [...items, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		loading = false;
	}

	async function fetchCategories() {
		const result = await listNodeTypes({ query: { limit: 100 } });
		if (result.data) allCategories = result.data;
	}

	function schemaOf(slug: string | null | undefined): AttributesSchema | null {
		const cat = allCategories.find((c) => c.slug === slug);
		return (cat?.attributes_schema as AttributesSchema | null | undefined) ?? null;
	}

	function selectType(type: string | null) {
		if (selectedType === type) return;
		items = [];
		hasMore = true;
		selectedType = type;
	}

	function sentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && hasMore && !loading) void fetchPage(items.at(-1)?.id);
			},
			{ rootMargin: '200px' }
		);
		observer.observe(node);
		return {
			destroy() {
				observer.disconnect();
			}
		};
	}

	function focusRef(node: HTMLInputElement) {
		searchEl = node;
		return {
			destroy() {
				searchEl = null;
			}
		};
	}

	$effect(() => {
		if (captureController.nodeCreationCount === 0) return;
		items = [];
		hasMore = true;
		void fetchPage();
	});

	$effect(() => {
		void fetchPage();
	});

	$effect(() => {
		void fetchCategories();
	});

	$effect(() => {
		if (!searchFocused) return;
		return registerShortcut({
			id: 'items-clear-search',
			keys: 'Escape',
			description: 'Clear search',
			group: 'Search',
			allowInInputs: true,
			handler: () => {
				searchInput = '';
				searchEl?.blur();
			}
		});
	});

	// Scroll preservation: save before navigating into an item, restore on return
	beforeNavigate(({ to }) => {
		if (to?.url?.pathname.startsWith(resolve('/items/'))) {
			savedScrollTop = document.getElementById('main-scroll')?.scrollTop ?? 0;
		}
	});

	afterNavigate(({ from }) => {
		if (from?.url?.pathname.startsWith(resolve('/items/'))) {
			const el = document.getElementById('main-scroll');
			if (el) el.scrollTop = savedScrollTop;
		}
	});
</script>

<svelte:head>
	<title>My items - Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<div class="flex items-center justify-between gap-4">
			<h1 class="font-heading text-3xl font-semibold tracking-tight">My items</h1>
			<Button onclick={() => goto(resolve('/items/new'))}>
				<Plus class="size-4" />
				New item
			</Button>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			<input
				use:focusRef
				onfocus={() => (searchFocused = true)}
				onblur={() => (searchFocused = false)}
				bind:value={searchInput}
				type="search"
				placeholder="Search your items…"
				class="flex h-9 min-w-0 flex-1 basis-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none sm:max-w-sm sm:basis-auto"
			/>
			<div class="ml-auto flex items-center gap-2">
				{#if showExampleFilter}
					<NativeSelect.Root
						size="sm"
						aria-label="Examples"
						value={exampleFilter}
						onchange={(e) => setExampleFilter(e.currentTarget.value as ExampleFilter)}
					>
						{#each exampleFilters as filter (filter)}
							<NativeSelect.Option value={filter}>
								{EXAMPLE_FILTER_LABELS[filter]}
							</NativeSelect.Option>
						{/each}
					</NativeSelect.Root>
				{/if}
				<div class="flex items-center gap-1">
					<button
						onclick={() => (viewMode = 'list')}
						class="relative rounded-md p-1.5 transition-colors after:absolute after:-inset-1.5 after:content-[''] {viewMode ===
						'list'
							? 'bg-muted text-foreground'
							: 'text-muted-foreground hover:text-foreground'}"
						aria-label="List view"
						aria-pressed={viewMode === 'list'}
					>
						<List class="size-4" />
					</button>
					<button
						onclick={() => (viewMode = 'grid')}
						class="relative rounded-md p-1.5 transition-colors after:absolute after:-inset-1.5 after:content-[''] {viewMode ===
						'grid'
							? 'bg-muted text-foreground'
							: 'text-muted-foreground hover:text-foreground'}"
						aria-label="Grid view"
						aria-pressed={viewMode === 'grid'}
					>
						<LayoutGrid class="size-4" />
					</button>
				</div>
			</div>
		</div>

		{#if allCategories.length > 1}
			<div class="flex flex-wrap gap-2">
				<Badge
					variant={selectedType === null ? 'default' : 'outline'}
					class="cursor-pointer"
					onclick={() => selectType(null)}
				>
					All
				</Badge>
				{#each allCategories as cat (cat.slug)}
					<Badge
						variant={selectedType === cat.slug ? 'default' : 'outline'}
						class="cursor-pointer"
						onclick={() => selectType(cat.slug)}
					>
						{cat.label}
					</Badge>
				{/each}
			</div>
		{/if}

		{#if loadingDisplay.show && shownItems.length === 0}
			<Shimmer loading={true}>
				{#if viewMode === 'grid'}
					<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
						{#each loadingSkeletons as skeleton (skeleton)}
							<div class="aspect-[3/4] animate-pulse rounded-xl bg-muted"></div>
						{/each}
					</div>
				{:else}
					<div class="grid gap-3">
						{#each loadingSkeletons as skeleton (skeleton)}
							<div class="rounded-lg border p-4">
								<div class="flex items-center justify-between gap-4">
									<div class="space-y-1">
										<div class="h-5 w-48 rounded bg-muted"></div>
										<div class="h-4 w-72 rounded bg-muted"></div>
									</div>
									<div class="h-6 w-16 rounded-full bg-muted"></div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</Shimmer>
		{:else if viewMode === 'grid'}
			<div
				data-slot="node-grid"
				class="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4"
			>
				{#each shownItems as item (item.id)}
					<NodeGridCard
						{item}
						schema={schemaOf(item.type)}
						categoryLabel={allCategories.find((c) => c.slug === item.type)?.label}
						match={q ? matchContext(item, schemaOf(item.type), q) : null}
						isExample={exampleItemIds.has(item.id)}
					/>
				{/each}
			</div>
		{:else}
			<Item.Group>
				{#each shownItems as item (item.id)}
					<NodeCard
						{item}
						schema={schemaOf(item.type)}
						categoryLabel={allCategories.find((c) => c.slug === item.type)?.label}
						match={q ? matchContext(item, schemaOf(item.type), q) : null}
						isExample={exampleItemIds.has(item.id)}
					/>
				{/each}
			</Item.Group>
		{/if}

		{#if items.length > 0 && shownItems.length === 0 && !loading && !hasMore}
			<div class="flex flex-col items-center gap-3 py-12 text-center">
				<EyeOff class="size-10 text-muted-foreground/50" />
				<p class="text-sm text-muted-foreground">
					{#if exampleFilter === 'only'}
						No example items match.
					{:else}
						{q || selectedType
							? 'Everything that matched is a hidden example.'
							: 'All your items are hidden examples.'} Choose All items to see them.
					{/if}
				</p>
				<Button variant="outline" size="sm" onclick={() => setExampleFilter('all')}>
					Show all items
				</Button>
			</div>
		{:else if items.length === 0 && !loading}
			<div class="flex flex-col items-center gap-3 py-12 text-center">
				{#if q}
					<SearchX class="size-10 text-muted-foreground/50" />
					<div>
						<p class="font-medium">Nothing matched "{q}"</p>
						<p class="text-sm text-muted-foreground">Try a different search term</p>
					</div>
					<Button variant="ghost" size="sm" onclick={() => (searchInput = '')}>Clear search</Button>
				{:else if selectedType}
					<LayoutGrid class="size-10 text-muted-foreground/50" />
					<div>
						<p class="font-medium">No {selectedTypeLabel} items yet</p>
						<p class="text-sm text-muted-foreground">
							Add one, or <button
								class="underline underline-offset-2 hover:text-foreground"
								onclick={() => selectType(null)}>clear this filter</button
							> to see everything.
						</p>
					</div>
					<Button size="sm" onclick={() => goto(resolve('/items/new'))}>
						<Plus class="size-4" />
						New item
					</Button>
				{:else}
					<LayoutGrid class="size-10 text-muted-foreground/50" />
					<div>
						<p class="font-medium">Nothing here yet</p>
						<p class="text-sm text-muted-foreground">Add your first item to get started</p>
					</div>
					<Button onclick={() => goto(resolve('/items/new'))}>
						<Plus class="size-4" />
						Add your first item
					</Button>
				{/if}
			</div>
		{/if}

		{#if hasMore}
			<div use:sentinel class="flex justify-center py-4" aria-hidden="true">
				{#if loading}
					<div
						class="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground"
					></div>
				{/if}
			</div>
		{/if}
	</div>
</main>
