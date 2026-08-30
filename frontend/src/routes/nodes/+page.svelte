<script lang="ts">
	import { resolve } from '$app/paths';
	import { Plus } from '@lucide/svelte';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { toast } from 'svelte-sonner';
	import { listNodes, type NodeResponse } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Card from '$lib/components/ui/card/index.js';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3, 4, 5];

	let nodes = $state<NodeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(true);
	let selectedType = $state<string | null>(null);
	let knownTypes = $state<string[]>([]);
	let searchInput = $state('');
	let q = $state('');

	// Debounce: when searchInput changes, wait 300ms then reset list and commit q.
	// Guard against no-op updates (e.g. on mount where value === q === '') so the
	// fetch effect isn't skipped while nodes stay cleared.
	$effect(() => {
		const value = searchInput;
		const timer = setTimeout(() => {
			if (value === q) return;
			nodes = [];
			hasMore = true;
			q = value;
		}, 300);
		return () => clearTimeout(timer);
	});

	async function fetchPage(after?: string) {
		loading = true;

		const result = await listNodes({
			query: { after, limit: PAGE_SIZE, type: selectedType ?? undefined, q: q || undefined }
		});

		if (result.error || !result.data) {
			toast.error("Couldn't load nodes", { description: errorMessage(result.error) });
		} else {
			nodes = after ? [...nodes, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
			if (selectedType === null && !q) {
				knownTypes = [...new Set([...knownTypes, ...result.data.map((n) => n.type)])].sort();
			}
		}
		loading = false;
	}

	function loadMore() {
		void fetchPage(nodes.at(-1)?.id);
	}

	function selectType(type: string | null) {
		if (selectedType === type) return;
		nodes = [];
		hasMore = true;
		selectedType = type;
	}

	// fetchPage reads selectedType and q synchronously, so this effect re-runs
	// whenever either changes. selectType and the debounce effect handle resets
	// before the state changes that trigger this re-run.
	$effect(() => {
		void fetchPage();
	});
</script>

<svelte:head>
	<title>Nodes</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<div class="flex items-center justify-between gap-4">
			<h1 class="text-3xl font-semibold tracking-tight">Nodes</h1>
			<Button href={resolve('/nodes/new')}>
				<Plus class="size-4" />
				New Node
			</Button>
		</div>

		<Input bind:value={searchInput} type="search" placeholder="Search nodes…" class="max-w-sm" />

		{#if knownTypes.length > 1}
			<div class="flex flex-wrap gap-2">
				<Badge
					variant={selectedType === null ? 'default' : 'outline'}
					class="cursor-pointer"
					onclick={() => selectType(null)}
				>
					All
				</Badge>
				{#each knownTypes as type (type)}
					<Badge
						variant={selectedType === type ? 'default' : 'outline'}
						class="cursor-pointer"
						onclick={() => selectType(type)}
					>
						{type}
					</Badge>
				{/each}
			</div>
		{/if}

		{#if loading && nodes.length === 0}
			<Shimmer loading={true}>
				<div class="grid gap-3">
					{#each loadingSkeletons as skeleton (skeleton)}
						<div class="rounded-lg border p-4" aria-label={`Loading node ${skeleton}`}>
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
				{#each nodes as node (node.id)}
					<a href={resolve('/nodes/[id]', { id: node.id })}>
						<Card.Root class="transition-colors hover:bg-muted/50">
							<Card.Header class="flex flex-row items-center justify-between gap-4 space-y-0">
								<div>
									<Card.Title>{node.name}</Card.Title>
									{#if node.description}
										<Card.Description>{node.description}</Card.Description>
									{/if}
								</div>
								<Badge variant="secondary">{node.type}</Badge>
							</Card.Header>
						</Card.Root>
					</a>
				{/each}
			</div>

			{#if nodes.length === 0 && !loading}
				<p class="text-muted-foreground">
					{#if q}
						No results for "{q}".
					{:else if selectedType}
						No "{selectedType}" nodes.
					{:else}
						No nodes yet.
					{/if}
				</p>
			{/if}
		{/if}

		{#if hasMore && nodes.length > 0}
			<div class="flex justify-center">
				<Button variant="outline" disabled={loading} onclick={loadMore}>
					{loading ? 'Loading…' : 'Load more'}
				</Button>
			</div>
		{/if}
	</div>
</main>
