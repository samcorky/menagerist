<script lang="ts">
	import { ArrowLeftRight, Pencil, Shapes, Trash2, X } from '@lucide/svelte';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { toast } from 'svelte-sonner';
	import {
		listNodeTypes,
		createNodeType,
		updateNodeType,
		deleteNodeType,
		listEdgeTypes,
		createEdgeType,
		updateEdgeType,
		deleteEdgeType,
		type NodeTypeResponse,
		type EdgeTypeResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { page } from '$app/state';
	import SchemaEditor, { type Schema } from '$lib/components/schema-editor.svelte';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3];

	// Tab state driven by ?tab= query param
	let tab = $state<'nodes' | 'edges'>(
		(page.url.searchParams.get('tab') as 'nodes' | 'edges') === 'edges' ? 'edges' : 'nodes'
	);

	function setTab(t: 'nodes' | 'edges') {
		tab = t;
		const url = new URL(window.location.href);
		url.searchParams.set('tab', t);
		history.replaceState({}, '', url.toString());
	}

	// ── Node Types ────────────────────────────────────────────────────────────
	let nodeTypes = $state<NodeTypeResponse[]>([]);
	let nodeLoading = $state(false);
	let nodeHasMore = $state(true);
	let nodeSlug = $state('');
	let nodeLabel = $state('');
	let nodeDescription = $state('');
	let nodeSubmitting = $state(false);

	let createNodeSchema = $state<Schema | null>(null);

	// edit / delete state
	let editingNodeTypeId = $state<string | null>(null);
	let editNodeLabel = $state('');
	let editNodeDescription = $state('');
	let editNodeSchema = $state<Schema | null>(null);
	let savingNodeTypeId = $state<string | null>(null);
	let confirmingDeleteNodeTypeId = $state<string | null>(null);
	let deletingNodeTypeId = $state<string | null>(null);

	async function fetchNodePage(after?: string) {
		nodeLoading = true;
		const result = await listNodeTypes({ query: { after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load node types", { description: errorMessage(result.error) });
		} else {
			nodeTypes = after ? [...nodeTypes, ...result.data] : result.data;
			nodeHasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		nodeLoading = false;
	}

	function loadMoreNodes() {
		void fetchNodePage(nodeTypes.at(-1)?.id);
	}

	function nodeSentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && nodeHasMore && !nodeLoading) loadMoreNodes();
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

	async function handleNodeSubmit(event: SubmitEvent) {
		event.preventDefault();
		nodeSubmitting = true;
		const result = await createNodeType({
			body: {
				slug: nodeSlug,
				label: nodeLabel,
				description: nodeDescription || undefined,
				attributes_schema: createNodeSchema
			}
		});
		if (result.error || !result.data) {
			toast.error("Couldn't create type", { description: errorMessage(result.error) });
		} else {
			nodeTypes = [result.data, ...nodeTypes];
			nodeSlug = '';
			nodeLabel = '';
			nodeDescription = '';
			createNodeSchema = null;
			toast.success('Type created');
		}
		nodeSubmitting = false;
	}

	function startEditNodeType(nt: NodeTypeResponse) {
		editingNodeTypeId = nt.id;
		editNodeLabel = nt.label;
		editNodeDescription = nt.description ?? '';
		editNodeSchema = (nt.attributes_schema as Schema | null) ?? null;
		confirmingDeleteNodeTypeId = null;
	}

	function cancelEditNodeType() {
		editingNodeTypeId = null;
		editNodeSchema = null;
	}

	async function handleNodeTypeUpdate(event: SubmitEvent, id: string) {
		event.preventDefault();
		savingNodeTypeId = id;
		const result = await updateNodeType({
			path: { node_type_id: id },
			body: {
				label: editNodeLabel,
				description: editNodeDescription || null,
				attributes_schema: editNodeSchema
			}
		});
		if (result.error || !result.data) {
			toast.error("Couldn't save changes", { description: errorMessage(result.error) });
		} else {
			nodeTypes = nodeTypes.map((nt) => (nt.id === id ? result.data! : nt));
			editingNodeTypeId = null;
			toast.success('Saved');
		}
		savingNodeTypeId = null;
	}

	async function handleNodeTypeDelete(nt: NodeTypeResponse) {
		if (confirmingDeleteNodeTypeId !== nt.id) {
			confirmingDeleteNodeTypeId = nt.id;
			editingNodeTypeId = null;
			return;
		}
		confirmingDeleteNodeTypeId = null;
		deletingNodeTypeId = nt.id;
		const result = await deleteNodeType({ path: { node_type_id: nt.id } });
		if (result.error) {
			toast.error("Couldn't delete type", { description: errorMessage(result.error) });
		} else {
			nodeTypes = nodeTypes.filter((existing) => existing.id !== nt.id);
			toast.success('Type deleted');
		}
		deletingNodeTypeId = null;
	}

	// ── Edge Types ────────────────────────────────────────────────────────────
	let edgeTypes = $state<EdgeTypeResponse[]>([]);
	let edgeLoading = $state(false);
	let edgeHasMore = $state(true);
	let edgeSlug = $state('');
	let edgeLabel = $state('');
	let edgeReverseLabel = $state('');
	let edgeDescription = $state('');
	let edgeDirectional = $state(true);
	let edgeSubmitting = $state(false);

	let createEdgeSchema = $state<Schema | null>(null);

	// edit / delete state
	let editingEdgeTypeId = $state<string | null>(null);
	let editEdgeLabel = $state('');
	let editEdgeReverseLabel = $state('');
	let editEdgeDescription = $state('');
	let editEdgeDirectional = $state(true);
	let editEdgeSchema = $state<Schema | null>(null);
	let savingEdgeTypeId = $state<string | null>(null);
	let confirmingDeleteEdgeTypeId = $state<string | null>(null);
	let deletingEdgeTypeId = $state<string | null>(null);

	async function fetchEdgePage(after?: string) {
		edgeLoading = true;
		const result = await listEdgeTypes({ query: { after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load edge types", { description: errorMessage(result.error) });
		} else {
			edgeTypes = after ? [...edgeTypes, ...result.data] : result.data;
			edgeHasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		edgeLoading = false;
	}

	function loadMoreEdges() {
		void fetchEdgePage(edgeTypes.at(-1)?.id);
	}

	function edgeSentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && edgeHasMore && !edgeLoading) loadMoreEdges();
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

	async function handleEdgeSubmit(event: SubmitEvent) {
		event.preventDefault();
		edgeSubmitting = true;
		const result = await createEdgeType({
			body: {
				slug: edgeSlug,
				label: edgeLabel,
				reverse_label: edgeReverseLabel || undefined,
				description: edgeDescription || undefined,
				directional: edgeDirectional,
				attributes_schema: createEdgeSchema
			}
		});
		if (result.error || !result.data) {
			toast.error("Couldn't create edge type", { description: errorMessage(result.error) });
		} else {
			edgeTypes = [result.data, ...edgeTypes];
			edgeSlug = '';
			edgeLabel = '';
			edgeReverseLabel = '';
			edgeDescription = '';
			edgeDirectional = true;
			createEdgeSchema = null;
			toast.success('Edge type created');
		}
		edgeSubmitting = false;
	}

	function startEditEdgeType(et: EdgeTypeResponse) {
		editingEdgeTypeId = et.id;
		editEdgeLabel = et.label;
		editEdgeReverseLabel = et.reverse_label ?? '';
		editEdgeDescription = et.description ?? '';
		editEdgeDirectional = et.directional;
		editEdgeSchema = (et.attributes_schema as Schema | null) ?? null;
		confirmingDeleteEdgeTypeId = null;
	}

	function cancelEditEdgeType() {
		editingEdgeTypeId = null;
		editEdgeSchema = null;
	}

	async function handleEdgeTypeUpdate(event: SubmitEvent, id: string) {
		event.preventDefault();
		savingEdgeTypeId = id;
		const result = await updateEdgeType({
			path: { edge_type_id: id },
			body: {
				label: editEdgeLabel,
				reverse_label: editEdgeReverseLabel || null,
				description: editEdgeDescription || null,
				directional: editEdgeDirectional,
				attributes_schema: editEdgeSchema
			}
		});
		if (result.error || !result.data) {
			toast.error("Couldn't save changes", { description: errorMessage(result.error) });
		} else {
			edgeTypes = edgeTypes.map((et) => (et.id === id ? result.data! : et));
			editingEdgeTypeId = null;
			toast.success('Saved');
		}
		savingEdgeTypeId = null;
	}

	async function handleEdgeTypeDelete(et: EdgeTypeResponse) {
		if (confirmingDeleteEdgeTypeId !== et.id) {
			confirmingDeleteEdgeTypeId = et.id;
			editingEdgeTypeId = null;
			return;
		}
		confirmingDeleteEdgeTypeId = null;
		deletingEdgeTypeId = et.id;
		const result = await deleteEdgeType({ path: { edge_type_id: et.id } });
		if (result.error) {
			toast.error("Couldn't delete edge type", { description: errorMessage(result.error) });
		} else {
			edgeTypes = edgeTypes.filter((existing) => existing.id !== et.id);
			toast.success('Edge type deleted');
		}
		deletingEdgeTypeId = null;
	}

	// Initial loads
	$effect(() => {
		void fetchNodePage();
	});
	$effect(() => {
		void fetchEdgePage();
	});
</script>

<svelte:head>
	<title>Types</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<h1 class="text-3xl font-semibold tracking-tight">Types</h1>

		<div class="flex w-fit gap-1 rounded-lg border p-1">
			<button
				class="rounded-md px-4 py-1.5 text-sm font-medium transition-colors {tab === 'nodes'
					? 'bg-background shadow-sm'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => setTab('nodes')}>Node Types</button
			>
			<button
				class="rounded-md px-4 py-1.5 text-sm font-medium transition-colors {tab === 'edges'
					? 'bg-background shadow-sm'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => setTab('edges')}>Edge Types</button
			>
		</div>

		{#if tab === 'nodes'}
			<!-- Node Types section -->
			<Card.Root>
				<Card.Header>
					<Card.Title>New Node Type</Card.Title>
				</Card.Header>
				<Card.Content>
					<form class="space-y-4" onsubmit={handleNodeSubmit}>
						<div class="space-y-1.5">
							<Label for="node-slug">Slug</Label>
							<Input
								id="node-slug"
								bind:value={nodeSlug}
								type="text"
								placeholder="e.g. film, person, place"
								required
							/>
						</div>
						<div class="space-y-1.5">
							<Label for="node-label">Label</Label>
							<Input
								id="node-label"
								bind:value={nodeLabel}
								type="text"
								placeholder="e.g. Film, Person, Place"
								required
							/>
						</div>
						<div class="space-y-1.5">
							<Label for="node-description">Description</Label>
							<Textarea
								id="node-description"
								bind:value={nodeDescription}
								placeholder="Optional description"
							/>
						</div>
						<SchemaEditor bind:schema={createNodeSchema} />
						<div class="flex justify-end">
							<Button type="submit" disabled={nodeSubmitting}>
								{nodeSubmitting ? 'Adding…' : 'Add Type'}
							</Button>
						</div>
					</form>
				</Card.Content>
			</Card.Root>

			{#if nodeLoading && nodeTypes.length === 0}
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
							<Card.Header class="flex flex-row items-start justify-between gap-4 space-y-0">
								<div class="min-w-0 flex-1">
									<Card.Title>{nodeType.label}</Card.Title>
									{#if nodeType.description}
										<Card.Description>{nodeType.description}</Card.Description>
									{/if}
								</div>
								<div class="flex shrink-0 items-center gap-1">
									<Badge variant="secondary">{nodeType.slug}</Badge>
									{#if confirmingDeleteNodeTypeId === nodeType.id}
										<Button
											type="button"
											variant="ghost"
											size="sm"
											onclick={() => (confirmingDeleteNodeTypeId = null)}
										>
											Cancel
										</Button>
										<Button
											type="button"
											variant="destructive"
											size="sm"
											disabled={deletingNodeTypeId === nodeType.id}
											onclick={() => handleNodeTypeDelete(nodeType)}
										>
											Confirm delete
										</Button>
									{:else}
										<Button
											type="button"
											variant="ghost"
											size="icon"
											onclick={() => startEditNodeType(nodeType)}
											aria-label="Edit type"
										>
											<Pencil class="size-4" />
										</Button>
										<Button
											type="button"
											variant="ghost"
											size="icon"
											disabled={deletingNodeTypeId === nodeType.id}
											onclick={() => handleNodeTypeDelete(nodeType)}
											aria-label="Delete type"
										>
											<Trash2 class="size-4" />
										</Button>
									{/if}
								</div>
							</Card.Header>

							{#if editingNodeTypeId === nodeType.id}
								<Card.Content class="border-t pt-4">
									<form class="space-y-3" onsubmit={(e) => handleNodeTypeUpdate(e, nodeType.id)}>
										<div class="space-y-1.5">
											<Label for="edit-node-label-{nodeType.id}">Label</Label>
											<Input
												id="edit-node-label-{nodeType.id}"
												bind:value={editNodeLabel}
												required
											/>
										</div>
										<div class="space-y-1.5">
											<Label for="edit-node-desc-{nodeType.id}">Description</Label>
											<Textarea
												id="edit-node-desc-{nodeType.id}"
												bind:value={editNodeDescription}
												placeholder="Optional description"
											/>
										</div>
										<SchemaEditor bind:schema={editNodeSchema} />
										<div class="flex justify-end gap-2">
											<Button type="button" variant="ghost" size="sm" onclick={cancelEditNodeType}>
												<X class="size-4" />
												Cancel
											</Button>
											<Button type="submit" size="sm" disabled={savingNodeTypeId === nodeType.id}>
												{savingNodeTypeId === nodeType.id ? 'Saving…' : 'Save'}
											</Button>
										</div>
									</form>
								</Card.Content>
							{/if}
						</Card.Root>
					{/each}
				</div>

				{#if nodeTypes.length === 0 && !nodeLoading}
					<div class="flex flex-col items-center gap-3 py-12 text-center">
						<Shapes class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">No node types yet</p>
							<p class="text-sm text-muted-foreground">
								Create a type above to start organising your nodes
							</p>
						</div>
					</div>
				{/if}
			{/if}

			{#if nodeHasMore}
				<div use:nodeSentinel class="flex justify-center py-4" aria-hidden="true">
					{#if nodeLoading}
						<div
							class="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground"
						></div>
					{/if}
				</div>
			{/if}
		{:else}
			<!-- Edge Types section -->
			<Card.Root>
				<Card.Header>
					<Card.Title>New Edge Type</Card.Title>
				</Card.Header>
				<Card.Content>
					<form class="space-y-4" onsubmit={handleEdgeSubmit}>
						<div class="space-y-1.5">
							<Label for="edge-slug">Slug</Label>
							<Input
								id="edge-slug"
								bind:value={edgeSlug}
								type="text"
								placeholder="e.g. directed-by, related-to"
								required
							/>
						</div>
						<div class="space-y-1.5">
							<Label for="edge-label">Label</Label>
							<Input
								id="edge-label"
								bind:value={edgeLabel}
								type="text"
								placeholder="e.g. Directed by, Related to"
								required
							/>
						</div>
						<div class="space-y-1.5">
							<Label for="edge-reverse-label">Reverse label</Label>
							<Input
								id="edge-reverse-label"
								bind:value={edgeReverseLabel}
								type="text"
								placeholder="e.g. Directed, Related to (optional)"
							/>
						</div>
						<div class="space-y-1.5">
							<Label for="edge-description">Description</Label>
							<Textarea
								id="edge-description"
								bind:value={edgeDescription}
								placeholder="Optional description"
							/>
						</div>
						<div class="flex items-center gap-2">
							<input
								id="edge-directional"
								type="checkbox"
								bind:checked={edgeDirectional}
								class="h-4 w-4 rounded border-input accent-primary"
							/>
							<div>
								<Label for="edge-directional">Directional relationship</Label>
								<p class="text-xs text-muted-foreground">
									Uncheck for symmetric relationships (A ↔ B)
								</p>
							</div>
						</div>
						<SchemaEditor bind:schema={createEdgeSchema} />
						<div class="flex justify-end">
							<Button type="submit" disabled={edgeSubmitting}>
								{edgeSubmitting ? 'Adding…' : 'Add Edge Type'}
							</Button>
						</div>
					</form>
				</Card.Content>
			</Card.Root>

			{#if edgeLoading && edgeTypes.length === 0}
				<Shimmer loading={true}>
					<div class="grid gap-3">
						{#each loadingSkeletons as skeleton (skeleton)}
							<div class="rounded-lg border p-4" aria-label={`Loading edge type ${skeleton}`}>
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
					{#each edgeTypes as edgeType (edgeType.id)}
						<Card.Root>
							<Card.Header class="flex flex-row items-start justify-between gap-4 space-y-0">
								<div class="min-w-0 flex-1">
									<Card.Title>{edgeType.label}</Card.Title>
									{#if edgeType.reverse_label}
										<p class="mt-0.5 text-sm text-muted-foreground">← {edgeType.reverse_label}</p>
									{/if}
									{#if edgeType.description}
										<Card.Description>{edgeType.description}</Card.Description>
									{/if}
								</div>
								<div class="flex shrink-0 flex-wrap items-center gap-1">
									<Badge variant="secondary">{edgeType.slug}</Badge>
									<Badge variant="outline">
										{edgeType.directional ? 'Directional →' : 'Symmetric ↔'}
									</Badge>
									{#if confirmingDeleteEdgeTypeId === edgeType.id}
										<Button
											type="button"
											variant="ghost"
											size="sm"
											onclick={() => (confirmingDeleteEdgeTypeId = null)}
										>
											Cancel
										</Button>
										<Button
											type="button"
											variant="destructive"
											size="sm"
											disabled={deletingEdgeTypeId === edgeType.id}
											onclick={() => handleEdgeTypeDelete(edgeType)}
										>
											Confirm delete
										</Button>
									{:else}
										<Button
											type="button"
											variant="ghost"
											size="icon"
											onclick={() => startEditEdgeType(edgeType)}
											aria-label="Edit edge type"
										>
											<Pencil class="size-4" />
										</Button>
										<Button
											type="button"
											variant="ghost"
											size="icon"
											disabled={deletingEdgeTypeId === edgeType.id}
											onclick={() => handleEdgeTypeDelete(edgeType)}
											aria-label="Delete edge type"
										>
											<Trash2 class="size-4" />
										</Button>
									{/if}
								</div>
							</Card.Header>

							{#if editingEdgeTypeId === edgeType.id}
								<Card.Content class="border-t pt-4">
									<form class="space-y-3" onsubmit={(e) => handleEdgeTypeUpdate(e, edgeType.id)}>
										<div class="space-y-1.5">
											<Label for="edit-edge-label-{edgeType.id}">Label</Label>
											<Input
												id="edit-edge-label-{edgeType.id}"
												bind:value={editEdgeLabel}
												required
											/>
										</div>
										<div class="space-y-1.5">
											<Label for="edit-edge-reverse-{edgeType.id}">Reverse label</Label>
											<Input
												id="edit-edge-reverse-{edgeType.id}"
												bind:value={editEdgeReverseLabel}
												placeholder="Optional"
											/>
										</div>
										<div class="space-y-1.5">
											<Label for="edit-edge-desc-{edgeType.id}">Description</Label>
											<Textarea
												id="edit-edge-desc-{edgeType.id}"
												bind:value={editEdgeDescription}
												placeholder="Optional description"
											/>
										</div>
										<div class="flex items-center gap-2">
											<input
												id="edit-edge-directional-{edgeType.id}"
												type="checkbox"
												bind:checked={editEdgeDirectional}
												class="h-4 w-4 rounded border-input accent-primary"
											/>
											<Label for="edit-edge-directional-{edgeType.id}">Directional</Label>
										</div>
										<SchemaEditor bind:schema={editEdgeSchema} />
										<div class="flex justify-end gap-2">
											<Button type="button" variant="ghost" size="sm" onclick={cancelEditEdgeType}>
												<X class="size-4" />
												Cancel
											</Button>
											<Button type="submit" size="sm" disabled={savingEdgeTypeId === edgeType.id}>
												{savingEdgeTypeId === edgeType.id ? 'Saving…' : 'Save'}
											</Button>
										</div>
									</form>
								</Card.Content>
							{/if}
						</Card.Root>
					{/each}
				</div>

				{#if edgeTypes.length === 0 && !edgeLoading}
					<div class="flex flex-col items-center gap-3 py-12 text-center">
						<ArrowLeftRight class="size-10 text-muted-foreground/50" />
						<div>
							<p class="font-medium">No edge types yet</p>
							<p class="text-sm text-muted-foreground">
								Create one above to give your connections meaning
							</p>
						</div>
					</div>
				{/if}
			{/if}

			{#if edgeHasMore}
				<div use:edgeSentinel class="flex justify-center py-4" aria-hidden="true">
					{#if edgeLoading}
						<div
							class="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground"
						></div>
					{/if}
				</div>
			{/if}
		{/if}
	</div>
</main>
