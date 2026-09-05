<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { beforeNavigate, afterNavigate } from '$app/navigation';
	import { browser } from '$app/environment';
	import { LayoutGrid, List, Plus, SearchX } from '@lucide/svelte';
	import { captureController } from '$lib/capture.svelte.js';
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
	import * as Card from '$lib/components/ui/card/index.js';

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
	let viewMode = $state<'list' | 'grid'>('list');

	let selectedTypeLabel = $derived(
		allCategories.find((c) => c.slug === selectedType)?.label ?? selectedType
	);

	// Initialise view mode from localStorage
	$effect(() => {
		if (browser) {
			const stored = localStorage.getItem('collection-view');
			if (stored === 'grid' || stored === 'list') viewMode = stored;
		}
	});

	$effect(() => {
		if (browser) localStorage.setItem('collection-view', viewMode);
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
		function handleKey(e: KeyboardEvent) {
			if (
				e.key === '/' &&
				document.activeElement?.tagName !== 'INPUT' &&
				document.activeElement?.tagName !== 'TEXTAREA'
			) {
				e.preventDefault();
				searchEl?.focus();
			}
			if (e.key === 'Escape' && document.activeElement === searchEl) {
				searchInput = '';
				searchEl?.blur();
			}
		}
		window.addEventListener('keydown', handleKey);
		return () => window.removeEventListener('keydown', handleKey);
	});

	$effect(() => {
		if (page.url.searchParams.get('search') === '1') {
			setTimeout(() => searchEl?.focus(), 50);
			const url = new URL(window.location.href);
			url.searchParams.delete('search');
			history.replaceState({}, '', url);
		}
	});

	// Scroll preservation: save before navigating into an item, restore on return
	beforeNavigate(({ to }) => {
		if (to?.url.pathname.startsWith(resolve('/collection/'))) {
			savedScrollTop = document.getElementById('main-scroll')?.scrollTop ?? 0;
		}
	});

	afterNavigate(({ from }) => {
		if (from?.url.pathname.startsWith(resolve('/collection/'))) {
			const el = document.getElementById('main-scroll');
			if (el) el.scrollTop = savedScrollTop;
		}
	});
</script>

<svelte:head>
	<title>My Collection — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<div class="flex items-center justify-between gap-4">
			<h1 class="font-heading text-3xl font-semibold tracking-tight">My Collection</h1>
			<Button onclick={() => captureController.show()}>
				<Plus class="size-4" />
				New item
			</Button>
		</div>

		<div class="flex items-center gap-2">
			<input
				use:focusRef
				bind:value={searchInput}
				type="search"
				placeholder="Search your collection…"
				class="flex h-9 flex-1 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none sm:max-w-sm"
			/>
			<div class="ml-auto flex items-center gap-1">
				<button
					onclick={() => (viewMode = 'list')}
					class="rounded-md p-1.5 transition-colors {viewMode === 'list'
						? 'bg-muted text-foreground'
						: 'text-muted-foreground hover:text-foreground'}"
					aria-label="List view"
					aria-pressed={viewMode === 'list'}
				>
					<List class="size-4" />
				</button>
				<button
					onclick={() => (viewMode = 'grid')}
					class="rounded-md p-1.5 transition-colors {viewMode === 'grid'
						? 'bg-muted text-foreground'
						: 'text-muted-foreground hover:text-foreground'}"
					aria-label="Grid view"
					aria-pressed={viewMode === 'grid'}
				>
					<LayoutGrid class="size-4" />
				</button>
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

		{#if loading && items.length === 0}
			<Shimmer loading={true}>
				{#if viewMode === 'grid'}
					<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
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
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
				{#each items as item (item.id)}
					{@const catLabel = allCategories.find((c) => c.slug === item.type)?.label}
					<a href={resolve('/collection/[id]', { id: item.id })} class="group block">
						<div
							class="flex aspect-[3/4] flex-col overflow-hidden rounded-xl border bg-muted/30 transition-colors group-hover:bg-muted/60"
						>
							<!-- Image placeholder -->
							<div class="flex flex-1 items-center justify-center text-muted-foreground/30">
								<LayoutGrid class="size-10" />
							</div>
							<div class="border-t bg-background/80 px-2.5 py-2">
								<p class="truncate text-sm leading-tight font-medium">{item.name}</p>
								{#if catLabel}
									<p class="mt-0.5 truncate text-xs text-muted-foreground">{catLabel}</p>
								{/if}
							</div>
						</div>
					</a>
				{/each}
			</div>
		{:else}
			<div class="grid gap-3">
				{#each items as item (item.id)}
					<a href={resolve('/collection/[id]', { id: item.id })}>
						<Card.Root class="transition-colors hover:bg-muted/50">
							<Card.Header class="flex flex-row items-center justify-between gap-4 space-y-0">
								<div>
									<Card.Title>{item.name}</Card.Title>
									{#if item.description}
										<Card.Description class="line-clamp-1">{item.description}</Card.Description>
									{/if}
								</div>
								{#if item.type}
									{@const catLabel = allCategories.find((c) => c.slug === item.type)?.label}
									<Badge variant="secondary" class="shrink-0">
										{catLabel ?? item.type}
									</Badge>
								{/if}
							</Card.Header>
						</Card.Root>
					</a>
				{/each}
			</div>
		{/if}

		{#if items.length === 0 && !loading}
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
					<Button size="sm" onclick={() => captureController.show()}>
						<Plus class="size-4" />
						New item
					</Button>
				{:else}
					<LayoutGrid class="size-10 text-muted-foreground/50" />
					<div>
						<p class="font-medium">Nothing here yet</p>
						<p class="text-sm text-muted-foreground">Add your first item to get started</p>
					</div>
					<Button onclick={() => captureController.show()}>
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
