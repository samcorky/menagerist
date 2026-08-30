<script lang="ts">
	import { resolve } from '$app/paths';
	import { Plus } from '@lucide/svelte';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { listNodes, type NodeResponse } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3, 4, 5];

	let nodes = $state<NodeResponse[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let hasMore = $state(true);
	let selectedType = $state<string | null>(null);
	let knownTypes = $state<string[]>([]);

	async function fetchPage(after?: string) {
		loading = true;
		error = null;

		const result = await listNodes({
			query: { after, limit: PAGE_SIZE, type: selectedType ?? undefined }
		});

		if (result.error || !result.data) {
			error = errorMessage(result.error);
		} else {
			nodes = after ? [...nodes, ...result.data] : result.data;
			hasMore = result.data.length === PAGE_SIZE;
			if (selectedType === null) {
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

	// fetchPage reads selectedType synchronously, so this effect re-runs
	// whenever selectedType changes. selectType must NOT call fetchPage
	// directly to avoid a double request.
	$effect(() => {
		void fetchPage();
	});
</script>

<svelte:head>
	<title>Nodes</title>
</svelte:head>

<main class="flex-1 bg-background px-6 py-10 text-foreground">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<div class="flex items-center justify-between gap-4">
			<h1 class="text-3xl font-semibold tracking-tight">Nodes</h1>
			<Button href={resolve('/nodes/new')}>
				<Plus class="size-4" />
				New Node
			</Button>
		</div>

		{#if error}
			<Alert variant="destructive">
				<AlertTitle>Couldn't load nodes</AlertTitle>
				<AlertDescription>{error}</AlertDescription>
			</Alert>
		{/if}

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
					{selectedType ? `No "${selectedType}" nodes.` : 'No nodes yet.'}
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
