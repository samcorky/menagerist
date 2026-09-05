<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { Star, Trash2 } from '@lucide/svelte';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import {
		createEdge,
		deleteEdge,
		deleteNode,
		getNode,
		listEdges,
		listEdgeTypes,
		listNodeTypes,
		listNodes,
		updateNode,
		type EdgeResponse,
		type EdgeTypeResponse,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { toast } from 'svelte-sonner';
	import AttributesEditor, {
		attributesToRows,
		rowsToAttributes,
		type AttributeRow
	} from '$lib/components/attributes-editor.svelte';
	import type { Schema } from '$lib/components/schema-editor.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Toggle } from '$lib/components/ui/toggle/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import ShimmerSlot from '$lib/components/shimmer-slot.svelte';
	import { Textarea } from '$lib/components/ui/textarea/index.js';

	let nodeId = $derived(page.params.id!);

	let node = $state<NodeResponse | null>(null);
	let edges = $state<EdgeResponse[]>([]);
	let otherNodes = $state<NodeResponse[]>([]);
	let edgeTypes = $state<EdgeTypeResponse[]>([]);
	let nodeTypes = $state<NodeTypeResponse[]>([]);
	let settingType = $state(false);
	let nodesById = $derived(new Map(otherNodes.map((candidate) => [candidate.id, candidate])));
	let edgeTypesById = $derived(new Map(edgeTypes.map((et) => [et.slug, et])));
	let nodeSchema = $derived(
		(nodeTypes.find((nt) => nt.slug === node?.type)?.attributes_schema as Schema | null) ?? null
	);
	let loading = $state(true);

	let name = $state('');
	let description = $state('');
	let attributeRows = $state<AttributeRow[]>([]);
	let saving = $state(false);
	let deletingNode = $state(false);

	let newEdgeType = $state('');
	let newEdgeTargetId = $state('');
	let creatingEdge = $state(false);
	let edgeTargetSearch = $state('');
	let edgeTargetOpen = $state(false);
	let filteredNodes = $derived(
		otherNodes.filter((n) =>
			`${n.name} ${n.type ?? ''}`.toLowerCase().includes(edgeTargetSearch.toLowerCase())
		)
	);
	let selectedNodeLabel = $derived(otherNodes.find((n) => n.id === newEdgeTargetId)?.name ?? '');

	// Autocomplete for relationship types
	let edgeTypeSearch = $state('');
	let edgeTypeOpen = $state(false);
	let filteredEdgeTypes = $derived(
		edgeTypes.filter(
			(et) =>
				et.label.toLowerCase().includes(edgeTypeSearch.toLowerCase()) ||
				et.slug.includes(edgeTypeSearch.toLowerCase())
		)
	);

	async function load() {
		loading = true;
		const [nodeResult, edgesResult, nodesResult, edgeTypesResult, nodeTypesResult] =
			await Promise.all([
				getNode({ path: { node_id: nodeId } }),
				listEdges({ query: { node_id: nodeId, limit: 100 } }),
				listNodes({ query: { limit: 500 } }),
				listEdgeTypes({ query: { limit: 100 } }),
				listNodeTypes({ query: { limit: 200 } })
			]);

		if (nodeResult.error || !nodeResult.data) {
			const { title, description: desc } = networkAwareError(nodeResult);
			toast.error(title, { description: desc });
			loading = false;
			return;
		}

		node = nodeResult.data;
		name = node.name;
		description = node.description ?? '';
		attributeRows = attributesToRows(node.attributes);
		edges = edgesResult.data ?? [];
		otherNodes = (nodesResult.data ?? []).filter((candidate) => candidate.id !== nodeId);
		edgeTypes = edgeTypesResult.data ?? [];
		nodeTypes = nodeTypesResult.data ?? [];
		loading = false;
	}

	$effect(() => {
		void load();
	});

	function otherNodeId(edge: EdgeResponse): string {
		return edge.source_id === nodeId ? edge.target_id : edge.source_id;
	}

	async function handleSetType(slug: string) {
		settingType = true;
		const result = await updateNode({ path: { node_id: nodeId }, body: { type: slug } });
		if (result.response?.status === 412) {
			toast.error('Edit conflict', {
				description: 'This item was updated elsewhere — refresh to see the latest version.'
			});
		} else if (result.error || !result.data) {
			toast.error("Couldn't set category", { description: errorMessage(result.error) });
		} else {
			node = result.data;
			toast.success('Category set');
		}
		settingType = false;
	}

	async function handleSave(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		const result = await updateNode({
			path: { node_id: nodeId },
			body: {
				name,
				description: description || null,
				attributes: rowsToAttributes(attributeRows)
			}
		});
		if (result.response?.status === 412) {
			toast.error('Edit conflict', {
				description: 'This item was edited elsewhere — refresh to see the latest version.'
			});
		} else if (result.error || !result.data) {
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
		} else {
			toast.success('Saved');
			node = result.data;
		}
		saving = false;
	}

	function handleDeleteNode() {
		const id = nodeId;
		deletingNode = true;

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deleteNode({ path: { node_id: id } });
			if (result.error) {
				deletingNode = false;
				const { title, description: desc } = networkAwareError(result);
				toast.error(title, { description: desc });
				return;
			}
			await goto(resolve('/collection'));
		}, 5000);

		toast('Item deleted', {
			action: {
				label: 'Undo',
				onClick: () => {
					undone = true;
					clearTimeout(timerId);
					deletingNode = false;
				}
			},
			duration: 5000
		});
	}

	async function handleToggleFavourite() {
		if (!node) return;
		const newValue = !node.favourite;
		node = { ...node, favourite: newValue };
		const result = await updateNode({ path: { node_id: nodeId }, body: { favourite: newValue } });
		if (result.error || !result.data) {
			node = { ...node, favourite: !newValue };
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
		} else {
			node = result.data;
		}
	}

	async function handleCreateEdge(event: SubmitEvent) {
		event.preventDefault();
		if (!newEdgeTargetId) {
			toast.error('Please select an item to connect to');
			return;
		}
		creatingEdge = true;
		const result = await createEdge({
			body: {
				source_id: nodeId,
				target_id: newEdgeTargetId,
				type: newEdgeType.trim(),
				attributes: {}
			}
		});
		if (result.error || !result.data) {
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
			if (result.response?.status === 404) {
				newEdgeTargetId = '';
				edgeTargetSearch = '';
			}
		} else {
			toast.success('Connection added');
			edges = [...edges, result.data];
			newEdgeType = '';
			newEdgeTargetId = '';
			edgeTargetSearch = '';
			edgeTypeSearch = '';
		}
		creatingEdge = false;
	}

	function handleDeleteEdge(edge: EdgeResponse) {
		// Optimistically remove
		edges = edges.filter((e) => e.id !== edge.id);

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deleteEdge({ path: { edge_id: edge.id } });
			if (result.error) {
				edges = [...edges, edge];
				const { title, description: desc } = networkAwareError(result);
				toast.error(title, { description: desc });
			}
		}, 5000);

		toast('Connection removed', {
			action: {
				label: 'Undo',
				onClick: () => {
					undone = true;
					clearTimeout(timerId);
					edges = [...edges, edge];
				}
			},
			duration: 5000
		});
	}
</script>

<svelte:head>
	<title>{node?.name ?? 'Item'} — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-2xl flex-col gap-6">
		<BackButton fallback={resolve('/collection')} />

		<Shimmer {loading}>
			<Card.Root>
				<Card.Header class="flex flex-row items-start justify-between gap-4 space-y-0">
					<div class="min-w-0 flex-1">
						<ShimmerSlot {loading} class="h-6 w-40">
							<Card.Title class="font-heading text-xl">{node?.name ?? ''}</Card.Title>
						</ShimmerSlot>
						<ShimmerSlot {loading} class="mt-1 h-4 w-56">
							{#if node?.type}
								{@const typeLabel = nodeTypes.find((nt) => nt.slug === node!.type)?.label}
								<Card.Description>
									{#if typeLabel}
										{typeLabel}
									{:else}
										<span
											class="font-mono text-xs text-muted-foreground/60 italic"
											title="This category no longer exists">{node.type}</span
										>
									{/if}
								</Card.Description>
							{:else if !loading && nodeTypes.length > 0}
								<div class="mt-2 space-y-1.5">
									<p class="text-xs text-muted-foreground">No category — pick one:</p>
									<div class="flex flex-wrap gap-1.5">
										{#each nodeTypes as nt (nt.slug)}
											<button
												type="button"
												onclick={() => handleSetType(nt.slug)}
												disabled={settingType}
												class="rounded-full border border-border bg-background px-2.5 py-0.5 text-xs transition-colors hover:border-primary/50 hover:bg-muted disabled:opacity-50"
											>
												{nt.label}
											</button>
										{/each}
									</div>
								</div>
							{/if}
						</ShimmerSlot>
					</div>
					{#if !loading}
						<Toggle
							pressed={node?.favourite ?? false}
							onPressedChange={handleToggleFavourite}
							aria-label={node?.favourite ? 'Remove from favourites' : 'Add to favourites'}
							class="shrink-0"
						>
							<Star class="size-4 {node?.favourite ? 'fill-current' : ''}" />
						</Toggle>
					{/if}
				</Card.Header>
				<Card.Content>
					<form class="space-y-4" onsubmit={handleSave}>
						<div class="space-y-2">
							<ShimmerSlot {loading} class="h-4 w-12">
								<Label for="name">Name</Label>
							</ShimmerSlot>
							<Input id="name" bind:value={name} required />
						</div>

						<div class="space-y-2">
							<ShimmerSlot {loading} class="h-4 w-24">
								<Label for="description">Description</Label>
							</ShimmerSlot>
							<Textarea id="description" bind:value={description} />
						</div>

						<AttributesEditor bind:rows={attributeRows} schema={nodeSchema} />

						<div class="flex flex-wrap items-center justify-between gap-2">
							{#if !loading}
								<Button
									type="button"
									variant="destructive"
									disabled={deletingNode}
									onclick={handleDeleteNode}
								>
									<Trash2 class="size-4" />
									{deletingNode ? 'Deleting…' : 'Delete'}
								</Button>
							{/if}
							<Button type="submit" disabled={saving || loading} class="ml-auto">
								{saving ? 'Saving…' : 'Save changes'}
							</Button>
						</div>
					</form>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title class="font-heading">Connected to</Card.Title>
				</Card.Header>
				<Card.Content class="space-y-4">
					{#if edges.length === 0}
						<p class="text-sm text-muted-foreground">No connections yet.</p>
					{:else}
						<ul class="space-y-2">
							{#each edges as edge (edge.id)}
								{@const et = edgeTypesById.get(edge.type)}
								{@const isOutgoing = edge.source_id === nodeId}
								{@const relationLabel = et
									? isOutgoing
										? et.label
										: (et.reverse_label ?? et.label)
									: edge.type}
								<li class="flex items-center justify-between gap-2 rounded-lg border p-3">
									<div class="text-sm">
										<span class="font-medium">{relationLabel}</span>
										<a
											href={resolve('/collection/[id]', { id: otherNodeId(edge) })}
											class="ml-2 text-muted-foreground underline"
										>
											{nodesById.get(otherNodeId(edge))?.name ?? 'View item'}
										</a>
									</div>
									<Button
										type="button"
										variant="ghost"
										size="icon"
										onclick={() => handleDeleteEdge(edge)}
										aria-label="Remove connection"
									>
										<Trash2 class="size-4" />
									</Button>
								</li>
							{/each}
						</ul>
					{/if}

					<Separator />

					<form class="space-y-3" onsubmit={handleCreateEdge}>
						<div class="space-y-2">
							<ShimmerSlot {loading} class="h-4 w-32">
								<Label for="edge-type">Relationship</Label>
							</ShimmerSlot>
							<div class="relative">
								<Input
									id="edge-type"
									value={edgeTypeOpen ? edgeTypeSearch : newEdgeType}
									placeholder="e.g. Directed by"
									autocomplete="off"
									oninput={(e) => {
										edgeTypeSearch = (e.target as HTMLInputElement).value;
										newEdgeType = edgeTypeSearch;
										edgeTypeOpen = true;
									}}
									onfocus={() => {
										edgeTypeOpen = true;
										edgeTypeSearch = newEdgeType;
									}}
									onblur={() => setTimeout(() => (edgeTypeOpen = false), 150)}
								/>
								{#if edgeTypeOpen && filteredEdgeTypes.length > 0}
									<ul
										class="absolute z-10 mt-1 max-h-40 w-full overflow-auto rounded-md border bg-popover p-1 shadow-md"
									>
										{#each filteredEdgeTypes as et (et.slug)}
											<li>
												<button
													type="button"
													class="flex w-full items-center justify-between rounded px-2 py-1.5 text-sm hover:bg-accent"
													onmousedown={() => {
														newEdgeType = et.slug;
														edgeTypeSearch = et.label;
														edgeTypeOpen = false;
													}}
												>
													<span>{et.label}</span>
													{#if et.reverse_label}
														<span class="text-xs text-muted-foreground">↔ {et.reverse_label}</span>
													{/if}
												</button>
											</li>
										{/each}
									</ul>
								{/if}
							</div>
						</div>

						<div class="space-y-2">
							<ShimmerSlot {loading} class="h-4 w-24">
								<Label for="edge-target">Item</Label>
							</ShimmerSlot>
							<div class="relative">
								<Input
									id="edge-target"
									value={edgeTargetOpen ? edgeTargetSearch : selectedNodeLabel}
									placeholder="Search items…"
									autocomplete="off"
									oninput={(e) => {
										edgeTargetSearch = (e.target as HTMLInputElement).value;
										edgeTargetOpen = true;
										newEdgeTargetId = '';
									}}
									onfocus={() => {
										edgeTargetOpen = true;
										edgeTargetSearch = '';
									}}
									onblur={() => setTimeout(() => (edgeTargetOpen = false), 150)}
								/>
								{#if edgeTargetOpen && filteredNodes.length > 0}
									<ul
										class="absolute z-10 mt-1 max-h-52 w-full overflow-auto rounded-md border bg-popover p-1 shadow-md"
									>
										{#each filteredNodes as candidate (candidate.id)}
											<li>
												<button
													type="button"
													class="flex w-full items-center justify-between rounded px-2 py-1.5 text-sm hover:bg-accent"
													onmousedown={() => {
														newEdgeTargetId = candidate.id;
														edgeTargetSearch = candidate.name;
														edgeTargetOpen = false;
													}}
												>
													<span>{candidate.name}</span>
													<span class="text-xs text-muted-foreground">{candidate.type ?? ''}</span>
												</button>
											</li>
										{/each}
									</ul>
								{/if}
								<input type="hidden" name="edge-target" value={newEdgeTargetId} />
							</div>
						</div>

						<div class="flex justify-end">
							<Button type="submit" disabled={creatingEdge}>
								{creatingEdge ? 'Connecting…' : 'Connect item'}
							</Button>
						</div>
					</form>
				</Card.Content>
			</Card.Root>
		</Shimmer>
	</div>
</main>
