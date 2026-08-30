<script lang="ts">
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { toast } from 'svelte-sonner';
	import { listNodeTypes, createNodeType, type NodeTypeResponse } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import * as Card from '$lib/components/ui/card/index.js';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3];

	let nodeTypes = $state<NodeTypeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(true);
	let slug = $state('');
	let label = $state('');
	let description = $state('');
	let submitting = $state(false);

	async function fetchPage(after?: string) {
		loading = true;

		const result = await listNodeTypes({ query: { after, limit: PAGE_SIZE } });

		if (result.error || !result.data) {
			toast.error("Couldn't load node types", { description: errorMessage(result.error) });
		} else {
			nodeTypes = after ? [...nodeTypes, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		loading = false;
	}

	function loadMore() {
		void fetchPage(nodeTypes.at(-1)?.id);
	}

	$effect(() => {
		void fetchPage();
	});

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		submitting = true;

		const result = await createNodeType({
			body: {
				slug,
				label,
				description: description || undefined
			}
		});

		if (result.error || !result.data) {
			toast.error("Couldn't create type", { description: errorMessage(result.error) });
		} else {
			nodeTypes = [result.data, ...nodeTypes];
			slug = '';
			label = '';
			description = '';
			toast.success('Type created');
		}
		submitting = false;
	}
</script>

<svelte:head>
	<title>Node Types</title>
</svelte:head>

<main class="flex-1 bg-background px-6 py-10 text-foreground">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<h1 class="text-3xl font-semibold tracking-tight">Node Types</h1>

		<Card.Root>
			<Card.Header>
				<Card.Title>New Type</Card.Title>
			</Card.Header>
			<Card.Content>
				<form class="space-y-4" onsubmit={handleSubmit}>
					<div class="space-y-1.5">
						<Label for="slug">Slug</Label>
						<Input
							id="slug"
							bind:value={slug}
							type="text"
							placeholder="e.g. film, person, place"
							required
						/>
					</div>
					<div class="space-y-1.5">
						<Label for="label">Label</Label>
						<Input
							id="label"
							bind:value={label}
							type="text"
							placeholder="e.g. Film, Person, Place"
							required
						/>
					</div>
					<div class="space-y-1.5">
						<Label for="description">Description</Label>
						<Textarea
							id="description"
							bind:value={description}
							placeholder="Optional description"
						/>
					</div>
					<div class="flex justify-end">
						<Button type="submit" disabled={submitting}>
							{submitting ? 'Adding…' : 'Add Type'}
						</Button>
					</div>
				</form>
			</Card.Content>
		</Card.Root>

		{#if loading && nodeTypes.length === 0}
			<Shimmer loading={true}>
				<div class="grid gap-3">
					{#each loadingSkeletons as skeleton (skeleton)}
						<div class="rounded-lg border p-4" aria-label={`Loading node type ${skeleton}`}>
							<div class="flex items-center justify-between gap-4">
								<div class="space-y-1">
									<div class="h-5 w-48 rounded bg-muted"></div>
									<div class="h-4 w-32 rounded-full bg-muted"></div>
								</div>
							</div>
						</div>
					{/each}
				</div>
			</Shimmer>
		{:else}
			<div class="grid gap-3">
				{#each nodeTypes as nodeType (nodeType.id)}
					<Card.Root>
						<Card.Header class="flex flex-row items-center justify-between gap-4 space-y-0">
							<div>
								<Card.Title>{nodeType.label}</Card.Title>
								{#if nodeType.description}
									<Card.Description>{nodeType.description}</Card.Description>
								{/if}
							</div>
							<Badge variant="secondary">{nodeType.slug}</Badge>
						</Card.Header>
					</Card.Root>
				{/each}
			</div>

			{#if nodeTypes.length === 0 && !loading}
				<p class="text-muted-foreground">No node types yet.</p>
			{/if}
		{/if}

		{#if hasMore && nodeTypes.length > 0}
			<div class="flex justify-center">
				<Button variant="outline" disabled={loading} onclick={loadMore}>
					{loading ? 'Loading…' : 'Load more'}
				</Button>
			</div>
		{/if}
	</div>
</main>
