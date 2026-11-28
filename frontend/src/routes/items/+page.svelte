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
		ListChecks,
		Plus,
		SearchX,
		LayoutGrid,
		SlidersHorizontal,
		TriangleAlert,
		Upload
	} from '@lucide/svelte';
	import { captureController } from '$lib/capture.svelte.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import NodeSkeleton from '$lib/components/node-skeleton.svelte';
	import ListFoot from '$lib/components/list-foot.svelte';
	import { toast } from 'svelte-sonner';
	import type { CollectionResponse, NodeResponse, NodeTypeResponse } from '$lib/api/client';
	import { cachedItemTypes, refreshItemTypes } from '$lib/palette-sources';
	import { fetchItemFields, fetchSavedFields, type ItemField } from '$lib/item-fields';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import QueryBuilder from '$lib/components/query-builder.svelte';
	import QueryChips from '$lib/components/query-chips.svelte';
	import SaveSmartCollectionDialog from '$lib/components/save-smart-collection-dialog.svelte';
	import { conditionNumbers, queryKey, type BuilderError } from '$lib/query/builder';
	import { ConnectionLookups } from '$lib/query/connection-lookups.svelte';
	import { buildCatalogue, summaryLookup, type SavedField } from '$lib/query/fields';
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
		FILTER_PARAM,
		type PageBasics
	} from '$lib/query/items-page';
	import { PagedList, type PageRequest } from '$lib/paged-list.svelte';
	import type { PageResult } from '$lib/paging';
	import { createCountTracker } from '$lib/query/search-count';
	import { combineWithSaved, narrowFilterCount, saveBlockReason } from '$lib/query/narrow';
	import { countConditions, emptyQuery, removeAt } from '$lib/query/tree';
	import { pickEmptyLine } from '$lib/empty-lines';
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
	import LoadFailed from '$lib/components/load-failed.svelte';
	import { offlineController } from '$lib/offline.svelte.js';
	import * as Item from '$lib/components/ui/item/index.js';
	import NodeCard from '$lib/components/node-card.svelte';
	import NodeGridCard from '$lib/components/node-grid-card.svelte';
	import BulkToolbar from '$lib/components/bulk-toolbar.svelte';
	import { auth } from '$lib/auth.svelte.js';
	import { PendingDeletes } from '$lib/pending-deletes.svelte';
	import { Selection } from '$lib/selection.svelte';
	import { leavesPage, SELECTION_FULL_MESSAGE } from '$lib/bulk-actions';
	import type { AttributesSchema } from '$lib/schema-types';
	import { effectiveSchema } from '$lib/node-types';
	import {
		EXAMPLE_FILTER_LABELS,
		loadExampleIds,
		readExampleFilter,
		visibleItems,
		writeExampleFilter,
		type ExampleFilter
	} from '$lib/examples';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import { CUSTOM_SORT, SORT_CHOICES, sortChoiceOf, withSortChoice } from '$lib/query/sort-choices';
	import { inFamilyOrder, typeNames } from '$lib/type-names';
	import { appearanceOf } from '$lib/type-inheritance';
	import { matchContext } from '$lib/search-context';
	import { normaliseQuery } from '$lib/search-palette';
	import { registerShortcut } from '$lib/shortcuts.svelte';

	const EMPTY_LINES = [
		'Your menagerie is quiet... too quiet.',
		'Nothing here yet. Even the Tribbles are elsewhere.',
		'An empty shelf is just a collection waiting to happen.',
		'Space: the final frontier. Shelves: the first one.',
		'No items detected. Scanning for signs of life...'
	];
	// Stable for this page within a session (hashed from the path, not the filters).
	const emptyLine = $derived(pickEmptyLine(EMPTY_LINES, page.url.pathname));

	// The foot of a long list, in the same spirit (#588). The count goes beside it.
	const END_LINES = [
		"That's your whole menagerie.",
		'You have reached the end of the shelf.',
		'Scanning complete. No further signs of life.',
		'The last of them. Live long and catalogue.'
	];

	// What the list is read for: the filter, and the page's own type and search box.
	type ItemsRead = { filter: Query; basics: PageBasics };

	// Persisted outside component so scroll position survives navigation
	let savedScrollTop = 0;

	// Starts from the list the session already holds, so cards draw with their type's icon at once.
	let allCategories = $state<NodeTypeResponse[]>(cachedItemTypes() ?? []);
	let selectedType = $state<string | null>(null);
	let fetchSeq = 0;
	const counts = createCountTracker();
	let totalCapped = $state(false);
	let marks = $state<WarningMarks>({ conditions: new Set(), messages: new Map(), sort: false });
	let filterError = $state<BuilderError | null>(null);
	let tooMany = $state(false);
	// The list reads a page at a time through the server's cursor, from the plain list or, with a
	// filter or a sort, from the search (`readItems`). It owns the rows and the paging state.
	const list = new PagedList<NodeResponse, ItemsRead>(readItems);
	const items = $derived(list.rows);
	const loading = $derived(list.loading);
	// The read in flight is a further page, not a new search, sort or filter.
	const loadingMore = $derived(list.loadingMore);
	const hasMore = $derived(list.hasMore);
	const total = $derived(list.total);
	// The first page could not be fetched: shown as a failure with Retry, never as an empty list.
	const loadFailed = $derived(list.failed);
	// A later page that would not load: the list's foot says so and offers Try again (#588).
	const pageFailed = $derived(list.nextFailed);
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

	// Bulk selection: kept across searches and filters, ended with the page.
	const selection = new Selection({ onlimit: () => toast.info(SELECTION_FULL_MESSAGE) });
	const pendingDeletes = new PendingDeletes();
	const canSelect = $derived(auth.can('graph:item:write'));
	const rows = $derived(shownItems.filter((item) => !pendingDeletes.hidden.has(item.id)));
	const rowIds = $derived(rows.map((item) => item.id));
	// A search, sort or filter is being read while the old rows stay: they dim instead of vanishing.
	const reloading = $derived(loading && !loadingMore && rows.length > 0);
	// Select stays put while a search or sort reloads the list, so the toolbar does not jump; it
	// goes only if the result that comes back is empty.
	let hadRows = $state(false);
	$effect(() => {
		if (rows.length > 0) hadRows = true;
	});
	const showSelect = $derived(canSelect && (rows.length > 0 || (loading && hadRows)));

	function pick(id: string) {
		selection.enter();
		selection.toggle(id);
	}

	// What the list is asked for: the filter, and the page's own type and search box.
	const readParams = (): ItemsRead => ({ filter, basics: { type: selectedType, q } });

	async function reloadList() {
		await list.load(readParams(), { keepRows: true });
	}
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
	let savedFields = $state<SavedField[] | null>(null);
	let collectionsFailed = $state(false);
	let allCollections = $state<{ id: string; name: string }[] | null>(null);
	const countLine = $derived(
		totalLine(total, totalCapped, { loading, appending: loading && items.length > 0 })
	);
	// The end-of-list count. The server's figure counts every item it matched, so it cannot
	// stand for a list the Examples filter has hidden rows from: there the rows are counted.
	const countableTotal = $derived(totalCapped || shownItems.length !== items.length ? null : total);
	const catalogue = $derived(
		buildCatalogue(allCategories, categoriesLoaded, itemFields, savedFields)
	);
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

	// The order is the sort the Filters dialog edits, so the two never disagree.
	const sortChoice = $derived(sortChoiceOf(filter.sort));

	function setSort(value: string) {
		writer.startSession();
		writer.write(withSortChoice(filter, value));
	}

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

	const typeName = $derived(typeNames(allCategories));
	let selectedTypeLabel = $derived(selectedType ? typeName.path(selectedType) : selectedType);

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

	// The selected type lives in the URL (`?type=`), so dashboard chips, the back button and a
	// reload all agree with the chips here. Only the URL is tracked: reading `selectedType` would
	// re-run this on every click and write the old URL value straight back.
	$effect(() => {
		const typeParam = page.url.searchParams.get('type');
		untrack(() => {
			if (typeParam === selectedType) return;
			selectedType = typeParam;
		});
	});

	$effect(() => {
		const value = searchInput;
		const timer = setTimeout(() => {
			if (value === q) return;
			q = value;
		}, 300);
		return () => clearTimeout(timer);
	});

	async function readItems({
		after,
		params
	}: PageRequest<ItemsRead>): Promise<PageResult<NodeResponse>> {
		const seq = ++fetchSeq;
		const more = after !== undefined;
		if (!more) counts.cancel();
		const result = await loadItemsPage({
			filter: params.filter,
			basics: params.basics,
			cursor: after ?? null
		});
		// A newer read has started: the list drops this one, and so must what it would set here.
		const current = seq === fetchSeq;
		if (result.status === 'ok') {
			const plainList = !usesSearch(params.filter);
			if (current) {
				// A further list page repeats the capped figure; keep the exact one already shown.
				if (!more || !plainList) totalCapped = result.totalCapped;
				if (!more && plainList && result.totalCapped) {
					void counts.run(params.basics, (exact) => {
						list.total = exact;
						totalCapped = false;
					});
				}
				marks = mapWarnings(result.warnings, result.prefix);
				filterError = null;
				tooMany = false;
			}
			return {
				data: result.items,
				cursor: result.cursor,
				total: !more || !plainList ? result.total : list.total
			};
		}
		// A page that would not load is the list's failure: the first page, or a later one the
		// foot offers Try again for (#588).
		if (result.status === 'failed') return { error: result };
		if (current) {
			tooMany = result.status === 'too-many';
			if (result.status === 'rejected') {
				const { target, message } = splitDetail(result.detail);
				const path =
					target && 'where' in target
						? toFilterPath(target.where, combinePrefix(params.filter, params.basics))
						: null;
				filterError = { message, path };
			} else filterError = null;
		}
		return { data: [], cursor: null, total: null };
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
			// Refreshed in the background; a failed refresh keeps the list already shown.
			refreshItemTypes().then(
				(types) => {
					allCategories = types;
					categoriesLoaded = true;
				},
				() => {
					categoriesLoaded = true;
				}
			),
			fetchItemFields().then((fields) => {
				itemFields = fields;
			}),
			fetchSavedFields().then((fields) => {
				savedFields = fields;
			}),
			loadCollections()
		]);
	}

	function schemaOf(slug: string | null | undefined): AttributesSchema | null {
		return effectiveSchema(allCategories.find((c) => c.slug === slug));
	}

	function selectType(type: string | null) {
		if (selectedType === type) return;
		selectedType = type;
		const params = new SvelteURLSearchParams(page.url.searchParams);
		if (type) params.set('type', type);
		else params.delete('type');
		const search = params.toString();
		void goto(resolve(search ? `/items?${search}` : '/items'), {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
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
		untrack(() => void list.load(readParams(), { keepRows: true }));
	});

	// Reload from the start whenever the type, the search box or the filter changes.
	$effect(() => {
		void [selectedType, q, filterKey];
		untrack(() => void list.load(readParams(), { keepRows: true }));
	});

	$effect(() => {
		void fetchCategories();
	});

	// Coming back online, or Retry in the banner, reloads a list that had failed.
	$effect(() => {
		void offlineController.retryCount;
		untrack(() => {
			if (loadFailed) void list.retry();
		});
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
	beforeNavigate((nav) => {
		// Leaving commits a delete still inside its Undo window (§14); a search or filter change
		// only rewrites this page's URL, so it must not.
		if (leavesPage(nav)) void pendingDeletes.flushAll();
		const to = nav.to;
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
		<div class="flex items-center gap-1">
			<IconButton
				label="Import from a CSV"
				labelOnTouch={false}
				onclick={() => goto(resolve('/items/import'))}
			>
				<Upload />
			</IconButton>
			<IconButton label="New item" variant="default" onclick={() => goto(resolve('/items/new'))}>
				<Plus />
			</IconButton>
		</div>
	</div>

	<div class="flex flex-wrap items-center gap-2">
		<input
			use:focusRef
			onfocus={() => (searchFocused = true)}
			onblur={() => (searchFocused = false)}
			bind:value={searchInput}
			type="search"
			placeholder="Search your items…"
			class="flex h-9 min-w-0 flex-1 basis-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none sm:max-w-sm sm:basis-auto md:text-sm"
		/>
		<div class="ml-auto flex flex-wrap items-center justify-end gap-2">
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
							{conditionCount === 1 ? 'condition' : 'conditions'}
						</span>
					</Badge>
				{/if}
			</Button>
			<NativeSelect.Root
				size="sm"
				class="shrink-0 max-sm:[&_select[data-size]]:h-11"
				aria-label="Sort by"
				value={sortChoice}
				onchange={(e) => setSort(e.currentTarget.value)}
			>
				{#each SORT_CHOICES as choice (choice.value)}
					<NativeSelect.Option value={choice.value}>{choice.label}</NativeSelect.Option>
				{/each}
				{#if sortChoice === CUSTOM_SORT}
					<NativeSelect.Option value={CUSTOM_SORT} disabled>Custom sort</NativeSelect.Option>
				{/if}
			</NativeSelect.Root>
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
			{#if showSelect}
				<Button
					variant={selection.active ? 'secondary' : 'outline'}
					class="max-sm:h-11"
					aria-pressed={selection.active}
					onclick={() => (selection.active ? selection.exit() : selection.enter())}
				>
					<ListChecks />
					Select
				</Button>
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
			{#each inFamilyOrder(allCategories) as cat (cat.slug)}
				<Badge
					variant={selectedType === cat.slug ? 'default' : 'outline'}
					class="cursor-pointer"
					onclick={() => selectType(cat.slug)}
				>
					{typeName.path(cat.slug)}
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
							onclick={() => openFilters(filterError?.path ?? null)}
						>
							Edit filters
						</Button>
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

	{#if selection.active}
		<BulkToolbar
			{selection}
			pending={pendingDeletes}
			visibleIds={rowIds}
			canCollect={auth.can('collections:collection:write')}
			onreload={reloadList}
		/>
	{/if}

	{#if loadingDisplay.show && shownItems.length === 0}
		<NodeSkeleton view={viewMode} count={8} />
	{:else if viewMode === 'grid'}
		<div
			data-slot="node-grid"
			aria-busy={reloading}
			class="grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-2 transition-opacity {reloading
				? 'opacity-60'
				: ''}"
		>
			{#each rows as item (item.id)}
				<NodeGridCard
					{item}
					selectable={selection.active}
					selected={selection.has(item.id)}
					onselect={() => selection.toggle(item.id)}
					onlongpress={canSelect && !selection.active ? () => pick(item.id) : undefined}
					schema={schemaOf(item.type)}
					categoryLabel={allCategories.find((c) => c.slug === item.type)?.label}
					categoryParent={typeName.parentOf(item.type)?.label}
					typeIcon={appearanceOf(item.type, allCategories).icon}
					typeColour={appearanceOf(item.type, allCategories).colour}
					match={q ? matchContext(item, schemaOf(item.type), q) : null}
					isExample={exampleItemIds.has(item.id)}
				/>
			{/each}
		</div>
	{:else}
		<Item.Group
			class="max-w-5xl transition-opacity {reloading ? 'opacity-60' : ''}"
			aria-busy={reloading}
		>
			{#each rows as item (item.id)}
				<NodeCard
					{item}
					selectable={selection.active}
					selected={selection.has(item.id)}
					onselect={() => selection.toggle(item.id)}
					onlongpress={canSelect && !selection.active ? () => pick(item.id) : undefined}
					schema={schemaOf(item.type)}
					categoryLabel={allCategories.find((c) => c.slug === item.type)?.label}
					categoryParent={typeName.parentOf(item.type)?.label}
					typeIcon={appearanceOf(item.type, allCategories).icon}
					typeColour={appearanceOf(item.type, allCategories).colour}
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
	{:else if loadFailed}
		<LoadFailed what="your items" onretry={() => void list.retry()} />
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
							onclick={() => selectType(null)}
						>
							clear this filter
						</button> to see everything.
					</p>
				</div>
				<Button size="sm" onclick={() => goto(resolve('/items/new'))}>
					<Plus class="size-4" />
					New item
				</Button>
			{:else}
				<LayoutGrid class="size-10 text-muted-foreground/50" />
				<div>
					<p class="font-medium" data-testid="empty-line">{emptyLine}</p>
					<p class="text-sm text-muted-foreground">Add your first item to get started</p>
				</div>
				<Button onclick={() => goto(resolve('/items/new'))}>
					<Plus class="size-4" />
					Add your first item
				</Button>
			{/if}
		</div>
	{/if}

	<ListFoot
		{loading}
		{hasMore}
		failed={pageFailed}
		rows={shownItems.length}
		total={countableTotal}
		noun="item"
		lines={END_LINES}
		lineKey={page.url.pathname}
		onload={() => void list.loadMore()}
		onretry={() => void list.retry()}
	/>
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
