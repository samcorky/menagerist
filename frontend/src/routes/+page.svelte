<script lang="ts">
	import { untrack } from 'svelte';
	import Page from '$lib/components/page.svelte';
	import CollapsibleSection from '$lib/components/collapsible-section.svelte';
	import NodeGridCard from '$lib/components/node-grid-card.svelte';
	import SurpriseButton from '$lib/components/surprise-button.svelte';
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { Package, Plus, Camera, ChevronRight, CircleCheck, RefreshCw, X } from '@lucide/svelte';
	import { auth } from '$lib/auth.svelte.js';
	import { captureController } from '$lib/capture.svelte.js';
	import { collectionRouteParams } from '$lib/collections';
	import { greeting, itemsHref, noPhotoQuery, percent, tidyRows } from '$lib/dashboard';
	import { formatRelativeTime } from '$lib/format-date';
	import {
		loadCollections,
		loadEdited,
		loadNewest,
		loadStats,
		loadTidy,
		loadTypeBreakdown,
		type Block,
		type Stats,
		type TidyResult,
		type TypeBreakdown
	} from '$lib/dashboard-sources';
	import { dismissExamplesBanner, isExamplesBannerDismissed } from '$lib/examples';
	import {
		listExamplePacks,
		type CollectionResponse,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { loadItemTypes } from '$lib/palette-sources';
	import { formatCount } from '$lib/query/items-page';
	import type { AttributesSchema } from '$lib/schema-types';
	import { Button } from '$lib/components/ui/button/index.js';

	// Each block holds its own result: null while loading, then ok or error.
	let stats = $state<Block<Stats> | null>(null);
	let newest = $state<Block<NodeResponse[]> | null>(null);
	let edited = $state<Block<NodeResponse[]> | null>(null);
	let collections = $state<Block<CollectionResponse[]> | null>(null);
	let breakdown = $state<Block<TypeBreakdown> | null>(null);
	let tidy = $state<TidyResult[] | null>(null);
	let types = $state<NodeTypeResponse[]>([]);
	// null until the pack list has loaded, so the line never shifts the layout
	let hasExamples = $state<boolean | null>(null);
	let examplesDismissed = $state(isExamplesBannerDismissed());

	const typeBySlug = $derived(new Map(types.map((t) => [t.slug, t])));
	const schemaOf = (slug: string | null | undefined) =>
		(typeBySlug.get(slug ?? '')?.attributes_schema as AttributesSchema | null | undefined) ?? null;

	const items = $derived(stats?.status === 'ok' ? stats.data.items : null);
	const isEmpty = $derived(items === 0);
	const topCollections = $derived(
		collections?.status === 'ok'
			? [...collections.data].sort((a, b) => b.item_count - a.item_count).slice(0, 5)
			: []
	);
	const smartCount = $derived(
		collections?.status === 'ok' ? collections.data.filter((c) => c.kind === 'dynamic').length : 0
	);
	const usedTypes = $derived(breakdown?.status === 'ok' ? breakdown.data.rows : []);
	const maxTypeCount = $derived(Math.max(1, ...usedTypes.map((row) => row.count)));
	const showNudge = $derived(
		items !== null && items >= 5 && breakdown?.status === 'ok' && usedTypes.length === 0
	);
	const nothingToTidy = $derived(
		tidy !== null && tidy.every((row) => row.count !== null && row.count.total === 0)
	);
	const firstName = $derived(auth.user?.display_name?.split(' ')[0] ?? '');
	const hello = $derived(greeting(new Date().getHours()));

	// Only the newest load may write: an older, slower one must not overwrite fresher numbers.
	let loadSeq = 0;
	async function loadData() {
		const seq = ++loadSeq;
		const stale = () => seq !== loadSeq;
		const typesPromise = loadItemTypes().catch(() => [] as NodeTypeResponse[]);
		void listExamplePacks()
			.then((result) => {
				if (stale()) return;
				hasExamples = result.data
					? result.data.some((pack) => pack.installation?.status === 'installed')
					: null;
			})
			.catch(() => !stale() && (hasExamples = null));
		void loadStats().then((result) => !stale() && (stats = result));
		void loadNewest().then((result) => !stale() && (newest = result));
		void loadEdited().then((result) => !stale() && (edited = result));
		const collectionsResult = await loadCollections();
		if (stale()) return;
		collections = collectionsResult;
		const loadedTypes = await typesPromise;
		if (stale()) return;
		types = loadedTypes;
		const breakdownResult = await loadTypeBreakdown(types);
		if (stale()) return;
		breakdown = breakdownResult;
		// "No item type" is asked against the types in use, which always fit one condition.
		const typeSlugs =
			breakdownResult.status === 'ok' ? breakdownResult.data.rows.map((row) => row.slug) : [];
		const tidyResult = await loadTidy(
			tidyRows({
				collectionIds:
					collectionsResult.status === 'ok' ? collectionsResult.data.map((c) => c.id) : [],
				typeSlugs
			})
		);
		if (!stale()) tidy = tidyResult;
	}

	// Loads once on arrival, and again each time an item is created while Home is open.
	$effect(() => {
		void captureController.nodeCreationCount;
		untrack(() => void loadData());
	});
</script>

<svelte:head>
	<title>Menagerist</title>
</svelte:head>

{#snippet retry(what: string)}
	<div
		class="flex items-center gap-2 rounded-xl border border-dashed p-3 text-sm text-muted-foreground"
	>
		Couldn't load {what}.
		<Button variant="outline" size="sm" onclick={() => void loadData()}>
			<RefreshCw class="size-3.5" />
			Try again
		</Button>
	</div>
{/snippet}

{#snippet tile(
	testid: string,
	label: string,
	value: string,
	note: string,
	href?: string,
	hideOnPhone = false
)}
	<svelte:element
		this={href ? 'a' : 'div'}
		{href}
		data-testid={testid}
		class="rounded-xl border bg-card p-3 {href
			? 'transition-colors hover:bg-muted/50'
			: ''} {hideOnPhone ? 'max-md:hidden' : ''}"
	>
		<p class="text-xs text-muted-foreground">{label}</p>
		<p class="font-heading text-2xl font-semibold tabular-nums">{value}</p>
		<p class="truncate text-xs text-muted-foreground">{note}</p>
	</svelte:element>
{/snippet}

<Page width="fluid" class="gap-5">
	{#if stats === null}
		<div class="space-y-3">
			<div class="h-8 w-56 animate-pulse rounded-lg bg-muted"></div>
			<div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
				{#each [1, 2, 3, 4, 5] as s (s)}
					<div class="h-[5.5rem] animate-pulse rounded-xl bg-muted"></div>
				{/each}
			</div>
		</div>
	{:else if isEmpty}
		<div class="flex flex-col items-center gap-5 py-20 text-center">
			<div class="flex size-16 items-center justify-center rounded-2xl bg-muted">
				<Package class="size-8 text-muted-foreground" />
			</div>
			<div class="space-y-1.5">
				<h1 class="font-heading text-2xl font-semibold tracking-tight">
					You don't have any items yet
				</h1>
				<p class="max-w-xs text-muted-foreground">
					Start by adding your first item - a film, a signed poster, a person, or anything you
					collect.
				</p>
			</div>
			<Button onclick={() => goto(resolve('/items/new'))} size="lg">
				<Plus class="size-4" />
				Add your first item
			</Button>
			<a
				href={resolve('/settings/examples')}
				class="text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
			>
				Or look around with some examples
			</a>
		</div>
	{:else}
		{#if hasExamples && !examplesDismissed}
			<div
				class="flex items-center justify-between gap-3 rounded-xl border bg-muted/30 px-4 py-3 text-sm"
			>
				<p>
					You have example items. Remove them when you're ready.
					<a
						href={resolve('/settings/examples')}
						class="font-medium underline-offset-2 hover:underline">Manage examples</a
					>
				</p>
				<Button
					variant="ghost"
					size="icon-sm"
					aria-label="Dismiss"
					onclick={() => {
						dismissExamplesBanner();
						examplesDismissed = true;
					}}
				>
					<X class="size-4" />
				</Button>
			</div>
		{/if}

		<div class="flex flex-wrap items-start justify-between gap-3">
			<div>
				<h1 class="font-heading text-3xl font-semibold tracking-tight">
					{hello}{firstName ? `, ${firstName}` : ''}
				</h1>
				<p class="mt-1 text-sm text-muted-foreground">
					{#if stats.status === 'ok'}
						{formatCount(stats.data.items, false)}
						{stats.data.items === 1 ? 'item' : 'items'}
						{#if collections?.status === 'ok'}
							across {collections.data.length}
							{collections.data.length === 1 ? 'collection' : 'collections'}
						{/if}
					{/if}
				</p>
			</div>
			<div class="flex flex-wrap gap-2">
				<Button onclick={() => goto(resolve('/items/new'))}>
					<Plus class="size-4" />
					New item
				</Button>
				<Button variant="outline" onclick={() => captureController.show()}>
					<Camera class="size-4" />
					Quick capture
				</Button>
				<SurpriseButton />
			</div>
		</div>

		{#if stats.status === 'error'}
			{@render retry('your totals')}
		{:else}
			{@const s = stats.data}
			<div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
				{@render tile(
					'stat-items',
					'Items',
					formatCount(s.items, false),
					`+${formatCount(s.month.total, s.month.capped)} in the last 30 days`,
					resolve('/items')
				)}
				{@render tile(
					'stat-collections',
					'Collections',
					collections?.status === 'ok' ? String(collections.data.length) : '–',
					collections?.status === 'ok' ? `${smartCount} smart` : '',
					resolve('/collections')
				)}
				{@render tile(
					'stat-types',
					'Item types',
					breakdown?.status === 'ok' ? String(usedTypes.length) : '–',
					'with items in them',
					undefined,
					true
				)}
				{@render tile(
					'stat-favourites',
					'Favourites',
					formatCount(s.favourites, false),
					`${percent(s.favourites, s.items)}% of items`
				)}
				{@render tile(
					'stat-photo',
					'With a photo',
					`${percent(s.withPhoto.total, s.items)}%`,
					s.withPhoto.capped
						? 'most have one'
						: `${formatCount(Math.max(0, s.items - s.withPhoto.total), false)} still need one`,
					resolve(itemsHref(noPhotoQuery()) as '/items')
				)}
			</div>
		{/if}

		<div class="grid items-start gap-x-6 gap-y-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
			<CollapsibleSection id="home-newest" title="Newly added" class="gap-3">
				{#snippet actions()}
					<a
						href={resolve('/items')}
						class="flex items-center gap-0.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
					>
						Browse all
						<ChevronRight class="size-3.5" />
					</a>
				{/snippet}
				{#if newest === null}
					<div class="h-32 animate-pulse rounded-xl bg-muted"></div>
				{:else if newest.status === 'error'}
					{@render retry('your newest items')}
				{:else}
					<div
						data-slot="node-grid"
						class="grid grid-cols-2 gap-2 max-sm:flex max-sm:snap-x max-sm:overflow-x-auto sm:grid-cols-[repeat(auto-fill,minmax(11rem,1fr))]"
					>
						{#each newest.data as item (item.id)}
							<div class="max-sm:w-40 max-sm:shrink-0 max-sm:snap-start">
								<NodeGridCard
									{item}
									schema={schemaOf(item.type)}
									categoryLabel={typeBySlug.get(item.type ?? '')?.label}
									typeIcon={typeBySlug.get(item.type ?? '')?.icon}
									typeColour={typeBySlug.get(item.type ?? '')?.colour}
								/>
							</div>
						{/each}
					</div>
				{/if}
			</CollapsibleSection>

			<CollapsibleSection id="home-tidy" title="Tidy up" class="gap-3">
				{#if tidy === null}
					<div class="h-32 animate-pulse rounded-xl bg-muted"></div>
				{:else if nothingToTidy}
					<p class="flex items-center gap-2 rounded-xl border p-3 text-sm text-muted-foreground">
						<CircleCheck class="size-4 text-emerald-600" />
						Nothing to tidy up.
					</p>
				{:else}
					<ul class="divide-y rounded-xl border bg-card">
						{#each tidy as result (result.row.id)}
							<li>
								<a
									href={resolve(itemsHref(result.row.query) as '/items')}
									class="flex min-h-10 items-center justify-between gap-3 px-3 py-2 text-sm transition-colors hover:bg-muted/50 pointer-coarse:min-h-11"
								>
									<span>{result.row.label}</span>
									<span class="flex items-center gap-1 font-medium tabular-nums">
										{result.count ? formatCount(result.count.total, result.count.capped) : '–'}
										<ChevronRight class="size-3.5 text-muted-foreground" />
									</span>
								</a>
							</li>
						{/each}
					</ul>
				{/if}
			</CollapsibleSection>
		</div>

		<div class="grid items-start gap-x-6 gap-y-5 md:grid-cols-2 xl:grid-cols-3">
			<CollapsibleSection id="home-collections" title="Collections" class="gap-3">
				{#snippet actions()}
					<a
						href={resolve('/collections')}
						class="flex items-center gap-0.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
					>
						All collections
						<ChevronRight class="size-3.5" />
					</a>
				{/snippet}
				{#if collections === null}
					<div class="h-24 animate-pulse rounded-xl bg-muted"></div>
				{:else if collections.status === 'error'}
					{@render retry('your collections')}
				{:else if topCollections.length === 0}
					<p class="rounded-xl border border-dashed p-3 text-sm text-muted-foreground">
						No collections yet.
						<a href={resolve('/collections')} class="font-medium underline-offset-2 hover:underline"
							>Create one</a
						>
					</p>
				{:else}
					<ul class="divide-y rounded-xl border bg-card">
						{#each topCollections as collection (collection.id)}
							<li>
								<a
									href={resolve('/collections/[id]', collectionRouteParams(collection))}
									class="flex min-h-10 items-center justify-between gap-3 px-3 py-2 text-sm transition-colors hover:bg-muted/50 pointer-coarse:min-h-11"
								>
									<span class="truncate">{collection.name}</span>
									<span class="shrink-0 text-muted-foreground tabular-nums">
										{formatCount(collection.item_count, collection.item_count_capped ?? false)}
									</span>
								</a>
							</li>
						{/each}
					</ul>
				{/if}
			</CollapsibleSection>

			<CollapsibleSection id="home-by-type" title="By item type" class="gap-3">
				{#if breakdown === null}
					<div class="h-24 animate-pulse rounded-xl bg-muted"></div>
				{:else if breakdown.status === 'error'}
					{@render retry('your item types')}
				{:else if usedTypes.length === 0}
					<p class="rounded-xl border border-dashed p-3 text-sm text-muted-foreground">
						None of your items has an item type yet.
						<a
							href={resolve('/settings/item-types')}
							class="font-medium underline-offset-2 hover:underline">Set up item types</a
						>
					</p>
				{:else}
					<ul class="space-y-1.5 rounded-xl border bg-card p-3">
						{#each usedTypes.slice(0, 6) as row (row.slug)}
							<li>
								<a
									href="{resolve('/items')}?type={encodeURIComponent(row.slug)}"
									class="block text-sm"
								>
									<span class="flex justify-between gap-3">
										<span class="truncate">{row.label}</span>
										<span class="text-muted-foreground tabular-nums"
											>{formatCount(row.count, false)}</span
										>
									</span>
									<span class="mt-1 block h-1.5 rounded-full bg-muted">
										<span
											class="block h-1.5 rounded-full bg-primary/70"
											style="width: {Math.max(4, (row.count / maxTypeCount) * 100)}%"
										></span>
									</span>
								</a>
							</li>
						{/each}
					</ul>
					{#if usedTypes.length > 6}
						<p class="text-xs text-muted-foreground">+{usedTypes.length - 6} more in use.</p>
					{/if}
				{/if}
			</CollapsibleSection>

			<CollapsibleSection id="home-edited" title="Pick up where you left off" class="gap-3">
				{#if edited === null}
					<div class="h-24 animate-pulse rounded-xl bg-muted"></div>
				{:else if edited.status === 'error'}
					{@render retry('your recent edits')}
				{:else}
					<ul class="divide-y rounded-xl border bg-card">
						{#each edited.data as item (item.id)}
							<li>
								<a
									href={resolve('/items/[id]', { id: item.id })}
									class="flex min-h-10 items-center justify-between gap-3 px-3 py-2 text-sm transition-colors hover:bg-muted/50 pointer-coarse:min-h-11"
								>
									<span class="truncate">{item.name}</span>
									<span class="shrink-0 text-xs text-muted-foreground">
										{formatRelativeTime(item.updated_at)}
									</span>
								</a>
							</li>
						{/each}
					</ul>
				{/if}
			</CollapsibleSection>
		</div>

		{#if showNudge}
			<div class="rounded-xl border border-dashed bg-muted/30 p-5">
				<p class="font-heading font-medium">Tip: organise with item types</p>
				<p class="mt-1 text-sm text-muted-foreground">
					Give your items types like "Film", "Person", or "Event" to filter and browse your items
					more easily.
				</p>
				<a
					href={resolve('/settings/item-types')}
					class="mt-3 inline-flex items-center gap-1 text-sm font-medium underline-offset-2 hover:underline"
				>
					Set up item types
					<ChevronRight class="size-3.5" />
				</a>
			</div>
		{/if}
	{/if}
</Page>
