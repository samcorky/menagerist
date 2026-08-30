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
		listNodes,
		updateNode,
		type EdgeResponse,
		type NodeResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { toast } from 'svelte-sonner';
	import AttributesEditor, {
		attributesToRows,
		rowsToAttributes,
		type AttributeRow
	} from '$lib/components/attributes-editor.svelte';
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
	let nodesById = $derived(new Map(otherNodes.map((candidate) => [candidate.id, candidate])));
	let loading = $state(true);

	let name = $state('');
	let description = $state('');
	let attributeRows = $state<AttributeRow[]>([]);
	let saving = $state(false);
	let deletingNode = $state(false);

	let newEdgeType = $state('');
	let newEdgeTargetId = $state('');
	let creatingEdge = $state(false);

	async function load() {
		loading = true;

		const [nodeResult, edgesResult, nodesResult] = await Promise.all([
			getNode({ path: { node_id: nodeId } }),
			listEdges({ query: { node_id: nodeId, limit: 100 } }),
			listNodes({ query: { limit: 100 } })
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
		loading = false;
	}

	$effect(() => {
		void load();
	});

	function otherNodeId(edge: EdgeResponse): string {
		return edge.source_id === nodeId ? edge.target_id : edge.source_id;
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
		if (!window.confirm(`Delete "${node?.name}"? This cannot be undone.`)) {
			return;
		}
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
		}
		creatingEdge = false;
	}

	async function handleDeleteEdge(edge: EdgeResponse) {
		if (!window.confirm('Remove this connection?')) {
			return;
		}
		const result = await deleteEdge({ path: { edge_id: edge.id } });
		if (!result.error) {
			edges = edges.filter((existing) => existing.id !== edge.id);
		}
	}
</script>

<svelte:head>
	<title>{node?.name ?? 'Node'}</title>
</svelte:head>

<main class="flex-1 bg-background px-6 py-10 text-foreground">
	<div class="mx-auto flex max-w-2xl flex-col gap-6">
		<Button variant="ghost" href={resolve('/nodes')} class="w-fit">← Back to Nodes</Button>

		<Shimmer {loading}>
			<Card.Root>
				<Card.Header>
					<ShimmerSlot {loading} class="h-6 w-40">
						<Card.Title>{node?.name ?? ''}</Card.Title>
					</ShimmerSlot>
					<ShimmerSlot {loading} class="mt-1 h-4 w-56">
						<Card.Description>Type: {node?.type ?? ''} (not editable)</Card.Description>
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

						<AttributesEditor bind:rows={attributeRows} />

						<div class="flex justify-between gap-2">
							{#if !loading}
								<Button
									type="button"
									variant="destructive"
									disabled={deletingNode}
									onclick={handleDeleteNode}
								>
									<Trash2 class="size-4" />
									Delete Node
								</Button>
							{/if}
							<Button type="submit" disabled={saving || loading}>
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
								<li class="flex items-center justify-between gap-2 rounded-lg border p-3">
									<div class="text-sm">
										<span class="font-medium">{edge.type}</span>
										<a
											href={resolve('/nodes/[id]', { id: otherNodeId(edge) })}
											class="ml-2 text-muted-foreground underline"
										>
											{nodesById.get(otherNodeId(edge))?.name ?? 'View connected node'}
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
							<select
								id="edge-target"
								bind:value={newEdgeTargetId}
								required
								class="h-9 w-full rounded-md border border-input bg-transparent px-2.5 text-sm"
							>
								<option value="" disabled selected>Select a node…</option>
								{#each otherNodes as candidate (candidate.id)}
									<option value={candidate.id}>{candidate.name} ({candidate.type})</option>
								{/each}
							</select>
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
