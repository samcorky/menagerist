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
		SearchX,
		Trash2,
		X
	} from '@lucide/svelte';
	import { tick, untrack } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		addItemsToCollection,
		deleteCollection,
		getCollection,
		listNodes,
		listNodeTypes,
		removeItemFromCollection,
		updateCollection,
		type CollectionResponse,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import {
		MAX_COLLECTION_NAME_LENGTH,
		addItemsErrorMessage,
		collectionSaveErrorMessage,
		describeItemCount,
		validateCollectionName
	} from '$lib/collections';
	import AddItemsDialog from '$lib/components/add-items-dialog.svelte';
	import BackButton from '$lib/components/back-button.svelte';
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
	const loadingSkeletons = [1, 2, 3, 4, 5];

	const collectionId = $derived(page.params.id ?? '');

	let collection = $state<CollectionResponse | null>(null);
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
	let viewMode = $state<'list' | 'grid'>('list');
	let exampleCollectionIds = $state<ReadonlySet<string>>(new Set());
	let exampleItemIds = $state<ReadonlySet<string>>(new Set());
	let exampleFilter = $state<ExampleFilter>(readExampleFilter());
	const showExampleFilter = $derived(exampleItemIds.size > 0 || exampleFilter !== 'all');
	const shownItems = $derived(visibleItems(items, exampleItemIds, exampleFilter));
	const exampleFilters = Object.keys(EXAMPLE_FILTER_LABELS) as ExampleFilter[];

	let editOpen = $state(false);
	let editName = $state('');
	let editDescription = $state('');
	let editTouched = $state(false);
	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let editTrigger: HTMLElement | null = null;

	let removingId = $state<string | null>(null);
	let addOpen = $state(false);
	let addTrigger: HTMLElement | null = null;
	let headerAddButton = $state<HTMLElement | null>(null);
	const typeLabels = $derived(Object.fromEntries(itemTypes.map((t) => [t.slug, t.label])));

	let confirmDelete = $state(false);
	let deleting = $state(false);
	let deleteTrigger: HTMLElement | null = null;

	const nameHint = $derived(validateCollectionName(editName));
	const showNameHint = $derived(editTouched && nameHint !== null);

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
		void listNodeTypes({ query: { limit: 100 } }).then((result) => {
			if (result.data) itemTypes = result.data;
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

	function schemaOf(slug: string | null | undefined): AttributesSchema | null {
		const type = itemTypes.find((t) => t.slug === slug);
		return (type?.attributes_schema as AttributesSchema | null | undefined) ?? null;
	}

	async function loadCollection(id: string) {
		const seq = ++collectionSeq;
		headerLoading = true;
		notFound = false;
		loadFailed = false;
		const result = await getCollection({ path: { collection_id: id } });
		if (seq !== collectionSeq || id !== collectionId) return;
		if (result.response?.status === 404) {
			notFound = true;
			collection = null;
		} else if (result.error || !result.data) {
			loadFailed = true;
			collection = null;
		} else {
			collection = result.data;
		}
		headerLoading = false;
	}

	async function fetchPage(id: string, search: string, after?: string) {
		const seq = ++fetchSeq;
		loading = true;
		if (!after) itemsFailed = false;
		const result = await listNodes({
			query: { after, limit: PAGE_SIZE, q: search || undefined, collection: id }
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
		loading = false;
	}

	$effect(() => {
		const id = collectionId;
		if (!id) return;
		untrack(() => {
			collection = null;
			items = [];
			hasMore = false;
			q = '';
			searchInput = '';
		});
		void loadCollection(id);
	});

	$effect(() => {
		const id = collectionId;
		const search = q;
		if (!id) return;
		void fetchPage(id, search);
	});

	function sentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && hasMore && !loading)
					void fetchPage(collectionId, q, items.at(-1)?.id);
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
		void loadCollection(collectionId);
		void fetchPage(collectionId, q);
	}

	async function handleRemove(item: NodeResponse) {
		if (removingId !== null) return;
		const id = collectionId;
		const collectionName = collection?.name ?? 'collection';
		const searchAtRemoval = q;
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
		if (id !== collectionId) return;
		items = items.filter((i) => i.id !== item.id);
		void loadCollection(id);
		void tick().then(() => {
			const next = neighbour
				? document.querySelector<HTMLElement>(`[data-remove-id="${neighbour.id}"]`)
				: null;
			(next ?? headerAddButton)?.focus();
		});
		toast.success(`Removed from ${collectionName}`, {
			duration: 5000,
			action: { label: 'Undo', onClick: () => void undoRemove(id, item, searchAtRemoval) }
		});
	}

	async function undoRemove(id: string, item: NodeResponse, searchAtRemoval: string) {
		const result = await addItemsToCollection({
			path: { collection_id: id },
			body: { item_ids: [item.id] }
		});
		if (result.error) {
			toast.error(addItemsErrorMessage(result.response?.status));
			return;
		}
		if (id !== collectionId) return;
		void loadCollection(id);
		// Restore in id order, unless it belongs on a page that has not loaded yet
		const last = items.at(-1);
		const beyondLoaded = hasMore && last !== undefined && item.id > last.id;
		if (searchAtRemoval === q && !beyondLoaded && !items.some((i) => i.id === item.id)) {
			items = [...items, item].sort((x, y) => (x.id < y.id ? -1 : x.id > y.id ? 1 : 0));
		}
	}

	function openEdit(event: MouseEvent) {
		if (!collection) return;
		editTrigger = event.currentTarget as HTMLElement;
		editName = collection.name;
		editDescription = collection.description ?? '';
		editTouched = false;
		saveError = null;
		editOpen = true;
	}

	function handleEditOpenChange(open: boolean) {
		if (!open && saving) return;
		editOpen = open;
		if (!open) void tick().then(() => editTrigger?.focus());
	}

	async function handleEditSubmit(event: SubmitEvent) {
		event.preventDefault();
		editTouched = true;
		if (nameHint !== null || saving) return;
		saving = true;
		saveError = null;
		const result = await updateCollection({
			path: { collection_id: collectionId },
			body: { name: editName.trim(), description: editDescription.trim() }
		});
		saving = false;
		if (result.response?.status === 412) {
			saveError = 'This collection was changed elsewhere. Close this and try again.';
			void loadCollection(collectionId);
			return;
		}
		if (result.error || !result.data) {
			const status = result.response?.status;
			if (status === undefined) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
			} else {
				saveError = collectionSaveErrorMessage(status);
			}
			return;
		}
		collection = result.data;
		handleEditOpenChange(false);
		toast.success('Collection saved');
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
		deleting = true;
		const result = await deleteCollection({ path: { collection_id: collectionId } });
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
							{#if exampleCollectionIds.has(collection.id)}
								<Badge variant="outline" class="shrink-0 text-muted-foreground">Example</Badge>
							{/if}
						</div>
						{#if collection.description}
							<p class="mt-1 whitespace-pre-line text-muted-foreground">
								{collection.description}
							</p>
						{/if}
						<p class="mt-1 text-sm text-muted-foreground">
							{describeItemCount(collection.item_count)}
						</p>
					</div>
					<div class="flex flex-wrap items-center gap-2">
						<Button bind:ref={headerAddButton} onclick={openAdd}>
							<Plus class="size-4" />
							Add items
						</Button>
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

			<div class="flex flex-wrap items-center gap-2">
				<input
					bind:value={searchInput}
					type="search"
					placeholder="Search this collection…"
					aria-label="Search this collection"
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
						</div>
					{/each}
				</Item.Group>
			{/if}

			{#if itemsFailed}
				<div class="flex flex-col items-start gap-3 rounded-xl border border-dashed p-5">
					<p class="text-sm text-muted-foreground">Couldn't load the items in this collection.</p>
					<Button variant="outline" onclick={() => void fetchPage(collectionId, q)}>
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
			{:else if items.length === 0 && !loading && !headerLoading}
				<div class="flex flex-col items-center gap-3 py-12 text-center">
					{#if q}
						<SearchX class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">Nothing matched "{q}"</p>
							<p class="text-sm text-muted-foreground">Try a different search term</p>
						</div>
						<Button variant="ghost" size="sm" onclick={() => (searchInput = '')}>
							Clear search
						</Button>
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

<AddItemsDialog
	open={addOpen}
	{collectionId}
	{typeLabels}
	onOpenChange={handleAddOpenChange}
	onAdded={refreshAfterChange}
/>

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
