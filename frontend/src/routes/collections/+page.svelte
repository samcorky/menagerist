<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { Library, Plus, SearchX } from '@lucide/svelte';
	import { tick, untrack } from 'svelte';
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';
	import {
		createCollection,
		listCollections,
		type CollectionResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import {
		MAX_COLLECTION_NAME_LENGTH,
		collectionRouteParams,
		collectionSaveErrorMessage,
		fetchAllCollections,
		validateCollectionName
	} from '$lib/collections';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import QueryBuilder from '$lib/components/query-builder.svelte';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { loadExampleIds } from '$lib/examples';
	import { fetchItemFields, type ItemField } from '$lib/item-fields';
	import { fetchAllNodeTypes } from '$lib/node-types';
	import { buildCatalogue } from '$lib/query/fields';
	import { emptyQuery } from '$lib/query/tree';
	import type { Query } from '$lib/query/types';
	import { normaliseQuery } from '$lib/search-palette';
	import {
		SmartCollectionError,
		canCreateSmart,
		describeCollectionCount,
		describeSaveError,
		isSmart,
		saveSmartCollection
	} from '$lib/smart-collections';

	const PAGE_SIZE = 50;

	const kinds = [
		{ value: 'manual', label: 'List you fill', hint: 'You choose which items go in.' },
		{
			value: 'smart',
			label: 'Smart: matches conditions',
			hint: 'Items that match are added automatically.'
		}
	] as const;

	let collections = $state<CollectionResponse[]>([]);
	let loading = $state(true);
	let loadFailed = $state(false);
	let hasMore = $state(false);
	let exampleCollectionIds = $state<ReadonlySet<string>>(new Set());
	let fetchSeq = 0;
	let searchInput = $state('');
	let q = $state('');

	let dialogOpen = $state(false);
	let name = $state('');
	let description = $state('');
	let touched = $state(false);
	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let trigger: HTMLElement | null = null;

	// 'manual' is a list the person fills; 'smart' saves a search (fixed once created).
	let kind = $state<'manual' | 'smart'>('manual');
	let smartQuery = $state<Query>(emptyQuery());
	let builderLoaded = false;
	let categories = $state<NodeTypeResponse[]>([]);
	let categoriesLoaded = $state(false);
	let itemFields = $state<ItemField[] | null>(null);
	let pickerCollections = $state<{ id: string; name: string }[] | null>(null);
	let collectionsFailed = $state(false);
	const catalogue = $derived(buildCatalogue(categories, categoriesLoaded, itemFields));
	const kindId = $props.id();

	// §13a: don't flash a skeleton for loads under 300ms
	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading);
	});

	const nameHint = $derived(validateCollectionName(name));
	const showNameHint = $derived(touched && nameHint !== null);
	const smartReason = $derived(kind === 'smart' ? canCreateSmart(name, smartQuery) : null);
	// The name's own hint already shows under the field once touched.
	const showSmartReason = $derived(
		smartReason !== null && !(showNameHint && smartReason === nameHint)
	);

	const showControls = $derived(
		!loadFailed && (collections.length > 0 || loading || q !== '' || searchInput !== '')
	);

	// Pick up ?q= from the URL (the search popup's "See all collections"), then drop it so the
	// same link works again after the box has been cleared.
	$effect(() => {
		const urlQ = normaliseQuery(page.url.searchParams.get('q'));
		if (!urlQ) return;
		if (urlQ !== untrack(() => q)) {
			collections = [];
			hasMore = false;
			q = urlQ;
		}
		searchInput = urlQ;
		const params = new SvelteURLSearchParams(page.url.searchParams);
		params.delete('q');
		const rest = params.toString();
		void goto(resolve(rest ? `/collections?${rest}` : '/collections'), {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	});

	$effect(() => {
		const value = normaliseQuery(searchInput);
		const timer = setTimeout(() => {
			if (value === q) return;
			collections = [];
			hasMore = false;
			q = value;
		}, 300);
		return () => clearTimeout(timer);
	});

	async function fetchPage(after?: string) {
		const seq = ++fetchSeq;
		loading = true;
		if (!after) loadFailed = false;
		const result = await listCollections({
			query: { after, limit: PAGE_SIZE, q: q || undefined }
		});
		if (seq !== fetchSeq) return;
		if (result.error || !result.data) {
			if (after) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
			} else {
				loadFailed = true;
			}
			hasMore = false;
		} else {
			collections = after ? [...collections, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		loading = false;
	}

	$effect(() => {
		void fetchPage();
	});

	$effect(() => {
		void loadExampleIds().then((ids) => (exampleCollectionIds = ids.collections));
	});

	function sentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && hasMore && !loading)
					void fetchPage(collections.at(-1)?.id);
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

	function resetDialog() {
		name = '';
		description = '';
		touched = false;
		saveError = null;
		kind = 'manual';
		smartQuery = emptyQuery();
	}

	function openDialog(event: MouseEvent) {
		trigger = event.currentTarget as HTMLElement;
		resetDialog();
		dialogOpen = true;
	}

	async function loadCollectionChoices() {
		collectionsFailed = false;
		const all = await fetchAllCollections();
		pickerCollections = all;
		collectionsFailed = all === null;
	}

	// The builder's lists are read once, the first time Smart is chosen.
	function loadBuilderData() {
		if (builderLoaded) return;
		builderLoaded = true;
		void fetchAllNodeTypes().then((types) => {
			if (types) categories = types;
			categoriesLoaded = true;
		});
		void fetchItemFields().then((fields) => (itemFields = fields));
		void loadCollectionChoices();
	}

	function chooseKind(next: 'manual' | 'smart') {
		kind = next;
		saveError = null;
		if (next === 'smart') loadBuilderData();
	}

	function handleOpenChange(open: boolean) {
		if (!open && saving) return;
		dialogOpen = open;
		if (!open) {
			resetDialog();
			void tick().then(() => trigger?.focus());
		}
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		touched = true;
		if (nameHint !== null || smartReason !== null || saving) return;
		saving = true;
		saveError = null;
		if (kind === 'smart') {
			try {
				const created = await saveSmartCollection(name, smartQuery, description);
				dialogOpen = false;
				void goto(resolve('/collections/[id]', collectionRouteParams(created)));
			} catch (e) {
				saveError = e instanceof SmartCollectionError ? describeSaveError(e, smartQuery) : null;
			} finally {
				saving = false;
			}
			return;
		}
		const result = await createCollection({
			body: { name: name.trim(), description: description.trim() || null }
		});
		saving = false;
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
		const created = result.data;
		dialogOpen = false;
		void goto(resolve('/collections/[id]', collectionRouteParams(created)));
	}
</script>

<svelte:head>
	<title>Collections - Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div>
				<h1 class="font-heading text-3xl font-semibold tracking-tight">Collections</h1>
				<p class="mt-1 text-muted-foreground">Group your items into named collections.</p>
			</div>
			{#if showControls}
				<Button onclick={openDialog}>
					<Plus class="size-4" />
					New collection
				</Button>
			{/if}
		</div>

		{#if showControls}
			<input
				bind:value={searchInput}
				type="search"
				placeholder="Search your collections…"
				aria-label="Search your collections"
				class="flex h-11 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none sm:h-9 sm:max-w-sm sm:text-sm"
			/>
		{/if}

		{#if loadingDisplay.show && collections.length === 0}
			<div class="grid gap-4 sm:grid-cols-2" aria-hidden="true">
				{#each [1, 2, 3, 4] as s (s)}
					<div class="h-28 animate-pulse rounded-xl bg-muted"></div>
				{/each}
			</div>
		{:else if loadFailed}
			<div class="flex flex-col items-start gap-3 rounded-xl border border-dashed p-5">
				<p class="text-sm text-muted-foreground">Couldn't load your collections.</p>
				<Button variant="outline" onclick={() => void fetchPage()}>Try again</Button>
			</div>
		{:else if collections.length > 0}
			<ul class="grid gap-4 sm:grid-cols-2">
				{#each collections as collection (collection.id)}
					<li>
						<a
							href={resolve('/collections/[id]', collectionRouteParams(collection))}
							class="block h-full rounded-xl focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
						>
							<Card.Root class="h-full transition-colors hover:bg-muted/50">
								<Card.Header>
									<Card.Title class="flex items-center gap-2">
										<span class="min-w-0 truncate">{collection.name}</span>
										{#if isSmart(collection)}
											<Badge variant="secondary" class="shrink-0">Smart</Badge>
										{/if}
										{#if exampleCollectionIds.has(collection.id)}
											<Badge variant="outline" class="shrink-0 text-muted-foreground">Example</Badge
											>
										{/if}
									</Card.Title>
									{#if collection.description}
										<Card.Description class="line-clamp-2"
											>{collection.description}</Card.Description
										>
									{/if}
								</Card.Header>
								<Card.Content class="text-sm text-muted-foreground">
									{describeCollectionCount(collection)}
								</Card.Content>
							</Card.Root>
						</a>
					</li>
				{/each}
			</ul>
		{:else if !loading && q}
			<div class="flex flex-col items-center gap-3 py-12 text-center">
				<SearchX class="size-10 text-muted-foreground/50" aria-hidden="true" />
				<div>
					<p class="font-medium">Nothing matched "{q}"</p>
					<p class="text-sm text-muted-foreground">Try a different search term</p>
				</div>
				<Button variant="ghost" class="min-h-11 sm:min-h-8" onclick={() => (searchInput = '')}>
					Clear search
				</Button>
			</div>
		{:else if !loading}
			<div
				class="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center"
			>
				<Library class="size-10 text-muted-foreground" aria-hidden="true" />
				<h2 class="text-lg font-medium">No collections yet</h2>
				<p class="max-w-sm text-sm text-muted-foreground">
					A collection groups items together. Make one for your vinyl, your Funkos, or films to
					watch.
				</p>
				<Button onclick={openDialog}>
					<Plus class="size-4" />
					New collection
				</Button>
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

<ResponsiveDialog.Root open={dialogOpen} onOpenChange={handleOpenChange}>
	<ResponsiveDialog.Content
		title="New collection"
		size="md"
		class={kind === 'smart' ? 'pb-0 sm:max-w-2xl' : undefined}
	>
		<form class="mt-4 space-y-4" onsubmit={handleSubmit} novalidate>
			<div class="space-y-1.5">
				<Label for="collection-name">Name</Label>
				<Input
					id="collection-name"
					bind:value={name}
					maxlength={MAX_COLLECTION_NAME_LENGTH}
					required
					autocomplete="off"
					aria-invalid={showNameHint}
					aria-describedby={showNameHint ? 'collection-name-hint' : undefined}
					onblur={() => (touched = true)}
				/>
				{#if showNameHint}
					<p id="collection-name-hint" class="text-sm text-destructive">{nameHint}</p>
				{/if}
			</div>
			<div class="space-y-1.5">
				<Label for="collection-description">Description</Label>
				<Textarea id="collection-description" bind:value={description} placeholder="Optional" />
			</div>
			<div role="radiogroup" aria-label="Kind of collection" class="grid gap-2 sm:grid-cols-2">
				{#each kinds as option (option.value)}
					<label
						class="flex min-h-11 cursor-pointer items-start gap-3 rounded-md border border-input p-3 has-checked:border-primary has-checked:bg-accent/40 has-focus-visible:ring-1 has-focus-visible:ring-ring"
					>
						<input
							type="radio"
							name="collection-kind-{kindId}"
							value={option.value}
							checked={kind === option.value}
							onchange={() => chooseKind(option.value)}
							aria-labelledby="{kindId}-{option.value}-label"
							aria-describedby="{kindId}-{option.value}-hint"
							class="mt-0.5 size-4 shrink-0 accent-primary"
						/>
						<span class="min-w-0 text-sm">
							<span id="{kindId}-{option.value}-label" class="block font-medium">
								{option.label}
							</span>
							<span id="{kindId}-{option.value}-hint" class="block text-muted-foreground">
								{option.hint}
							</span>
						</span>
					</label>
				{/each}
			</div>
			{#if kind === 'smart'}
				<QueryBuilder
					inline
					query={smartQuery}
					{catalogue}
					collections={pickerCollections}
					{collectionsFailed}
					onretrycollections={() => void loadCollectionChoices()}
					onchange={(next) => (smartQuery = next)}
				/>
			{/if}
			{#if saveError}
				<p role="alert" class="text-sm text-destructive">{saveError}</p>
			{/if}
			<div
				class={[
					'flex flex-wrap items-center justify-end gap-2',
					kind === 'smart' && 'sticky bottom-0 -mx-6 border-t bg-background px-6 py-4'
				]}
			>
				{#if showSmartReason}
					<p id="{kindId}-reason" class="w-full text-sm text-muted-foreground sm:mr-auto sm:w-auto">
						{smartReason}
					</p>
				{/if}
				<Button type="button" variant="outline" onclick={() => handleOpenChange(false)}>
					Cancel
				</Button>
				<Button
					type="submit"
					disabled={saving || smartReason !== null}
					aria-describedby={showSmartReason ? `${kindId}-reason` : undefined}
				>
					{saving ? 'Creating…' : 'Create collection'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
