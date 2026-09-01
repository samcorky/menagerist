<script lang="ts">
	import { resolve } from '$app/paths';
	import { Package, Plus, ChevronRight } from '@lucide/svelte';
	import { captureController } from '$lib/capture.svelte.js';
	import {
		listNodes,
		listNodeTypes,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';

	let items = $state<NodeResponse[]>([]);
	let categories = $state<NodeTypeResponse[]>([]);
	let loading = $state(true);
	let totalItems = $state(0);

	let recentItems = $derived(items);
	let showNudge = $derived(!loading && totalItems >= 5 && categories.length === 0);

	$effect(() => {
		if (captureController.nodeCreationCount === 0) return;
		void loadData();
	});

	async function loadData() {
		loading = true;
		const [itemsResult, categoriesResult] = await Promise.all([
			listNodes({ query: { limit: 6 } }),
			listNodeTypes({ query: { limit: 50 } })
		]);
		items = itemsResult.data ?? [];
		const rawTotal = itemsResult.response?.headers.get('x-total-count');
		totalItems = rawTotal ? parseInt(rawTotal, 10) : items.length;
		categories = categoriesResult.data ?? [];
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
		{#if loading}
			<div class="space-y-3">
				<div class="h-8 w-48 animate-pulse rounded-lg bg-muted"></div>
				<div class="h-4 w-32 animate-pulse rounded bg-muted"></div>
			</div>
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
				{#each [1, 2, 3, 4, 5, 6] as s (s)}
					<div class="h-24 animate-pulse rounded-xl bg-muted"></div>
				{/each}
			</div>
		{:else if totalItems === 0}
			<div class="flex flex-col items-center gap-5 py-20 text-center">
				<div class="flex size-16 items-center justify-center rounded-2xl bg-muted">
					<Package class="size-8 text-muted-foreground" />
				</div>
				<div class="space-y-1.5">
					<h1 class="font-heading text-2xl font-semibold tracking-tight">
						Your collection is empty
					</h1>
					<p class="max-w-xs text-muted-foreground">
						Start by adding your first item — a film, a signed poster, a person, or anything you
						collect.
					</p>
				</div>
				<Button onclick={() => captureController.show()} size="lg">
					<Plus class="size-4" />
					Add your first item
				</Button>
			</div>
		{:else}
			<div class="flex items-start justify-between gap-4">
				<div>
					<h1 class="font-heading text-3xl font-semibold tracking-tight">My Collection</h1>
					<p class="mt-1 text-sm text-muted-foreground">
						{totalItems}
						{totalItems === 1 ? 'item' : 'items'}
						{#if categories.length > 0}
							· {categories.length}
							{categories.length === 1 ? 'category' : 'categories'}
						{/if}
					</p>
				</div>
				<Button onclick={() => captureController.show()}>
					<Plus class="size-4" />
					New item
				</Button>
			</div>

			<section class="space-y-3">
				<div class="flex items-center justify-between">
					<h2 class="font-heading text-lg font-semibold">Recently added</h2>
					<a
						href={resolve('/collection')}
						class="flex items-center gap-0.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
					>
						Browse all
						<ChevronRight class="size-3.5" />
					</a>
				</div>
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
					{#each recentItems as item (item.id)}
						<a href={resolve('/collection/[id]', { id: item.id })} class="group block">
							<Card.Root class="h-full transition-colors group-hover:bg-muted/50">
								<Card.Header class="p-4">
									<Card.Title class="line-clamp-2 text-sm leading-snug">{item.name}</Card.Title>
									{#if item.type}
										<Badge variant="secondary" class="mt-1 w-fit text-xs">{item.type}</Badge>
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

			{#if categories.length > 0}
				<section class="space-y-3">
					<h2 class="font-heading text-lg font-semibold">By category</h2>
					<div class="flex flex-wrap gap-2">
						{#each categories as cat (cat.slug)}
							<a
								href="{resolve('/collection')}?type={cat.slug}"
								class="flex items-center gap-1.5 rounded-full border border-border bg-background px-3.5 py-1.5 text-sm font-medium transition-colors hover:border-primary/40 hover:bg-muted"
							>
								{cat.label}
							</a>
						{/each}
						<a
							href={resolve('/collection')}
							class="flex items-center gap-1.5 rounded-full border border-dashed border-border px-3.5 py-1.5 text-sm text-muted-foreground transition-colors hover:border-border hover:text-foreground"
						>
							All items
						</a>
					</div>
				</section>
			{/if}

			{#if showNudge}
				<div class="rounded-xl border border-dashed bg-muted/30 p-5">
					<p class="font-heading font-medium">Tip: organise with categories</p>
					<p class="mt-1 text-sm text-muted-foreground">
						Give your items types like "Film", "Person", or "Event" to filter and browse your
						collection more easily.
					</p>
					<a
						href={resolve('/settings/categories')}
						class="mt-3 inline-flex items-center gap-1 text-sm font-medium underline-offset-2 hover:underline"
					>
						Set up categories
						<ChevronRight class="size-3.5" />
					</a>
				</div>
			{/if}
		{/if}
	</div>
</main>
