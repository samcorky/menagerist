<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { Trash2 } from '@lucide/svelte';
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
	import { errorMessage } from '$lib/api/errors';
	import { toast } from 'svelte-sonner';
	import AttributesEditor, {
		attributesToRows,
		rowsToAttributes,
		type AttributeRow
	} from '$lib/components/attributes-editor.svelte';
	import type { Schema } from '$lib/components/schema-editor.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
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
	let confirmingDeleteNode = $state(false);
	let confirmingEdgeId = $state<string | null>(null);

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

	async function load() {
		loading = true;

		const [nodeResult, edgesResult, nodesResult, edgeTypesResult, nodeTypesResult] =
			await Promise.all([
				getNode({ path: { node_id: nodeId } }),
				listEdges({ query: { node_id: nodeId, limit: 100 } }),
				listNodes({ query: { limit: 100 } }),
				listEdgeTypes({ query: { limit: 100 } }),
				listNodeTypes({ query: { limit: 200 } })
			]);

		if (nodeResult.error || !nodeResult.data) {
			toast.error("Couldn't load node", { description: errorMessage(nodeResult.error) });
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
		if (result.error || !result.data) {
			toast.error("Couldn't set type", { description: errorMessage(result.error) });
		} else {
			node = result.data;
			toast.success('Type set');
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
				description: 'This node was edited elsewhere — refresh to see the latest version.'
			});
		} else if (result.error || !result.data) {
			toast.error("Couldn't save changes", { description: errorMessage(result.error) });
		} else {
			toast.success('Saved');
			node = result.data;
		}
		saving = false;
	}

	async function handleDeleteNode() {
		if (!confirmingDeleteNode) {
			confirmingDeleteNode = true;
			return;
		}
		confirmingDeleteNode = false;
		deletingNode = true;
		const result = await deleteNode({ path: { node_id: nodeId } });
		if (result.error) {
			toast.error("Couldn't delete node", { description: errorMessage(result.error) });
			deletingNode = false;
			return;
		}
		toast.success('Node deleted');
		await goto(resolve('/nodes'));
	}

	async function handleCreateEdge(event: SubmitEvent) {
		event.preventDefault();
		if (!newEdgeTargetId) {
			toast.error('Please select a node to connect to');
			return;
		}
		creatingEdge = true;

		const result = await createEdge({
			body: { source_id: nodeId, target_id: newEdgeTargetId, type: newEdgeType, attributes: {} }
		});

		if (result.error || !result.data) {
			toast.error("Couldn't add connection", { description: errorMessage(result.error) });
		} else {
			toast.success('Connection added');
			edges = [...edges, result.data];
			newEdgeType = '';
			newEdgeTargetId = '';
			edgeTargetSearch = '';
		}
		creatingEdge = false;
	}

	async function handleDeleteEdge(edge: EdgeResponse) {
		if (confirmingEdgeId !== edge.id) {
			confirmingEdgeId = edge.id;
			return;
		}
		confirmingEdgeId = null;
		const result = await deleteEdge({ path: { edge_id: edge.id } });
		if (!result.error) {
			edges = edges.filter((existing) => existing.id !== edge.id);
			toast.success('Connection removed');
		} else {
			toast.error("Couldn't remove connection", { description: errorMessage(result.error) });
		}
	}
</script>

<svelte:head>
	<title>{node?.name ?? 'Node'}</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-2xl flex-col gap-6">
		<BackButton fallback={resolve('/nodes')} />

		<Shimmer {loading}>
			<Card.Root>
				<Card.Header>
					<ShimmerSlot {loading} class="h-6 w-40">
						<Card.Title>{node?.name ?? ''}</Card.Title>
					</ShimmerSlot>
					<ShimmerSlot {loading} class="mt-1 h-4 w-56">
						{#if node?.type}
							<Card.Description
								>Type: <span class="font-mono text-xs">{node.type}</span></Card.Description
							>
						{:else if !loading && nodeTypes.length > 0}
							<div class="mt-2 space-y-1.5">
								<p class="text-xs text-muted-foreground">No type — pick one:</p>
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
								{#if confirmingDeleteNode}
									<div class="flex gap-2">
										<Button
											type="button"
											variant="outline"
											onclick={() => (confirmingDeleteNode = false)}
										>
											Cancel
										</Button>
										<Button
											type="button"
											variant="destructive"
											disabled={deletingNode}
											onclick={handleDeleteNode}
										>
											Confirm delete
										</Button>
									</div>
								{:else}
									<Button
										type="button"
										variant="destructive"
										disabled={deletingNode}
										onclick={handleDeleteNode}
									>
										<Trash2 class="size-4" />
										Delete
									</Button>
								{/if}
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
					<Card.Title>Connections</Card.Title>
					<Card.Description>Edges touching this node, in either direction.</Card.Description>
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
											href={resolve('/nodes/[id]', { id: otherNodeId(edge) })}
											class="ml-2 text-muted-foreground underline"
										>
											{nodesById.get(otherNodeId(edge))?.name ?? 'View connected node'}
										</a>
									</div>
									{#if confirmingEdgeId === edge.id}
										<div class="flex gap-1">
											<Button
												type="button"
												variant="ghost"
												size="sm"
												onclick={() => (confirmingEdgeId = null)}
											>
												Cancel
											</Button>
											<Button
												type="button"
												variant="destructive"
												size="sm"
												onclick={() => handleDeleteEdge(edge)}
											>
												Remove
											</Button>
										</div>
									{:else}
										<Button
											type="button"
											variant="ghost"
											size="icon"
											onclick={() => handleDeleteEdge(edge)}
											aria-label="Remove connection"
										>
											<Trash2 class="size-4" />
										</Button>
									{/if}
								</li>
							{/each}
						</ul>
					{/if}

					<Separator />

					<form class="space-y-3" onsubmit={handleCreateEdge}>
						<div class="space-y-2">
							<ShimmerSlot {loading} class="h-4 w-32">
								<Label for="edge-type">Connection type</Label>
							</ShimmerSlot>
							<Input
								id="edge-type"
								bind:value={newEdgeType}
								required
								placeholder="e.g. directed-by"
							/>
						</div>

						<div class="space-y-2">
							<ShimmerSlot {loading} class="h-4 w-24">
								<Label for="edge-target">Connect to</Label>
							</ShimmerSlot>
							<div class="relative">
								<Input
									id="edge-target"
									value={edgeTargetOpen ? edgeTargetSearch : selectedNodeLabel}
									placeholder="Search nodes…"
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
								{creatingEdge ? 'Adding…' : 'Add connection'}
							</Button>
						</div>
					</form>
				</Card.Content>
			</Card.Root>
		</Shimmer>
	</div>
</main>
