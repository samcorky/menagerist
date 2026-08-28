<script lang="ts">
	import { resolve } from '$app/paths';
	import { Plus } from '@lucide/svelte';
	import { listNodes, type NodeResponse } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';

	const PAGE_SIZE = 50;

	let nodes = $state<NodeResponse[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let hasMore = $state(true);

	async function fetchPage(after?: string) {
		loading = true;
		error = null;

		const result = await listNodes({ query: { after, limit: PAGE_SIZE } });

		if (result.error || !result.data) {
			error = errorMessage(result.error);
		} else {
			nodes = after ? [...nodes, ...result.data.items] : result.data.items;
			hasMore = result.data.items.length === PAGE_SIZE;
		}
		loading = false;
	}

	function loadMore() {
		void fetchPage(nodes.at(-1)?.id);
	}

	// Reads no reactive state synchronously before its first await, so this
	// effect has no tracked dependencies and only runs once, on mount -
	// `loadMore` (which does read `node`) only ever runs from the button
	// click below, never from here. See fetchPage(after) split above: an
	// effect calling a function that both reads and later reassigns the same
	// state creates a self-retriggering loop.
	$effect(() => {
		void fetchPage();
	});
</script>

<svelte:head>
	<title>Nodes</title>
</svelte:head>

<main class="min-h-screen bg-background px-6 py-10 text-foreground">
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
			<p class="text-muted-foreground">No nodes yet.</p>
		{/if}

		{#if hasMore}
			<div class="flex justify-center">
				<Button variant="outline" disabled={loading} onclick={loadMore}>
					{loading ? 'Loading…' : 'Load more'}
				</Button>
			</div>
		{/if}
	</div>
</main>
