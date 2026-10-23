<script lang="ts">
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import {
		EyeOff,
		LayoutGrid,
		Library,
		List,
		Pencil,
		Plus,
		SlidersHorizontal,
		TriangleAlert,
		SearchX,
		Trash2,
		X
	} from '@lucide/svelte';
	import { tick, untrack } from 'svelte';
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';
	import {
		addItemsToCollection,
		deleteCollection,
		getCollection,
		listNodes,
		removeItemFromCollection,
		updateCollection,
		type CollectionResponse,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { fetchAllNodeTypes } from '$lib/node-types';
	import { fetchItemFields, type ItemField } from '$lib/item-fields';
	import NarrowedBar from '$lib/components/narrowed-bar.svelte';
	import QueryBuilder from '$lib/components/query-builder.svelte';
	import QueryChips from '$lib/components/query-chips.svelte';
	import SaveSmartCollectionDialog from '$lib/components/save-smart-collection-dialog.svelte';
	import SmartConditions from '$lib/components/smart-conditions.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { conditionNumbers, queryKey, type BuilderError } from '$lib/query/builder';
	import { parseQuery } from '$lib/query/codec';
	import { buildCatalogue, summaryLookup } from '$lib/query/fields';
	import {
		FILTER_PARAM,
		INVALID_LINK_MESSAGE,
		createFilterWriter,
		readFilter,
		withFilter
	} from '$lib/query/items-page';
	import {
		NARROW_TOO_LARGE_MESSAGE,
		linkedBlockReason,
		linkedNarrow,
		locateInCombined,
		narrowFilterCount,
		narrowedBarText,
		narrowedMarks,
		needsNarrowing,
		combineWithSaved,
		saveBlockReason,
		updateConfirmation
	} from '$lib/query/narrow';
	import { SearchError, type SearchWarning } from '$lib/query/search';
	import { countConditions, emptyQuery, removeAt } from '$lib/query/tree';
	import type { Path, Query } from '$lib/query/types';
	import { mapWarnings, pathKey, splitDetail } from '$lib/query/warnings';
	import {
		SmartCollectionError,
		describeSaveError,
		isSmart,
		loadSmartCollection,
		updateDefinition
	} from '$lib/smart-collections';
	import {
		MAX_COLLECTION_NAME_LENGTH,
		addItemsErrorMessage,
		canonicalSlugFor,
		collectionAddress,
		collectionNameLookup,
		collectionRouteParams,
		collectionSaveErrorMessage,
		fetchAllCollections,
		slugPatch,
		slugSaveErrorMessage,
		validateCollectionName
	} from '$lib/collections';
	import AddItemsDialog from '$lib/components/add-items-dialog.svelte';
	import CollectionCount from '$lib/components/collection-count.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import CollectionSlugField from '$lib/components/collection-slug-field.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import NodeCard from '$lib/components/node-card.svelte';
	import NodeGridCard from '$lib/components/node-grid-card.svelte';
	import NotFound from '$lib/components/not-found.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Item from '$lib/components/ui/item/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import {
		EXAMPLE_FILTER_LABELS,
		loadExampleIds,
		readExampleFilter,
		visibleItems,
		writeExampleFilter,
		type ExampleFilter
	} from '$lib/examples';
	import type { AttributesSchema } from '$lib/schema-types';
	import { matchContext } from '$lib/search-context';

	const PAGE_SIZE = 50;
	const SMART_EXPLANATION = 'Items are added automatically by the conditions.';
	const EDIT_CONDITIONS_DESCRIPTION =
		'Change the saved conditions, then choose Save. Cancel discards your changes.';
	const loadingSkeletons = [1, 2, 3, 4, 5];

	// The address segment: an id or a slug. Item queries need the canonical id.
	const collectionId = $derived(page.params.id ?? '');

	let collection = $state<CollectionResponse | null>(null);
	const canonicalId = $derived(collection?.id ?? '');
	// The first page of results has arrived; the exact count waits for it
	let firstPageLoaded = $state(false);
	let headerLoading = $state(true);
	let notFound = $state(false);
	let loadFailed = $state(false);

	let items = $state<NodeResponse[]>([]);
	let itemTypes = $state<NodeTypeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(false);
	let itemsFailed = $state(false);
	let fetchSeq = 0;
	let collectionSeq = 0;
	let searchInput = $state('');
	let q = $state('');
	let selectedType = $state('');
	let viewMode = $state<'list' | 'grid'>('list');
	let exampleCollectionIds = $state<ReadonlySet<string>>(new Set());
	let exampleItemIds = $state<ReadonlySet<string>>(new Set());
	let exampleFilter = $state<ExampleFilter>(readExampleFilter());
	const showExampleFilter = $derived(exampleItemIds.size > 0 || exampleFilter !== 'all');
	const shownItems = $derived(visibleItems(items, exampleItemIds, exampleFilter));
	const exampleFilters = Object.keys(EXAMPLE_FILTER_LABELS) as ExampleFilter[];

	// Smart collections: the kind decides how results load, so nothing loads until it is known.
	const collectionKind = $derived(collection ? collection.kind : null);
	const smart = $derived(collection ? isSmart(collection) : false);
	const storedQuery = $derived(collection && smart ? parseQuery(collection.definition) : null);
	const unreadable = $derived(smart && storedQuery === null);
	let smartCursor = $state<string | null>(null);
	let smartWarnings = $state<SearchWarning[]>([]);
	let typesLoaded = $state(false);
	let itemFields = $state<ItemField[] | null>(null);
	let conditionsOpen = $state(false);
	let wasConditionsOpen = false;
	let draft = $state<Query | null>(null);
	let conditionsSaving = $state(false);
	let conditionsError = $state<BuilderError | null>(null);
	const catalogue = $derived(buildCatalogue(itemTypes, typesLoaded, itemFields));
	let collectionsFailed = $state(false);
	let allCollections = $state<CollectionResponse[] | null>(null);
	const lookup = $derived(summaryLookup(catalogue, collectionNameLookup(allCollections)));
	const builderQuery = $derived(draft ?? storedQuery ?? emptyQuery());

	// Ad-hoc narrowing of a smart collection: filters (`?f=`), search (`?q=`) and type (`?type=`)
	// live in the URL and are ANDed onto the saved conditions. The saved definition is untouched.
	const adhocState = $derived(
		smart
			? readFilter(page.url.searchParams.get(FILTER_PARAM))
			: { query: emptyQuery(), invalid: false }
	);
	const adhoc = $derived(adhocState.query);
	const adhocKey = $derived(queryKey(adhoc));
	const adhocCount = $derived(countConditions(adhoc));
	const basics = $derived({ q, type: selectedType || null });
	const narrowCount = $derived(narrowFilterCount(adhoc, basics));
	const narrowed = $derived(smart && storedQuery !== null && needsNarrowing(adhoc, basics));
	const storedKey = $derived(storedQuery ? queryKey(storedQuery) : '');
	const combinedQuery = $derived(combineWithSaved(storedQuery ?? emptyQuery(), adhoc, basics));
	const blockReason = $derived(
		narrowed && storedQuery ? saveBlockReason(storedQuery, adhoc, basics) : null
	);
	// "Save as new, linked": `in collection <this>` plus the filters, search text and type.
	const linkedQuery = $derived(linkedNarrow(canonicalId, adhoc, basics));
	const linkedReason = $derived(linkedBlockReason(canonicalId, adhoc, basics));
	// A manual collection narrows by search text and type only, and offers only the linked save.
	const manualNarrowed = $derived(
		!!collection && !smart && (q.trim() !== '' || selectedType !== '')
	);
	const manualBarText = $derived(
		narrowedBarText(narrowFilterCount(emptyQuery(), basics), null, {
			count: collection?.item_count ?? 0,
			capped: collection?.item_count_capped ?? false
		})
	);
	let narrowedTotal = $state<{ total: number; capped: boolean } | null>(null);
	let searchWarnings = $state<SearchWarning[]>([]);
	let tooLarge = $state(false);
	let adhocError = $state<BuilderError | null>(null);
	let filtersOpen = $state(false);
	let filtersFocus = $state<Path | null>(null);
	let saveOpen = $state(false);
	let linkedOpen = $state(false);
	let updateOpen = $state(false);
	let updating = $state(false);
	let updateError = $state<string | null>(null);
	let filterAnnouncement = $state('');
	// The last search text and type seen in, or written to, the URL
	let appliedQ = '';
	let appliedType = '';
	const savedWarnings = $derived(narrowed ? (collection?.warnings ?? []) : smartWarnings);
	const sortWarned = $derived(mapWarnings(savedWarnings).sort);
	const adhocMarks = $derived(
		narrowed && storedQuery
			? narrowedMarks(searchWarnings, storedQuery, adhoc, basics)
			: { conditions: new Set<string>(), sort: false }
	);
	const barText = $derived(
		narrowedBarText(narrowCount, tooLarge || adhocError ? null : narrowedTotal, {
			count: collection?.item_count ?? 0,
			capped: collection?.item_count_capped ?? false
		})
	);
	const adhocErrorText = $derived.by(() => {
		if (!adhocError) return '';
		const n = adhocError.path ? conditionNumbers(adhoc).get(pathKey(adhocError.path)) : undefined;
		return n ? `Condition ${n}: ${adhocError.message}` : adhocError.message;
	});

	let editOpen = $state(false);
	let editName = $state('');
	let editSlug = $state('');
	let slugError = $state<string | null>(null);
	let regenerating = $state(false);
	let editDescription = $state('');
	let editTouched = $state(false);
	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let editTrigger: HTMLElement | null = null;
	let conditionsTrigger: HTMLElement | null = null;

	let removingId = $state<string | null>(null);
	let addOpen = $state(false);
	let addTrigger: HTMLElement | null = null;
	let headerAddButton = $state<HTMLElement | null>(null);
	const showTypeFilter = $derived(itemTypes.length > 0 || selectedType !== '');
	const typeLabels = $derived(Object.fromEntries(itemTypes.map((t) => [t.slug, t.label])));

	let confirmDelete = $state(false);
	let deleting = $state(false);
	let deleteTrigger: HTMLElement | null = null;

	const nameHint = $derived(validateCollectionName(editName));
	const showNameHint = $derived(editTouched && nameHint !== null);
	// The server rebuilds the slug from the saved name, so an unsaved rename must be saved first
	const nameUnsaved = $derived(collection !== null && editName.trim() !== collection.name);

	// §13a: don't flash a skeleton for loads under 300ms
	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading || headerLoading);
	});

	function setExampleFilter(filter: ExampleFilter) {
		exampleFilter = filter;
		writeExampleFilter(filter);
	}

	$effect(() => {
		void loadExampleIds().then((ids) => {
			exampleItemIds = ids.items;
			exampleCollectionIds = ids.collections;
		});
	});

	$effect(() => {
		void fetchAllNodeTypes().then((types) => {
			if (types) itemTypes = types;
			typesLoaded = true;
		});
	});

	// Shares the items page's view preference
	$effect(() => {
		if (browser) {
			const stored = localStorage.getItem('items-view');
			if (stored === 'grid' || stored === 'list') viewMode = stored;
		}
	});

	$effect(() => {
		if (browser) localStorage.setItem('items-view', viewMode);
	});

	$effect(() => {
		const value = searchInput;
		const timer = setTimeout(() => {
			if (value === q) return;
			items = [];
			hasMore = false;
			q = value;
		}, 300);
		return () => clearTimeout(timer);
	});

	function selectType(slug: string) {
		if (slug === selectedType) return;
		items = [];
		hasMore = false;
		selectedType = slug;
	}

	function schemaOf(slug: string | null | undefined): AttributesSchema | null {
		const type = itemTypes.find((t) => t.slug === slug);
		return (type?.attributes_schema as AttributesSchema | null | undefined) ?? null;
	}

	// `id` is the address segment on the first load, then always the canonical id, so the ETag
	// cache key is `/collection/<uuid>` for every later call. `quiet` keeps the skeleton away.
	async function loadCollection(id: string, quiet = false) {
		const seq = ++collectionSeq;
		if (!quiet) headerLoading = true;
		notFound = false;
		loadFailed = false;
		const result = await getCollection({ path: { collection_id: id } });
		if (seq !== collectionSeq) return;
		if (id !== collectionId && id !== collection?.id) {
			headerLoading = false;
			return;
		}
		if (result.response?.status === 404) {
			notFound = true;
			collection = null;
		} else if (result.error || !result.data) {
			// A background reload that fails leaves the page as it was
			if (!quiet) {
				loadFailed = true;
				collection = null;
			}
		} else {
			collection = result.data;
			showCanonicalAddress(result.data);
			// Reload once by id so later ETags are keyed by id, not by the slug just used
			if (id !== result.data.id) void loadCollection(result.data.id, true);
		}
		headerLoading = false;
	}

	// Replaces an id (or an old slug) in the address with the slug, without a history entry.
	function showCanonicalAddress(loaded: CollectionResponse) {
		if (canonicalSlugFor(collectionId, loaded) === null) return;
		void goto(resolve(collectionAddress(loaded, page.url)), {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	}

	function navigateWith(params: URLSearchParams, replace: boolean) {
		if (!collection) return;
		const search = params.toString();
		const address = collectionAddress(collection, {
			search: search ? `?${search}` : '',
			hash: page.url.hash
		});
		void goto(resolve(address), { replaceState: replace, keepFocus: true, noScroll: true });
	}

	const writer = createFilterWriter((next: Query, replace: boolean) =>
		navigateWith(withFilter(page.url.searchParams, next), replace)
	);
	$effect(() => () => writer.cancel());

	$effect(() => {
		if (!adhocState.invalid) return;
		untrack(() => {
			toast.error(INVALID_LINK_MESSAGE);
			const params = new SvelteURLSearchParams(page.url.searchParams);
			params.delete(FILTER_PARAM);
			navigateWith(params, true);
		});
	});

	// The search box and the type select follow the URL (Back, a shared link) and write to it.
	$effect(() => {
		if (!smart) return;
		const urlQ = page.url.searchParams.get('q') ?? '';
		const urlType = page.url.searchParams.get('type') ?? '';
		untrack(() => {
			if (urlQ !== appliedQ) {
				appliedQ = urlQ;
				if (urlQ !== q) {
					items = [];
					hasMore = false;
					q = urlQ;
				}
				searchInput = urlQ;
			}
			if (urlType !== appliedType) {
				appliedType = urlType;
				if (urlType !== selectedType) {
					items = [];
					hasMore = false;
					selectedType = urlType;
				}
			}
		});
	});

	$effect(() => {
		if (!smart) return;
		const nextQ = q;
		const nextType = selectedType;
		untrack(() => {
			if (nextQ === appliedQ && nextType === appliedType) return;
			appliedQ = nextQ;
			appliedType = nextType;
			const params = new SvelteURLSearchParams(page.url.searchParams);
			if (nextQ) params.set('q', nextQ);
			else params.delete('q');
			if (nextType) params.set('type', nextType);
			else params.delete('type');
			navigateWith(params, true);
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

	function removeFilter(path: Path, text: string) {
		writer.startSession();
		writer.write(removeAt(adhoc, path));
		filterAnnouncement = `Filter removed: ${text}.`;
	}

	function clearAdhocFilters() {
		writer.startSession();
		writer.write(emptyQuery());
		filterAnnouncement = 'Filters cleared.';
	}

	// Back to the saved view: drops the filters, the search text and the type.
	function clearNarrowing() {
		writer.cancel();
		const params = new SvelteURLSearchParams(page.url.searchParams);
		for (const key of [FILTER_PARAM, 'q', 'type']) params.delete(key);
		appliedQ = '';
		appliedType = '';
		searchInput = '';
		q = '';
		selectedType = '';
		navigateWith(params, false);
		filterAnnouncement = 'Showing the saved conditions only.';
	}

	// Quiet on failure: only the collection picker says so.
	async function loadCollections() {
		collectionsFailed = false;
		const all = await fetchAllCollections();
		allCollections = all;
		collectionsFailed = all === null;
	}

	function clearManualNarrowing() {
		items = [];
		hasMore = false;
		searchInput = '';
		q = '';
		selectedType = '';
	}

	function savedAsNew(created: CollectionResponse) {
		void goto(resolve('/collections/[id]', collectionRouteParams(created)));
	}

	function openUpdate() {
		updateError = null;
		updateOpen = true;
	}

	async function confirmUpdate() {
		if (!collection || updating) return;
		const id = collection.id;
		const definition = combinedQuery;
		updating = true;
		updateError = null;
		try {
			const updated = await updateDefinition(id, definition);
			if (id !== collection?.id) return;
			collection = updated;
			updateOpen = false;
			clearNarrowing();
			toast.success('Collection updated');
		} catch (e) {
			if (!(e instanceof SmartCollectionError)) throw e;
			updateError = describeSaveError(e, definition);
			if (e.status === 412) void loadCollection(id, true);
		} finally {
			updating = false;
		}
	}

	function handleUpdateOpenChange(open: boolean) {
		if (!open && updating) return;
		updateOpen = open;
	}

	async function fetchPage(id: string, search: string, type: string, after?: string) {
		const seq = ++fetchSeq;
		loading = true;
		if (!after) {
			itemsFailed = false;
			firstPageLoaded = false;
		}
		const result = await listNodes({
			query: {
				after,
				limit: PAGE_SIZE,
				q: search || undefined,
				type: type || undefined,
				collection: id
			}
		});
		if (seq !== fetchSeq) return;
		if (result.response?.status === 404) {
			notFound = true;
			hasMore = false;
		} else if (result.error || !result.data) {
			if (after) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
			} else {
				itemsFailed = true;
			}
			hasMore = false;
		} else {
			items = after ? [...items, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		if (!after) firstPageLoaded = true;
		loading = false;
	}

	$effect(() => {
		const id = collectionId;
		if (!id) return;
		// Already showing this collection (the address just became its slug)
		const loaded = untrack(() => collection);
		if (loaded && (loaded.slug === id || loaded.id === id)) return;
		untrack(() => {
			collection = null;
			items = [];
			hasMore = false;
			q = '';
			searchInput = '';
			selectedType = '';
			appliedQ = '';
			appliedType = '';
		});
		void loadCollection(id);
	});

	async function fetchSmart(more = false) {
		const current = collection;
		if (!current) return;
		const seq = ++fetchSeq;
		loading = true;
		if (!more) {
			itemsFailed = false;
			firstPageLoaded = false;
			tooLarge = false;
		}
		try {
			const result = await loadSmartCollection(current, {
				cursor: more ? smartCursor : null,
				limit: PAGE_SIZE,
				narrow: { adhoc, basics }
			});
			if (seq !== fetchSeq) return;
			items = more ? [...items, ...result.items] : result.items;
			smartCursor = result.nextCursor;
			hasMore = result.nextCursor !== null;
			smartWarnings = result.warnings;
			searchWarnings = result.searchWarnings;
			tooLarge = result.tooLarge;
			adhocError = null;
			narrowedTotal = { total: result.total, capped: result.totalCapped };
		} catch (e) {
			if (seq !== fetchSeq) return;
			if (
				e instanceof SearchError &&
				e.detail !== null &&
				(e.status === 400 || e.status === 422) &&
				storedQuery
			) {
				const { target, message } = splitDetail(e.detail);
				const at =
					target && 'where' in target
						? locateInCombined(target.where, storedQuery, adhoc, basics)
						: null;
				adhocError = { message, path: at?.part === 'adhoc' ? at.path : null };
				items = [];
				hasMore = false;
			} else if (more) {
				toast.error(e instanceof SearchError ? e.title : 'Something went wrong', {
					description: e instanceof SearchError ? e.description : undefined
				});
			} else {
				itemsFailed = true;
			}
			hasMore = false;
		}
		if (!more) firstPageLoaded = true;
		loading = false;
	}

	$effect(() => {
		const id = canonicalId;
		const search = q;
		const type = selectedType;
		const kind = collectionKind;
		// Refetch when the filters, or the saved conditions, change
		void [adhocKey, storedKey];
		if (!id || !kind) return;
		untrack(() => {
			if (kind === 'dynamic') {
				smartCursor = null;
				void fetchSmart();
			} else {
				void fetchPage(id, search, type);
			}
		});
	});

	$effect(() => {
		if (!smart) return;
		void loadCollections();
	});

	$effect(() => {
		if (!smart) return;
		void fetchItemFields().then((fields) => {
			itemFields = fields;
		});
	});

	/** Saves the edited conditions; true when there is nothing left to save. */
	async function commitConditions(): Promise<boolean> {
		const next = draft;
		if (!next || !collection) return true;
		if (conditionsSaving) return false;
		if (storedQuery && queryKey(next) === queryKey(storedQuery)) return true;
		const id = collection.id;
		conditionsSaving = true;
		try {
			const updated = await updateDefinition(id, next);
			if (id !== collection?.id) return false;
			collection = updated;
			items = [];
			toast.success('Conditions saved');
			return true;
		} catch (e) {
			if (!(e instanceof SmartCollectionError)) throw e;
			const where = e.target && 'where' in e.target ? e.target.where : null;
			conditionsError = { message: e.message, path: where };
			if (e.status === 412) void loadCollection(id, true);
			return false;
		} finally {
			conditionsSaving = false;
		}
	}

	async function saveConditions() {
		if (await commitConditions()) conditionsOpen = false;
	}

	function openConditions(event?: MouseEvent) {
		if (event) conditionsTrigger = event.currentTarget as HTMLElement;
		conditionsOpen = true;
	}

	// Closing the panel any way but Save discards the edits.
	$effect(() => {
		const open = conditionsOpen;
		if (wasConditionsOpen && !open) {
			untrack(() => {
				draft = null;
				conditionsError = null;
				void tick().then(() => conditionsTrigger?.focus());
			});
		}
		wasConditionsOpen = open;
	});

	function sentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && hasMore && !loading)
					if (smart) void fetchSmart(true);
					else void fetchPage(canonicalId, q, selectedType, items.at(-1)?.id);
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

	function openAdd(event: MouseEvent) {
		addTrigger = event.currentTarget as HTMLElement;
		addOpen = true;
	}

	function handleAddOpenChange(open: boolean) {
		addOpen = open;
		if (!open) {
			void tick().then(() => {
				// The empty-state button disappears once items are added
				(addTrigger?.isConnected ? addTrigger : headerAddButton)?.focus();
			});
		}
	}

	function refreshAfterChange() {
		void loadCollection(canonicalId, true);
		void fetchPage(canonicalId, q, selectedType);
	}

	async function handleRemove(item: NodeResponse) {
		if (removingId !== null || !collection) return;
		const id = collection.id;
		const collectionName = collection?.name ?? 'collection';
		const searchAtRemoval = q;
		const typeAtRemoval = selectedType;
		const index = shownItems.findIndex((i) => i.id === item.id);
		const neighbour = shownItems[index + 1] ?? shownItems[index - 1];
		removingId = item.id;
		const result = await removeItemFromCollection({
			path: { collection_id: id, item_id: item.id }
		});
		removingId = null;
		if (result.error) {
			const { title, description } = networkAwareError(result);
			toast.error(title, { description });
			return;
		}
		if (id !== collection?.id) return;
		items = items.filter((i) => i.id !== item.id);
		void loadCollection(id, true);
		void tick().then(() => {
			const next = neighbour
				? document.querySelector<HTMLElement>(`[data-remove-id="${neighbour.id}"]`)
				: null;
			(next ?? headerAddButton)?.focus();
		});
		toast.success(`Removed from ${collectionName}`, {
			duration: 5000,
			action: {
				label: 'Undo',
				onClick: () => void undoRemove(id, item, searchAtRemoval, typeAtRemoval)
			}
		});
	}

	async function undoRemove(
		id: string,
		item: NodeResponse,
		searchAtRemoval: string,
		typeAtRemoval: string
	) {
		const result = await addItemsToCollection({
			path: { collection_id: id },
			body: { item_ids: [item.id] }
		});
		if (result.error) {
			toast.error(addItemsErrorMessage(result.response?.status));
			return;
		}
		if (id !== collection?.id) return;
		void loadCollection(id, true);
		// Restore in id order, unless it belongs on a page that has not loaded yet
		const last = items.at(-1);
		const beyondLoaded = hasMore && last !== undefined && item.id > last.id;
		if (
			searchAtRemoval === q &&
			typeAtRemoval === selectedType &&
			!beyondLoaded &&
			!items.some((i) => i.id === item.id)
		) {
			items = [...items, item].sort((x, y) => (x.id < y.id ? -1 : x.id > y.id ? 1 : 0));
		}
	}

	function openEdit(event: MouseEvent) {
		if (!collection) return;
		editTrigger = event.currentTarget as HTMLElement;
		editName = collection.name;
		editSlug = collection.slug;
		slugError = null;
		editDescription = collection.description ?? '';
		editTouched = false;
		saveError = null;
		editOpen = true;
	}

	function handleEditOpenChange(open: boolean) {
		if (!open && (saving || regenerating)) return;
		editOpen = open;
		if (!open) void tick().then(() => editTrigger?.focus());
	}

	async function handleEditSubmit(event: SubmitEvent) {
		event.preventDefault();
		editTouched = true;
		if (nameHint !== null || saving || !collection) return;
		if (regenerating) return;
		const id = collection.id;
		saving = true;
		saveError = null;
		slugError = null;
		const slugChange = slugPatch(collection.slug, editSlug);
		const result = await updateCollection({
			path: { collection_id: id },
			body: { name: editName.trim(), description: editDescription.trim(), ...slugChange }
		});
		saving = false;
		if (result.response?.status === 412) {
			saveError = 'This collection was changed elsewhere. Close this and try again.';
			void loadCollection(id, true);
			return;
		}
		if (result.error || !result.data) {
			const status = result.response?.status;
			if (status === undefined) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
			} else if ('slug' in slugChange && (status === 409 || status === 400)) {
				slugError = slugSaveErrorMessage(status, errorMessage(result.error));
			} else {
				saveError = collectionSaveErrorMessage(status);
			}
			return;
		}
		collection = result.data;
		showCanonicalAddress(result.data);
		handleEditOpenChange(false);
		toast.success('Collection saved');
	}

	async function regenerateSlug() {
		if (regenerating || saving || nameUnsaved || !collection) return;
		const id = collection.id;
		regenerating = true;
		slugError = null;
		saveError = null;
		const result = await updateCollection({
			path: { collection_id: id },
			body: { regenerate_slug: true }
		});
		regenerating = false;
		if (result.response?.status === 412) {
			saveError = 'This collection was changed elsewhere. Close this and try again.';
			void loadCollection(id, true);
			return;
		}
		if (result.error || !result.data) {
			const status = result.response?.status;
			if (status === undefined) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
			} else {
				slugError =
					slugSaveErrorMessage(status, errorMessage(result.error)) ??
					collectionSaveErrorMessage(status);
			}
			return;
		}
		collection = result.data;
		editSlug = result.data.slug;
		showCanonicalAddress(result.data);
	}

	function openDelete(event: MouseEvent) {
		deleteTrigger = event.currentTarget as HTMLElement;
		confirmDelete = true;
	}

	function handleDeleteOpenChange(open: boolean) {
		if (!open && deleting) return;
		confirmDelete = open;
		if (!open) void tick().then(() => deleteTrigger?.focus());
	}

	async function handleDelete() {
		if (!collection) return;
		deleting = true;
		const result = await deleteCollection({ path: { collection_id: collection.id } });
		if (result.error) {
			deleting = false;
			confirmDelete = false;
			const { title, description } = networkAwareError(result);
			toast.error(title, { description });
			void tick().then(() => deleteTrigger?.focus());
			return;
		}
		toast.success('Collection deleted');
		await goto(resolve('/collections'));
	}
</script>

<svelte:head>
	<title>{collection ? `${collection.name} - Menagerist` : 'Collection - Menagerist'}</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<BackButton fallback={resolve('/collections')} />

		{#if notFound}
			<NotFound
				heading="Collection not found"
				description="This collection no longer exists."
				backHref={resolve('/collections')}
				backLabel="Back to Collections"
			/>
		{:else if loadFailed}
			<div class="flex flex-col items-start gap-3 rounded-xl border border-dashed p-5">
				<p class="text-sm text-muted-foreground">Couldn't load this collection.</p>
				<Button variant="outline" onclick={() => void loadCollection(collectionId)}>
					Try again
				</Button>
			</div>
		{:else}
			{#if collection}
				<div class="flex flex-wrap items-start justify-between gap-3">
					<div class="min-w-0">
						<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
							<h1 class="font-heading text-3xl font-semibold tracking-tight break-words">
								{collection.name}
							</h1>
							{#if smart}
								<Badge variant="secondary" class="shrink-0">Smart</Badge>
							{/if}
							{#if exampleCollectionIds.has(collection.id)}
								<Badge variant="outline" class="shrink-0 text-muted-foreground">Example</Badge>
							{/if}
						</div>
						{#if collection.description}
							<p class="mt-1 whitespace-pre-line text-muted-foreground">
								{collection.description}
							</p>
						{/if}
						<CollectionCount {collection} ready={firstPageLoaded} />
					</div>
					<div class="flex flex-wrap items-center gap-2">
						{#if smart}
							{#if !unreadable}
								<Button bind:ref={headerAddButton} onclick={openConditions}>
									<SlidersHorizontal class="size-4" />
									Edit conditions
								</Button>
							{/if}
						{:else}
							<Button bind:ref={headerAddButton} onclick={openAdd}>
								<Plus class="size-4" />
								Add items
							</Button>
						{/if}
						<Button variant="outline" onclick={openEdit}>
							<Pencil class="size-4" />
							Edit
						</Button>
						<Button variant="outline" onclick={openDelete}>
							<Trash2 class="size-4" />
							Delete
						</Button>
					</div>
				</div>
			{:else if loadingDisplay.show}
				<div class="h-16 animate-pulse rounded-xl bg-muted" aria-hidden="true"></div>
			{/if}

			{#if collection && smart}
				<div class="flex flex-col gap-3">
					<SmartConditions
						definition={collection.definition}
						{lookup}
						warnings={savedWarnings}
						locked
					/>
					<p class="text-sm text-muted-foreground">{SMART_EXPLANATION}</p>
				</div>
			{/if}

			<div class="flex flex-wrap items-center gap-2">
				{#if !unreadable}
					<input
						bind:value={searchInput}
						type="search"
						placeholder="Search this collection…"
						aria-label="Search this collection"
						class="flex h-9 min-w-0 flex-1 basis-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none sm:max-w-sm sm:basis-auto"
					/>
				{/if}
				<div class="ml-auto flex items-center gap-2">
					{#if smart && !unreadable}
						<Button
							variant="outline"
							class="max-sm:h-11"
							aria-haspopup="dialog"
							onclick={() => openFilters(null)}
						>
							<SlidersHorizontal />
							Filter
							{#if adhocCount > 0}
								<Badge class="ml-0.5 h-5 min-w-5 px-1.5 tabular-nums">
									{adhocCount}<span class="sr-only">
										{adhocCount === 1 ? 'condition' : 'conditions'}</span
									>
								</Badge>
							{/if}
						</Button>
					{/if}
					{#if showTypeFilter && !unreadable}
						<NativeSelect.Root
							size="sm"
							class="max-sm:[&_select[data-size]]:h-11"
							aria-label="Item type"
							value={selectedType}
							onchange={(e) => selectType(e.currentTarget.value)}
						>
							<NativeSelect.Option value="">All types</NativeSelect.Option>
							{#each itemTypes as type (type.slug)}
								<NativeSelect.Option value={type.slug}>{type.label}</NativeSelect.Option>
							{/each}
						</NativeSelect.Root>
					{/if}
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
							class="relative rounded-md p-1.5 transition-colors after:absolute after:-inset-2.5 after:content-[''] {viewMode ===
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
							class="relative rounded-md p-1.5 transition-colors after:absolute after:-inset-2.5 after:content-[''] {viewMode ===
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

			{#if smart && !unreadable && (adhocCount > 0 || narrowed)}
				<div class="flex flex-col gap-3">
					{#if adhocCount > 0}
						<QueryChips
							query={adhoc}
							{lookup}
							warned={adhocMarks.conditions}
							{catalogue}
							onopen={(path) => openFilters(path)}
							onremove={removeFilter}
							onclear={clearAdhocFilters}
						/>
					{/if}
					{#if narrowed}
						<NarrowedBar
							text={barText}
							{blockReason}
							{updating}
							linkedBlockReason={linkedReason}
							onsave={() => (saveOpen = true)}
							onlinked={() => (linkedOpen = true)}
							onupdate={openUpdate}
							onclear={clearNarrowing}
						/>
					{/if}
					{#if adhocError}
						<Alert.Root variant="destructive">
							<TriangleAlert />
							<Alert.Title>This filter can't be used</Alert.Title>
							<Alert.Description>
								{adhocErrorText}
								<Button
									variant="link"
									class="h-auto p-0"
									onclick={() => openFilters(adhocError?.path ?? null)}>Edit filters</Button
								>
							</Alert.Description>
						</Alert.Root>
					{:else if tooLarge}
						<Alert.Root>
							<TriangleAlert />
							<Alert.Description>{NARROW_TOO_LARGE_MESSAGE}</Alert.Description>
						</Alert.Root>
					{/if}
				</div>
			{/if}
			{#if manualNarrowed}
				<NarrowedBar
					text={manualBarText}
					blockReason={null}
					linkedBlockReason={linkedReason}
					onlinked={() => (linkedOpen = true)}
					onclear={clearManualNarrowing}
				/>
			{/if}
			<p class="sr-only" role="status" aria-live="polite">{filterAnnouncement}</p>

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
									<div class="space-y-1">
										<div class="h-5 w-48 rounded bg-muted"></div>
										<div class="h-4 w-72 rounded bg-muted"></div>
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
						<div class="relative">
							<NodeGridCard
								{item}
								schema={schemaOf(item.type)}
								categoryLabel={itemTypes.find((t) => t.slug === item.type)?.label}
								match={q ? matchContext(item, schemaOf(item.type), q) : null}
								isExample={exampleItemIds.has(item.id)}
							/>
							{#if !smart}
								<button
									type="button"
									onclick={() => void handleRemove(item)}
									disabled={removingId === item.id}
									data-remove-id={item.id}
									aria-label="Remove {item.name} from this collection"
									title="Remove from collection"
									class="absolute top-2 right-2 rounded-full bg-background/90 p-1.5 text-muted-foreground shadow-sm transition-colors after:absolute after:-inset-2.5 after:content-[''] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
								>
									<X class="size-4" />
								</button>
							{/if}
						</div>
					{/each}
				</div>
			{:else}
				<Item.Group>
					{#each shownItems as item (item.id)}
						<div role="listitem" class="flex items-stretch gap-2">
							<div class="min-w-0 flex-1">
								<NodeCard
									{item}
									schema={schemaOf(item.type)}
									categoryLabel={itemTypes.find((t) => t.slug === item.type)?.label}
									match={q ? matchContext(item, schemaOf(item.type), q) : null}
									isExample={exampleItemIds.has(item.id)}
								/>
							</div>
							{#if !smart}
								<button
									type="button"
									onclick={() => void handleRemove(item)}
									disabled={removingId === item.id}
									data-remove-id={item.id}
									aria-label="Remove {item.name} from this collection"
									title="Remove from collection"
									class="relative shrink-0 self-center rounded-md p-2 text-muted-foreground transition-colors after:absolute after:-inset-2 after:content-[''] hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
								>
									<X class="size-4" />
								</button>
							{/if}
						</div>
					{/each}
				</Item.Group>
			{/if}

			{#if itemsFailed}
				<div class="flex flex-col items-start gap-3 rounded-xl border border-dashed p-5">
					<p class="text-sm text-muted-foreground">Couldn't load the items in this collection.</p>
					<Button
						variant="outline"
						onclick={() =>
							smart ? void fetchSmart() : void fetchPage(canonicalId, q, selectedType)}
					>
						Try again
					</Button>
				</div>
			{:else if items.length > 0 && shownItems.length === 0 && !loading && !hasMore}
				<div class="flex flex-col items-center gap-3 py-12 text-center">
					<EyeOff class="size-10 text-muted-foreground/50" />
					<p class="text-sm text-muted-foreground">
						{#if exampleFilter === 'only'}
							No example items match.
						{:else}
							Everything here is a hidden example. Choose All items to see them.
						{/if}
					</p>
					<Button variant="outline" size="sm" onclick={() => setExampleFilter('all')}>
						Show all items
					</Button>
				</div>
			{:else if items.length === 0 && !loading && !headerLoading && (adhocError || tooLarge)}
				<!-- The notice above says why; there is nothing to list. -->
			{:else if items.length === 0 && !loading && !headerLoading && unreadable}
				<!-- The conditions message above says why; there is nothing to list. -->
			{:else if items.length === 0 && !loading && !headerLoading}
				<div class="flex flex-col items-center gap-3 py-12 text-center">
					{#if narrowed}
						<SearchX class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">No items match your filters</p>
							<p class="text-sm text-muted-foreground">
								Change a filter, or clear them to see the whole collection.
							</p>
						</div>
						<Button variant="ghost" size="sm" onclick={clearNarrowing}>Clear</Button>
					{:else if smart}
						<SearchX class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">No items match these conditions</p>
							<p class="text-sm text-muted-foreground">Items appear here as soon as they match.</p>
						</div>
						<Button variant="outline" onclick={openConditions}>
							<SlidersHorizontal class="size-4" />
							Edit conditions
						</Button>
					{:else if q}
						<SearchX class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">Nothing matched "{q}"</p>
							<p class="text-sm text-muted-foreground">Try a different search term</p>
						</div>
						<Button variant="ghost" size="sm" onclick={() => (searchInput = '')}>
							Clear search
						</Button>
					{:else if selectedType}
						<SearchX class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">Nothing matched this type</p>
							<p class="text-sm text-muted-foreground">
								No {typeLabels[selectedType] ?? selectedType} items in this collection
							</p>
						</div>
						<Button variant="ghost" size="sm" onclick={() => selectType('')}>Show all types</Button>
					{:else}
						<Library class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">Nothing in this collection yet.</p>
							<p class="text-sm text-muted-foreground">Add items here, or from any item's page.</p>
						</div>
						<Button onclick={openAdd}>
							<Plus class="size-4" />
							Add items
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
		{/if}
	</div>
</main>

<ResponsiveDialog.Root open={editOpen} onOpenChange={handleEditOpenChange}>
	<ResponsiveDialog.Content title="Edit collection" size="md">
		<form class="mt-4 space-y-4" onsubmit={handleEditSubmit} novalidate>
			<div class="space-y-1.5">
				<Label for="edit-collection-name">Name</Label>
				<Input
					id="edit-collection-name"
					bind:value={editName}
					maxlength={MAX_COLLECTION_NAME_LENGTH}
					required
					autocomplete="off"
					aria-invalid={showNameHint}
					aria-describedby={showNameHint ? 'edit-collection-name-hint' : undefined}
					onblur={() => (editTouched = true)}
				/>
				{#if showNameHint}
					<p id="edit-collection-name-hint" class="text-sm text-destructive">{nameHint}</p>
				{/if}
			</div>
			<CollectionSlugField
				bind:value={editSlug}
				error={slugError}
				{regenerating}
				disabled={saving}
				{nameUnsaved}
				onRegenerate={regenerateSlug}
			/>
			<div class="space-y-1.5">
				<Label for="edit-collection-description">Description</Label>
				<Textarea
					id="edit-collection-description"
					bind:value={editDescription}
					placeholder="Optional"
				/>
			</div>
			{#if saveError}
				<p role="alert" class="text-sm text-destructive">{saveError}</p>
			{/if}
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => handleEditOpenChange(false)}>
					Cancel
				</Button>
				<Button type="submit" disabled={saving}>
					{saving ? 'Saving…' : 'Save'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

{#if !smart}
	<AddItemsDialog
		open={addOpen}
		collectionId={canonicalId}
		{typeLabels}
		onOpenChange={handleAddOpenChange}
		onAdded={refreshAfterChange}
	/>
{/if}

{#if linkedQuery}
	<SaveSmartCollectionDialog
		bind:open={linkedOpen}
		query={linkedQuery}
		title="Save as new, linked to this collection"
		intro="The new collection is always the items in this collection that match these conditions."
		onsaved={savedAsNew}
	/>
{/if}

{#if smart && !unreadable}
	<QueryBuilder
		bind:open={conditionsOpen}
		query={builderQuery}
		{catalogue}
		collections={allCollections}
		{collectionsFailed}
		onretrycollections={() => void loadCollections()}
		excludeCollectionId={canonicalId}
		warned={mapWarnings(savedWarnings).conditions}
		{sortWarned}
		error={conditionsError}
		title="Edit conditions"
		description={EDIT_CONDITIONS_DESCRIPTION}
		saving={conditionsSaving}
		onsave={() => void saveConditions()}
		oncancel={() => (conditionsOpen = false)}
		onchange={(next) => (draft = next)}
	/>
	<QueryBuilder
		bind:open={filtersOpen}
		query={adhoc}
		{catalogue}
		collections={allCollections}
		{collectionsFailed}
		onretrycollections={() => void loadCollections()}
		excludeCollectionId={canonicalId}
		warned={adhocMarks.conditions}
		sortWarned={adhocMarks.sort}
		error={adhocError}
		notice={tooLarge ? NARROW_TOO_LARGE_MESSAGE : null}
		focus={filtersFocus}
		description="Narrow this collection further. Changes apply as you go and are not saved to the collection."
		onchange={(next, { debounce }) => writer.write(next, { debounce })}
	/>
	<SaveSmartCollectionDialog bind:open={saveOpen} query={combinedQuery} onsaved={savedAsNew} />
	<ConfirmDialog
		open={updateOpen}
		title="Update this collection?"
		description={updateDescription}
		busy={updating}
		busyLabel="Updating…"
		confirmLabel="Update collection"
		destructive={false}
		onOpenChange={handleUpdateOpenChange}
		onConfirm={confirmUpdate}
	/>
{/if}

{#snippet updateDescription()}
	{updateConfirmation(
		storedQuery ? countConditions(storedQuery) : 0,
		countConditions(combinedQuery),
		adhoc.sort.length > 0
	)}
	{#if updateError}
		<span role="alert" class="mt-2 block text-destructive">{updateError}</span>
	{/if}
{/snippet}

<ConfirmDialog
	open={confirmDelete}
	title="Delete this collection?"
	description="The items on it are kept."
	busy={deleting}
	busyLabel="Deleting…"
	confirmLabel="Delete"
	onOpenChange={handleDeleteOpenChange}
	onConfirm={handleDelete}
/>
