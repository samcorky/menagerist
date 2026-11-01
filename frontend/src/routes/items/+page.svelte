<script lang="ts">
	import IconButton from '$lib/components/icon-button.svelte';
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import {
		collectionNameLookup,
		collectionRouteParams,
		fetchAllCollections
	} from '$lib/collections';
	import { page } from '$app/state';
	import { beforeNavigate, afterNavigate, goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import { untrack } from 'svelte';
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import {
		BookmarkPlus,
		EyeOff,
		List,
		Plus,
		SearchX,
		LayoutGrid,
		SlidersHorizontal,
		TriangleAlert
	} from '@lucide/svelte';
	import { captureController } from '$lib/capture.svelte.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { toast } from 'svelte-sonner';
	import type { CollectionResponse, NodeResponse, NodeTypeResponse } from '$lib/api/client';
	import { fetchAllNodeTypes } from '$lib/node-types';
	import { fetchItemFields, type ItemField } from '$lib/item-fields';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import QueryBuilder from '$lib/components/query-builder.svelte';
	import QueryChips from '$lib/components/query-chips.svelte';
	import SaveSmartCollectionDialog from '$lib/components/save-smart-collection-dialog.svelte';
	import { conditionNumbers, queryKey, type BuilderError } from '$lib/query/builder';
	import { ConnectionLookups } from '$lib/query/connection-lookups.svelte';
	import { buildCatalogue, summaryLookup } from '$lib/query/fields';
	import {
		combinePrefix,
		createFilterWriter,
		totalLine,
		INVALID_LINK_MESSAGE,
		loadItemsPage,
		readFilter,
		SEARCH_TOO_LONG_MESSAGE,
		searchTextIgnored,
		TOO_MANY_MESSAGE,
		usesSearch,
		withFilter,
		FILTER_PARAM
	} from '$lib/query/items-page';
	import { createCountTracker } from '$lib/query/search-count';
	import { combineWithSaved, narrowFilterCount, saveBlockReason } from '$lib/query/narrow';
	import { countConditions, emptyQuery, removeAt } from '$lib/query/tree';
	import {
		mapWarnings,
		pathKey,
		splitDetail,
		toFilterPath,
		type WarningMarks
	} from '$lib/query/warnings';
	import type { Path, Query } from '$lib/query/types';
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

	const loadingSkeletons = [1, 2, 3, 4, 5];

	// Persisted outside component so scroll position survives navigation
	let savedScrollTop = 0;

	let items = $state<NodeResponse[]>([]);
	let allCategories = $state<NodeTypeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(true);
	let selectedType = $state<string | null>(null);
	let fetchSeq = 0;
	const counts = createCountTracker();
	// Search paging: the next cursor, and the count the server reported.
	let cursor = $state<string | null>(null);
	let total = $state<number | null>(null);
	let totalCapped = $state(false);
	let marks = $state<WarningMarks>({ conditions: new Set(), messages: new Map(), sort: false });
	let filterError = $state<BuilderError | null>(null);
	let tooMany = $state(false);
	let filtersOpen = $state(false);
	let filtersFocus = $state<Path | null>(null);
	let saveOpen = $state(false);
	let filterAnnouncement = $state('');
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

	// The advanced filter lives in the URL (`?f=`).
	const filterParam = $derived(page.url.searchParams.get(FILTER_PARAM));
	const filterState = $derived(readFilter(filterParam));
	const filter = $derived(filterState.query);
	const filterKey = $derived(queryKey(filter));
	const searching = $derived(usesSearch(filter));
	const conditionCount = $derived(countConditions(filter));
	// What is on screen (filter, search box and type select) is what a smart collection saves
	const saveBasics = $derived({ q, type: selectedType });
	const saveQuery = $derived(combineWithSaved(emptyQuery(), filter, saveBasics));
	const saveReason = $derived(saveBlockReason(emptyQuery(), filter, saveBasics));
	const canSave = $derived(narrowFilterCount(filter, saveBasics) > 0);
	let categoriesLoaded = $state(false);
	let itemFields = $state<ItemField[] | null>(null);
	let collectionsFailed = $state(false);
	let allCollections = $state<{ id: string; name: string }[] | null>(null);
	const countLine = $derived(
		totalLine(total, totalCapped, { loading, appending: loading && items.length > 0 })
	);
	const catalogue = $derived(buildCatalogue(allCategories, categoriesLoaded, itemFields));
	const connections = new ConnectionLookups();
	const lookup = $derived(
		summaryLookup(catalogue, collectionNameLookup(allCollections), connections.summary)
	);
	$effect(() => connections.ensureFor(filter));
	const filterErrorText = $derived.by(() => {
		if (!filterError) return '';
		const n = filterError.path
			? conditionNumbers(filter).get(pathKey(filterError.path))
			: undefined;
		return n ? `Condition ${n}: ${filterError.message}` : filterError.message;
	});

	const writer = createFilterWriter((next: Query, replace: boolean) => {
		const search = withFilter(page.url.searchParams, next).toString();
		void goto(resolve(search ? `/items?${search}` : '/items'), {
			replaceState: replace,
			keepFocus: true,
			noScroll: true
		});
	});
	$effect(() => () => writer.cancel());

	$effect(() => {
		if (!filterState.invalid) return;
		untrack(() => {
			toast.error(INVALID_LINK_MESSAGE);
			const params = new SvelteURLSearchParams(page.url.searchParams);
			params.delete(FILTER_PARAM);
			const rest = params.toString();
			void goto(resolve(rest ? `/items?${rest}` : '/items'), {
				replaceState: true,
				keepFocus: true,
				noScroll: true
			});
		});
	});

	function openFilters(focus: Path | null) {
		filtersFocus = focus;
		writer.startSession();
		filtersOpen = true;
	}

	$effect(() => {
		if (!filtersOpen) writer.flush();
	});

	function savedAsSmart(collection: CollectionResponse) {
		void goto(resolve('/collections/[id]', collectionRouteParams(collection)));
	}

	function removeFilter(path: Path, text: string) {
		writer.startSession();
		writer.write(removeAt(filter, path));
		filterAnnouncement = `Filter removed: ${text}.`;
	}

	function clearFilters() {
		writer.startSession();
		writer.write(emptyQuery());
		filterAnnouncement = 'Filters cleared.';
	}

	$effect(() => {
		return registerShortcut({
			id: 'items-filters',
			keys: 'f',
			description: 'Open filters',
			group: 'Search',
			handler: (event) => {
				event.preventDefault();
				openFilters(null);
			}
		});
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

	async function fetchPage(more = false) {
		const seq = ++fetchSeq;
		if (!more) counts.cancel();
		loading = true;
		const basics = { type: selectedType, q };
		const result = await loadItemsPage({
			filter,
			basics,
			after: more && !searching ? items.at(-1)?.id : undefined,
			cursor: more && searching ? cursor : null
		});
		if (seq !== fetchSeq) return;
		if (result.status === 'ok') {
			items = more ? [...items, ...result.items] : result.items;
			hasMore = result.hasMore;
			cursor = result.cursor;
			// A further list page repeats the capped figure; keep the exact one already shown.
			if (!more || searching) {
				total = result.total;
				totalCapped = result.totalCapped;
			}
			if (!more && !searching && result.totalCapped) {
				void counts.run(basics, (exact) => {
					total = exact;
					totalCapped = false;
				});
			}
			marks = mapWarnings(result.warnings, result.prefix);
			filterError = null;
			tooMany = false;
		} else {
			hasMore = false;
			if (!more) items = [];
			tooMany = result.status === 'too-many';
			if (result.status === 'rejected') {
				const { target, message } = splitDetail(result.detail);
				const path =
					target && 'where' in target
						? toFilterPath(target.where, combinePrefix(filter, basics))
						: null;
				filterError = { message, path };
			} else filterError = null;
			if (result.status === 'failed') {
				toast.error(result.title, { description: result.description });
			}
		}
		loading = false;
	}

	// Quiet on failure: only the collection picker says so.
	async function loadCollections() {
		collectionsFailed = false;
		const all = await fetchAllCollections();
		allCollections = all;
		collectionsFailed = all === null;
	}

	async function fetchCategories() {
		// Neither call waits for the other: the slower listing must not hold up the type catalogue.
		await Promise.all([
			fetchAllNodeTypes().then((types) => {
				if (types) allCategories = types;
				categoriesLoaded = true;
			}),
			fetchItemFields().then((fields) => {
				itemFields = fields;
			}),
			loadCollections()
		]);
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
				if (entries[0].isIntersecting && hasMore && !loading) void fetchPage(true);
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
		untrack(() => {
			items = [];
			hasMore = true;
			cursor = null;
			void fetchPage();
		});
	});

	// Reload from the start whenever the type, the search box or the filter changes.
	$effect(() => {
		void [selectedType, q, filterKey];
		untrack(() => {
			items = [];
			hasMore = true;
			cursor = null;
			void fetchPage();
		});
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

<Page width="fluid">
	<div class="flex items-center justify-between gap-4">
		<h1 class="font-heading text-3xl font-semibold tracking-tight">My items</h1>
		<IconButton label="New item" variant="default" onclick={() => goto(resolve('/items/new'))}>
			<Plus />
		</IconButton>
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
			<Button
				variant="outline"
				class="max-sm:h-11"
				aria-haspopup="dialog"
				onclick={() => openFilters(null)}
			>
				<SlidersHorizontal />
				Filters
				{#if conditionCount > 0}
					<Badge class="ml-0.5 h-5 min-w-5 px-1.5 tabular-nums">
						{conditionCount}<span class="sr-only">
							{conditionCount === 1 ? 'condition' : 'conditions'}</span
						>
					</Badge>
				{/if}
			</Button>
			{#if showExampleFilter}
				<NativeSelect.Root
					size="sm"
					class="max-sm:[&_select[data-size]]:h-11"
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

	{#if conditionCount > 0 || searching}
		<div class="flex flex-col gap-3">
			<QueryChips
				query={filter}
				{lookup}
				warned={marks.conditions}
				warnedMessages={marks.messages}
				{catalogue}
				onopen={(path) => openFilters(path)}
				onremove={removeFilter}
				onclear={clearFilters}
			/>
			{#if filterError}
				<Alert.Root variant="destructive">
					<TriangleAlert />
					<Alert.Title>This filter can't be used</Alert.Title>
					<Alert.Description>
						{filterErrorText}
						<Button
							variant="link"
							class="h-auto p-0"
							onclick={() => openFilters(filterError?.path ?? null)}>Edit filters</Button
						>
					</Alert.Description>
				</Alert.Root>
			{:else if tooMany}
				<Alert.Root>
					<TriangleAlert />
					<Alert.Description>{TOO_MANY_MESSAGE}</Alert.Description>
				</Alert.Root>
			{:else if countLine}
				<p class="text-sm text-muted-foreground">{countLine}</p>
			{/if}
			{#if searchTextIgnored(filter, q)}
				<p class="text-sm text-muted-foreground">{SEARCH_TOO_LONG_MESSAGE}</p>
			{/if}
		</div>
	{:else if countLine}
		<p class="text-sm text-muted-foreground">{countLine}</p>
	{/if}
	{#if canSave}
		<div class="flex flex-col items-start gap-1.5">
			<IconButton
				label="Save as smart collection"
				variant="outline"
				aria-haspopup="dialog"
				disabled={saveReason !== null}
				aria-describedby={saveReason ? 'save-smart-reason' : undefined}
				onclick={() => (saveOpen = true)}
			>
				<BookmarkPlus />
			</IconButton>
			{#if saveReason}
				<p id="save-smart-reason" class="text-sm text-muted-foreground">{saveReason}</p>
			{/if}
		</div>
	{/if}
	<p class="sr-only" role="status" aria-live="polite">{filterAnnouncement}</p>

	{#if loadingDisplay.show && shownItems.length === 0}
		<Shimmer loading={true}>
			{#if viewMode === 'grid'}
				<div class="grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-2">
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
		<div data-slot="node-grid" class="grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-2">
			{#each shownItems as item (item.id)}
				<NodeGridCard
					{item}
					schema={schemaOf(item.type)}
					categoryLabel={allCategories.find((c) => c.slug === item.type)?.label}
					typeIcon={allCategories.find((c) => c.slug === item.type)?.icon}
					typeColour={allCategories.find((c) => c.slug === item.type)?.colour}
					match={q ? matchContext(item, schemaOf(item.type), q) : null}
					isExample={exampleItemIds.has(item.id)}
				/>
			{/each}
		</div>
	{:else}
		<Item.Group class="max-w-5xl">
			{#each shownItems as item (item.id)}
				<NodeCard
					{item}
					schema={schemaOf(item.type)}
					categoryLabel={allCategories.find((c) => c.slug === item.type)?.label}
					typeIcon={allCategories.find((c) => c.slug === item.type)?.icon}
					typeColour={allCategories.find((c) => c.slug === item.type)?.colour}
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
	{:else if items.length === 0 && !loading && !filterError && !tooMany}
		<div class="flex flex-col items-center gap-3 py-12 text-center">
			{#if searching && conditionCount > 0}
				<SearchX class="size-10 text-muted-foreground/50" />
				<div>
					<p class="font-medium">No items match these filters</p>
					<p class="text-sm text-muted-foreground">
						Change a condition, or clear the filters to see everything.
					</p>
				</div>
				<Button variant="ghost" size="sm" onclick={clearFilters}>Clear filters</Button>
			{:else if q}
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
</Page>

<SaveSmartCollectionDialog bind:open={saveOpen} query={saveQuery} onsaved={savedAsSmart} />

<QueryBuilder
	bind:open={filtersOpen}
	query={filter}
	{catalogue}
	collections={allCollections}
	{collectionsFailed}
	onretrycollections={() => void loadCollections()}
	{connections}
	warned={marks.conditions}
	warnedMessages={marks.messages}
	sortWarned={marks.sort}
	error={filterError}
	notice={tooMany ? TOO_MANY_MESSAGE : null}
	focus={filtersFocus}
	onchange={(next, { debounce }) => writer.write(next, { debounce })}
/>
