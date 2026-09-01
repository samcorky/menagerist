<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { LayoutGrid, Plus, SearchX } from '@lucide/svelte';
	import { captureController } from '$lib/capture.svelte.js';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { toast } from 'svelte-sonner';
	import {
		listNodes,
		listNodeTypes,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3, 4, 5];

	let items = $state<NodeResponse[]>([]);
	let allCategories = $state<NodeTypeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(true);
	let selectedType = $state<string | null>(null);
	let fetchSeq = 0;
	let searchInput = $state('');
	let q = $state('');
	let searchEl = $state<HTMLInputElement | null>(null);

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
			toast.error("Couldn't load items", { description: errorMessage(result.error) });
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

		<input
			use:focusRef
			bind:value={searchInput}
			type="search"
			placeholder="Search your collection…"
			class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none sm:max-w-sm"
		/>

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
			</Shimmer>
		{:else}
			<div class="grid gap-3">
				{#each items as item (item.id)}
					<a href={resolve('/collection/[id]', { id: item.id })}>
						<Card.Root class="transition-colors hover:bg-muted/50">
							<Card.Header class="flex flex-row items-center justify-between gap-4 space-y-0">
								<div>
									<Card.Title>{item.name}</Card.Title>
									{#if item.description}
										<Card.Description>{item.description}</Card.Description>
									{/if}
								</div>
								{#if item.type}
									{@const catLabel = allCategories.find((c) => c.slug === item.type)?.label}
									<Badge
										variant={catLabel ? 'secondary' : 'outline'}
										class={catLabel ? '' : 'text-muted-foreground/60 italic'}
									>
										{catLabel ?? item.type}
									</Badge>
								{/if}
							</Card.Header>
						</Card.Root>
					</a>
				{/each}
			</div>

			{#if items.length === 0 && !loading}
				<div class="flex flex-col items-center gap-3 py-12 text-center">
					{#if q}
						<SearchX class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">Nothing matched "{q}"</p>
							<p class="text-sm text-muted-foreground">Try a different search term</p>
						</div>
						<Button variant="ghost" size="sm" onclick={() => (searchInput = '')}
							>Clear search</Button
						>
					{:else if selectedType}
						<LayoutGrid class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">No "{selectedType}" items yet</p>
							<p class="text-sm text-muted-foreground">Add one to get started</p>
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
