<script lang="ts">
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { Package, Plus, ChevronRight, AlertCircle, Star, X } from '@lucide/svelte';
	import { captureController } from '$lib/capture.svelte.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import {
		listNodes,
		listNodeTypes,
		listExamplePacks,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Item from '$lib/components/ui/item/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { dismissExamplesBanner, isExamplesBannerDismissed } from '$lib/examples';

	// 30-day window per §18a
	const RECENT_DAYS = 30;
	const RECENT_LIMIT = 12;

	let allItems = $state<NodeResponse[]>([]);
	let categories = $state<NodeTypeResponse[]>([]);
	let loading = $state(true);
	let totalItems = $state(0);

	// §13a: don't flash a skeleton for loads under 300ms
	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading);
	});

	let categoryBySlug = $derived(new Map(categories.map((c) => [c.slug, c])));

	// "Recently added" - items with a created_at within the last 30 days
	let recentItems = $derived(
		allItems.filter((item) => {
			if (!item.created_at) return true; // no timestamp → include by default
			const age = Date.now() - new Date(item.created_at).getTime();
			return age <= RECENT_DAYS * 24 * 60 * 60 * 1000;
		})
	);

	// "Missing details" - no description and no attributes
	let missingDetails = $derived(
		allItems.filter(
			(item) => !item.description?.trim() && Object.keys(item.attributes ?? {}).length === 0
		)
	);

	let showNudge = $derived(!loading && totalItems >= 5 && categories.length === 0);

	$effect(() => {
		if (captureController.nodeCreationCount === 0) return;
		void loadData();
	});

	let favouriteItems = $state<NodeResponse[]>([]);
	// null until the pack list has loaded, so the line never shifts the layout
	let hasExamples = $state<boolean | null>(null);
	let examplesDismissed = $state(isExamplesBannerDismissed());

	async function loadData() {
		loading = true;
		const [itemsResult, categoriesResult, favouritesResult, examplesResult] = await Promise.all([
			listNodes({ query: { limit: RECENT_LIMIT } }),
			listNodeTypes({ query: { limit: 50 } }),
			listNodes({ query: { limit: 100, favourite: true } }),
			listExamplePacks().catch(() => null)
		]);
		allItems = itemsResult.data ?? [];
		const rawTotal = itemsResult.response?.headers.get('Total-Count');
		totalItems = rawTotal ? parseInt(rawTotal, 10) : allItems.length;
		categories = categoriesResult.data ?? [];
		favouriteItems = favouritesResult.data ?? [];
		hasExamples = examplesResult?.data
			? examplesResult.data.some((pack) => pack.installation?.status === 'installed')
			: null;
		loading = false;
	}

	$effect(() => {
		void loadData();
	});
</script>

<svelte:head>
	<title>Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-3xl flex-col gap-10">
		{#if loadingDisplay.show}
			<div class="space-y-3">
				<div class="h-8 w-48 animate-pulse rounded-lg bg-muted"></div>
				<div class="h-4 w-32 animate-pulse rounded bg-muted"></div>
			</div>
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
				{#each [1, 2, 3, 4, 5, 6] as s (s)}
					<div class="h-24 animate-pulse rounded-xl bg-muted"></div>
				{/each}
			</div>
		{:else if !loading && totalItems === 0}
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
		{:else if !loading}
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
			<div class="flex items-start justify-between gap-4">
				<div>
					<h1 class="font-heading text-3xl font-semibold tracking-tight">My items</h1>
					<p class="mt-1 text-sm text-muted-foreground">
						{totalItems}
						{totalItems === 1 ? 'item' : 'items'}
						{#if categories.length > 0}
							· {categories.length}
							{categories.length === 1 ? 'item type' : 'item types'}
						{/if}
					</p>
				</div>
				<Button onclick={() => goto(resolve('/items/new'))}>
					<Plus class="size-4" />
					New item
				</Button>
			</div>

			<!-- Recently added (30-day window) -->
			{#if recentItems.length > 0}
				<section class="space-y-3">
					<div class="flex items-center justify-between">
						<div>
							<h2 class="font-heading text-lg font-semibold">Recently added</h2>
							<p class="text-xs text-muted-foreground">Added in the last {RECENT_DAYS} days</p>
						</div>
						<a
							href={resolve('/items')}
							class="flex items-center gap-0.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
						>
							Browse all
							<ChevronRight class="size-3.5" />
						</a>
					</div>
					<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
						{#each recentItems.slice(0, 6) as item (item.id)}
							{@const catLabel = categoryBySlug.get(item.type ?? '')?.label}
							<a href={resolve('/items/[id]', { id: item.id })} class="group block">
								<Card.Root class="h-full transition-colors group-hover:bg-muted/50">
									<Card.Header class="p-4">
										<Card.Title class="line-clamp-2 text-sm leading-snug">{item.name}</Card.Title>
										{#if catLabel}
											<Badge variant="secondary" class="mt-1 w-fit text-xs">{catLabel}</Badge>
										{/if}
										{#if item.description}
											<Card.Description class="mt-1 line-clamp-2 text-xs"
												>{item.description}</Card.Description
											>
										{/if}
									</Card.Header>
								</Card.Root>
							</a>
						{/each}
					</div>
				</section>
			{/if}

			<!-- Favourites -->
			{#if favouriteItems.length > 0}
				<section class="space-y-3">
					<div class="flex items-center justify-between">
						<div>
							<h2 class="font-heading text-lg font-semibold">Favourites</h2>
							<p class="text-xs text-muted-foreground">
								{favouriteItems.length} starred {favouriteItems.length === 1 ? 'item' : 'items'}
							</p>
						</div>
					</div>
					<Item.Group>
						{#each favouriteItems as item (item.id)}
							{@const catLabel = categoryBySlug.get(item.type ?? '')?.label}
							<Item.Root variant="outline">
								{#snippet child({ props })}
									<a {...props} href={resolve('/items/[id]', { id: item.id })}>
										<Item.Content>
											<Item.Title>{item.name}</Item.Title>
											{#if catLabel}
												<Item.Description>{catLabel}</Item.Description>
											{/if}
										</Item.Content>
										<Item.Actions>
											<Star class="size-3.5 fill-current text-muted-foreground" />
										</Item.Actions>
									</a>
								{/snippet}
							</Item.Root>
						{/each}
					</Item.Group>
				</section>
			{/if}

			<!-- Missing details smart group -->
			{#if missingDetails.length > 0 && totalItems >= 3}
				<section class="space-y-3">
					<div class="flex items-center justify-between">
						<div>
							<h2 class="font-heading text-lg font-semibold">Missing details</h2>
							<p class="text-xs text-muted-foreground">
								{missingDetails.length}
								{missingDetails.length === 1 ? 'item has' : 'items have'} no description or extra information
							</p>
						</div>
					</div>
					<Item.Group>
						{#each missingDetails.slice(0, 5) as item (item.id)}
							{@const catLabel = categoryBySlug.get(item.type ?? '')?.label}
							<Item.Root variant="outline" class="border-dashed">
								{#snippet child({ props })}
									<a {...props} href={resolve('/items/[id]', { id: item.id })}>
										<Item.Content>
											<Item.Title>{item.name}</Item.Title>
											{#if catLabel}
												<Item.Description>{catLabel}</Item.Description>
											{/if}
										</Item.Content>
										<Item.Actions class="text-xs text-muted-foreground">
											<AlertCircle class="size-3.5" />
											Add information
										</Item.Actions>
									</a>
								{/snippet}
							</Item.Root>
						{/each}
					</Item.Group>
				</section>
			{/if}

			<!-- By item type -->
			{#if categories.length > 0}
				<section class="space-y-3">
					<h2 class="font-heading text-lg font-semibold">By item type</h2>
					<div class="flex flex-wrap gap-2">
						{#each categories as cat (cat.slug)}
							<a
								href="{resolve('/items')}?type={cat.slug}"
								class="flex items-center gap-1.5 rounded-full border border-border bg-background px-3.5 py-1.5 text-sm font-medium transition-colors hover:border-primary/40 hover:bg-muted"
							>
								{cat.label}
							</a>
						{/each}
						<a
							href={resolve('/items')}
							class="flex items-center gap-1.5 rounded-full border border-dashed border-border px-3.5 py-1.5 text-sm text-muted-foreground transition-colors hover:border-border hover:text-foreground"
						>
							All items
						</a>
					</div>
				</section>
			{/if}

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
	</div>
</main>
