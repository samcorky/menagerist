<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { Pencil, Star, Trash2, X } from '@lucide/svelte';
	import { Dialog } from 'bits-ui';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import {
		createEdge,
		createEdges,
		deleteEdge,
		deleteNode,
		getNode,
		listEdges,
		listEdgeTypes,
		listNodeTypes,
		listNodes,
		updateEdge,
		updateNode,
		type EdgeResponse,
		type EdgeTypeResponse,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { toast } from 'svelte-sonner';
	import { attributesToRows, rowsToAttributes, type AttributeRow } from '$lib/attribute-rows';
	import AttributesEditor from '$lib/components/attributes-editor.svelte';
	import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';
	import { archivedKeys, readSchemaMeta } from '$lib/schema-meta';
	import { customDetailProblems, displayDetailValue, isDetailRow } from '$lib/custom-details';
	import { normalise, isSectionItem } from '$lib/layout';
	import { descriptorForProp } from '$lib/field-types';
	import BackButton from '$lib/components/back-button.svelte';
	import TagsInput from '$lib/components/tags-input.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import NotFound from '$lib/components/not-found.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Toggle } from '$lib/components/ui/toggle/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import ShimmerSlot from '$lib/components/shimmer-slot.svelte';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import { serverErrorsToFields } from '$lib/validation-messages';
	import MediaGallery from '$lib/components/media-gallery.svelte';
	import NodeCover from '$lib/components/node-cover.svelte';
	import NodeSummary from '$lib/components/node-summary.svelte';

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
		(nodeTypes.find((nt) => nt.slug === node?.type)
			?.attributes_schema as AttributesSchema | null) ?? null
	);
	let attributeLabelsByKey = $derived(
		new Map(
			Object.entries(nodeSchema?.properties ?? {}).map(([key, prop]) => [key, prop.title || key])
		)
	);
	let schemaLayout = $derived(
		nodeSchema ? normalise(readSchemaMeta(nodeSchema).layout, nodeSchema.properties) : []
	);
	let loading = $state(true);
	let notFound = $state(false);
	let mode = $state<'read' | 'edit'>('read');

	let name = $state('');
	let description = $state('');
	let tags = $state<string[]>([]);
	let attributeRows = $state<AttributeRow[]>([]);
	let freeformAttrRows = $derived(attributeRows.filter((r) => isDetailRow(r, nodeSchema)));
	let detailsBlocked = $derived(customDetailProblems(attributeRows, nodeSchema).blocking);
	let attributeServerErrors = $state<Record<string, string> | null>(null);
	let saving = $state(false);
	let deletingNode = $state(false);
	let confirmDeleteNode = $state(false);

	let editingEdge = $state<EdgeResponse | null>(null);
	let editRows = $state<AttributeRow[]>([]);
	let editErrors = $state<Record<string, string> | null>(null);
	let savingEdge = $state(false);
	let edgeSchema = $derived(editingEdge ? edgeTypeSchemaOf(editingEdge) : null);
	let edgeBlocked = $derived(customDetailProblems(editRows, edgeSchema).blocking);
	let editingOther = $derived(editingEdge ? nodesById.get(otherNodeId(editingEdge)) : undefined);
	let editTrigger: HTMLElement | null = null;

	let newEdgeType = $state('');
	let selectedTargets = $state<NodeResponse[]>([]);
	let newEdgeRows = $state<AttributeRow[]>([]);
	let creatingEdge = $state(false);
	let edgeTargetSearch = $state('');
	let edgeTargetOpen = $state(false);
	let filteredNodes = $derived(
		otherNodes.filter(
			(n) =>
				!selectedTargets.some((t) => t.id === n.id) &&
				`${n.name} ${n.type ?? ''}`.toLowerCase().includes(edgeTargetSearch.toLowerCase())
		)
	);

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
		notFound = false;
		const [nodeResult, edgesResult, nodesResult, edgeTypesResult, nodeTypesResult] =
			await Promise.all([
				getNode({ path: { node_id: nodeId } }),
				listEdges({ query: { node_id: nodeId, limit: 100 } }),
				listNodes({ query: { limit: 500 } }),
				listEdgeTypes({ query: { limit: 100 } }),
				listNodeTypes({ query: { limit: 200 } })
			]);

		if (nodeResult.response?.status === 404 || nodeResult.response?.status === 422) {
			notFound = true;
			loading = false;
			return;
		}

		if (nodeResult.error || !nodeResult.data) {
			const { title, description: desc } = networkAwareError(nodeResult);
			toast.error(title, { description: desc });
			loading = false;
			return;
		}

		node = nodeResult.data;
		name = node.name;
		description = node.description ?? '';
		tags = node.tags;
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

	function schemaOfType(slug: string | null | undefined): AttributesSchema | null {
		const type = nodeTypes.find((nt) => nt.slug === slug);
		return (type?.attributes_schema as AttributesSchema | null | undefined) ?? null;
	}

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
		attributeServerErrors = null;
		const result = await updateNode({
			path: { node_id: nodeId },
			body: {
				name,
				description: description || null,
				tags,
				attributes: rowsToAttributes(attributeRows, nodeSchema)
			}
		});
		if (result.response?.status === 412) {
			toast.error('Edit conflict', {
				description: 'This item was edited elsewhere — refresh to see the latest version.'
			});
		} else if (result.error || !result.data) {
			const fieldErrors =
				(
					result.error as {
						errors?: Array<{ path?: string; message?: string; keyword?: string; value?: unknown }>;
					} | null
				)?.errors ?? [];
			const placed = serverErrorsToFields(nodeSchema, fieldErrors);
			if (Object.keys(placed).length) {
				attributeServerErrors = placed;
			}
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
		} else {
			toast.success('Saved');
			node = result.data;
		}
		saving = false;
	}

	function handleCancelEdit() {
		if (node) {
			name = node.name;
			description = node.description ?? '';
			tags = node.tags;
			attributeRows = attributesToRows(node.attributes);
		}
		mode = 'read';
	}

	async function handleDeleteNode() {
		deletingNode = true;
		const result = await deleteNode({ path: { node_id: nodeId } });
		if (result.error) {
			deletingNode = false;
			confirmDeleteNode = false;
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
			return;
		}
		await goto(resolve('/collection'));
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

	function addSelectedTarget(candidate: NodeResponse) {
		if (selectedTargets.some((t) => t.id === candidate.id)) return;
		selectedTargets = [...selectedTargets, candidate];
		edgeTargetSearch = '';
	}

	function removeSelectedTarget(id: string) {
		selectedTargets = selectedTargets.filter((t) => t.id !== id);
	}

	async function handleCreateEdge(event: SubmitEvent) {
		event.preventDefault();
		if (selectedTargets.length === 0) {
			toast.error('Please select at least one item to connect to');
			return;
		}
		creatingEdge = true;
		const result = await createEdges({
			body: {
				source_id: nodeId,
				target_ids: selectedTargets.map((t) => t.id),
				type: newEdgeType.trim(),
				attributes: rowsToAttributes(
					newEdgeRows,
					edgeTypesById.get(newEdgeType)?.attributes_schema as AttributesSchema | null
				)
			}
		});
		if (result.error || !result.data) {
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
		} else {
			const { created, skipped } = result.data;
			edges = [...edges, ...created];
			const itemWord = created.length === 1 ? 'item' : 'items';
			const message =
				skipped.length === 0
					? `${created.length} ${itemWord} connected`
					: `${created.length} ${itemWord} connected, ${skipped.length} already connected`;
			toast(message, {
				action: { label: 'Undo', onClick: () => void undoCreateEdges(created) },
				duration: 5000
			});
			newEdgeType = '';
			selectedTargets = [];
			edgeTargetSearch = '';
			edgeTypeSearch = '';
			newEdgeRows = [];
		}
		creatingEdge = false;
	}

	async function undoCreateEdges(created: EdgeResponse[]) {
		const createdIds = new Set(created.map((e) => e.id));
		edges = edges.filter((e) => !createdIds.has(e.id));
		await Promise.all(
			created.map((edge) => deleteEdge({ path: { edge_id: edge.id } }).catch(() => undefined))
		);
	}

	function edgeTypeSchemaOf(edge: EdgeResponse): AttributesSchema | null {
		const schema = edgeTypesById.get(edge.type)?.attributes_schema as AttributesSchema | null;
		return schema ?? null;
	}

	function isEdgeEditable(edge: EdgeResponse): boolean {
		if (Object.keys(edge.attributes ?? {}).length > 0) return true;
		const schema = edgeTypeSchemaOf(edge);
		if (!schema) return false;
		const archived = archivedKeys(schema);
		return Object.keys(schema.properties).some((key) => !archived.has(key));
	}

	function openEditEdge(edge: EdgeResponse, trigger: HTMLElement) {
		editTrigger = trigger;
		editRows = attributesToRows(edge.attributes);
		editErrors = null;
		editingEdge = edge;
	}

	function closeEditEdge() {
		editingEdge = null;
	}

	async function handleSaveEdge(event: SubmitEvent) {
		event.preventDefault();
		const edge = editingEdge;
		if (!edge || savingEdge) return;
		savingEdge = true;
		editErrors = null;
		const result = await updateEdge({
			path: { edge_id: edge.id },
			body: { attributes: rowsToAttributes(editRows, edgeSchema) }
		});
		if (result.response?.status === 412) {
			toast.error('Edit conflict', {
				description: 'This connection was edited elsewhere — refresh to see the latest version.'
			});
		} else if (result.error || !result.data) {
			const fieldErrors =
				(
					result.error as {
						errors?: Array<{ path?: string; message?: string; keyword?: string; value?: unknown }>;
					} | null
				)?.errors ?? [];
			const placed = serverErrorsToFields(edgeSchema, fieldErrors);
			if (Object.keys(placed).length) {
				editErrors = placed;
			}
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
		} else {
			const saved = result.data;
			edges = edges.map((e) => (e.id === saved.id ? saved : e));
			editingEdge = null;
			toast.success('Saved');
		}
		savingEdge = false;
	}

	async function handleDeleteEdge(edge: EdgeResponse) {
		edges = edges.filter((e) => e.id !== edge.id);
		const result = await deleteEdge({ path: { edge_id: edge.id } });
		if (result.error) {
			edges = [...edges, edge];
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
			return;
		}
		toast('Connection removed', {
			action: { label: 'Undo', onClick: () => void recreateEdge(edge) },
			duration: 5000
		});
	}

	async function recreateEdge(edge: EdgeResponse) {
		const result = await createEdge({
			body: {
				source_id: edge.source_id,
				target_id: edge.target_id,
				type: edge.type,
				attributes: edge.attributes ?? {}
			}
		});
		if (result.error || !result.data) {
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
			return;
		}
		edges = [...edges, result.data];
	}
</script>

<svelte:head>
	<title>{node?.name ?? 'Item'} — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-2xl flex-col gap-6">
		<BackButton fallback={resolve('/collection')} />

		{#if notFound}
			<NotFound backHref={resolve('/collection')} />
		{:else}
			<Shimmer {loading}>
				<Card.Root class="overflow-hidden">
					{#if node}
						<NodeCover nodeId={node.id} class="w-full rounded-none" hiRes />
					{/if}
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
							<div class="flex shrink-0 items-center gap-1">
								<Toggle
									pressed={node?.favourite ?? false}
									onPressedChange={handleToggleFavourite}
									aria-label={node?.favourite ? 'Remove from favourites' : 'Add to favourites'}
								>
									<Star class="size-4 {node?.favourite ? 'fill-current' : ''}" />
								</Toggle>
								{#if mode === 'read'}
									<Button
										type="button"
										variant="ghost"
										size="icon"
										onclick={() => (mode = 'edit')}
										aria-label="Edit"
									>
										<Pencil class="size-4" />
									</Button>
								{/if}
							</div>
						{/if}
					</Card.Header>
					<Card.Content>
						{#if mode === 'edit'}
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

								<TagsInput bind:tags />

								<AttributesEditor
									bind:rows={attributeRows}
									schema={nodeSchema}
									serverErrors={attributeServerErrors}
								/>

								<div class="flex flex-wrap items-center justify-between gap-2">
									{#if !loading}
										{#if confirmDeleteNode}
											<div class="flex items-center gap-2">
												<span class="text-sm text-muted-foreground">Delete this item?</span>
												<Button
													type="button"
													variant="outline"
													size="sm"
													onclick={() => (confirmDeleteNode = false)}
												>
													Cancel
												</Button>
												<Button
													type="button"
													variant="destructive"
													size="sm"
													disabled={deletingNode}
													onclick={handleDeleteNode}
												>
													{deletingNode ? 'Deleting…' : 'Delete'}
												</Button>
											</div>
										{:else}
											<Button
												type="button"
												variant="destructive"
												disabled={deletingNode}
												onclick={() => (confirmDeleteNode = true)}
											>
												<Trash2 class="size-4" />
												Delete
											</Button>
										{/if}
									{/if}
									<div class="ml-auto flex items-center gap-2">
										<Button type="button" variant="outline" onclick={handleCancelEdit}>
											Cancel
										</Button>
										<Button type="submit" disabled={saving || loading || detailsBlocked}>
											{saving ? 'Saving…' : 'Save changes'}
										</Button>
									</div>
								</div>
							</form>
						{:else}
							<div class="space-y-4">
								<ShimmerSlot {loading} class="h-4 w-full">
									{#if node?.description}
										<p class="text-sm whitespace-pre-wrap">{node.description}</p>
									{:else}
										<p class="text-sm text-muted-foreground italic">No description.</p>
									{/if}
								</ShimmerSlot>

								{#if !loading && node && node.tags.length > 0}
									<ul class="flex flex-wrap gap-1.5" aria-label="Tags">
										{#each node.tags as tag (tag)}
											<li>
												<Badge variant="secondary">
													<span class="max-w-40 truncate" title={tag}>{tag}</span>
												</Badge>
											</li>
										{/each}
									</ul>
								{/if}

								{#snippet attrField(key: string, prop: JsonSchemaProperty)}
									{@const rawValue = attributeRows.find((r) => r.key === key)?.value}
									{#if rawValue !== undefined}
										{@const desc = descriptorForProp(prop)}
										{@const ViewWidget = desc?.ViewWidget}
										<div
											class="flex gap-2 {prop.type === 'array' ? 'items-start' : 'items-center'}"
										>
											<span class="w-32 shrink-0 pt-0.5 text-sm text-muted-foreground">
												{prop.title || key}
											</span>
											<div class="flex-1 text-sm">
												{#if ViewWidget}
													<ViewWidget value={rawValue} {prop} />
												{:else}
													{String(rawValue)}
												{/if}
											</div>
										</div>
									{/if}
								{/snippet}

								{#if !loading && (schemaLayout.length > 0 || freeformAttrRows.length > 0)}
									<div class="space-y-2">
										{#if nodeSchema && schemaLayout.length > 0}
											{#each schemaLayout as layoutItem (isSectionItem(layoutItem) ? layoutItem.id : layoutItem.key)}
												{#if isSectionItem(layoutItem)}
													<div class="space-y-1.5 pt-1">
														<p
															class="text-xs font-medium tracking-wide text-muted-foreground uppercase"
														>
															{layoutItem.section}
														</p>
														<div
															class="space-y-1.5 rounded-md border border-input/60 bg-muted/20 p-3"
														>
															{#each layoutItem.items as { key } (key)}
																{#if key in nodeSchema.properties}
																	{@render attrField(key, nodeSchema.properties[key])}
																{/if}
															{/each}
														</div>
													</div>
												{:else if layoutItem.key in nodeSchema.properties}
													{@render attrField(layoutItem.key, nodeSchema.properties[layoutItem.key])}
												{/if}
											{/each}
										{/if}

										{#if freeformAttrRows.length > 0}
											{#each freeformAttrRows as row (row)}
												<div class="flex items-center gap-2">
													<span class="w-32 shrink-0 text-sm text-muted-foreground">
														{attributeLabelsByKey.get(row.key) ?? row.key}
													</span>
													<span class="text-sm">{displayDetailValue(row)}</span>
												</div>
											{/each}
										{/if}
									</div>
								{/if}
							</div>
						{/if}
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
									{@const other = nodesById.get(otherNodeId(edge))}
									{@const rowSchema = edgeTypeSchemaOf(edge)}
									<li class="flex items-center justify-between gap-2 rounded-lg border p-3">
										<div class="min-w-0 flex-1 space-y-1 text-sm">
											<div class="truncate font-medium">{relationLabel}</div>
											<div class="flex min-w-0 items-center gap-2">
												<a
													href={resolve('/collection/[id]', { id: otherNodeId(edge) })}
													class="truncate text-muted-foreground underline"
												>
													{other?.name ?? 'View item'}
												</a>
												{#if other}
													<NodeSummary
														attributes={other.attributes}
														schema={schemaOfType(other.type)}
														surface="row"
														size="sm"
													/>
												{/if}
											</div>
											{#if rowSchema}
												<div class="truncate">
													<NodeSummary
														attributes={edge.attributes}
														schema={rowSchema}
														surface="connection"
														size="sm"
													/>
												</div>
											{/if}
										</div>
										<div class="flex shrink-0 items-center">
											{#if isEdgeEditable(edge)}
												<Button
													type="button"
													variant="ghost"
													size="icon"
													onclick={(e) => openEditEdge(edge, e.currentTarget)}
													aria-label="Edit connection"
												>
													<Pencil class="size-4" />
												</Button>
											{/if}
											<Button
												type="button"
												variant="ghost"
												size="icon"
												onclick={() => handleDeleteEdge(edge)}
												aria-label="Remove connection"
											>
												<Trash2 class="size-4" />
											</Button>
										</div>
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
											newEdgeRows = [];
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
															newEdgeRows = [];
															edgeTypeOpen = false;
														}}
													>
														<span>{et.label}</span>
														{#if et.reverse_label}
															<span class="text-xs text-muted-foreground">↔ {et.reverse_label}</span
															>
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
									<Label for="edge-target">{selectedTargets.length > 1 ? 'Items' : 'Item'}</Label>
								</ShimmerSlot>
								{#if selectedTargets.length > 0}
									<ul class="flex flex-wrap gap-1.5">
										{#each selectedTargets as target (target.id)}
											<li>
												<Badge variant="secondary" class="pr-1">
													<span class="max-w-40 truncate" title={target.name}>{target.name}</span>
													<button
														type="button"
														onclick={() => removeSelectedTarget(target.id)}
														aria-label="Remove {target.name}"
														class="rounded-full p-0.5 hover:bg-foreground/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
													>
														<X class="size-3" />
													</button>
												</Badge>
											</li>
										{/each}
									</ul>
								{/if}
								<div class="relative">
									<Input
										id="edge-target"
										bind:value={edgeTargetSearch}
										placeholder="Search items…"
										autocomplete="off"
										onfocus={() => (edgeTargetOpen = true)}
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
														onmousedown={(e) => {
															e.preventDefault();
															addSelectedTarget(candidate);
														}}
													>
														<span class="flex min-w-0 items-center gap-2">
															<span class="shrink-0">{candidate.name}</span>
															<NodeSummary
																attributes={candidate.attributes}
																schema={schemaOfType(candidate.type)}
																surface="picker"
																size="sm"
															/>
														</span>
														<span class="ml-2 shrink-0 text-xs text-muted-foreground"
															>{candidate.type ?? ''}</span
														>
													</button>
												</li>
											{/each}
										</ul>
									{/if}
								</div>
							</div>

							{#if edgeTypesById.get(newEdgeType)?.attributes_schema}
								<div class="space-y-2">
									<p class="text-xs text-muted-foreground">Applies to every connection you add.</p>
									<AttributesEditor
										bind:rows={newEdgeRows}
										schema={edgeTypesById.get(newEdgeType)
											?.attributes_schema as AttributesSchema | null}
									/>
								</div>
							{/if}

							<div class="flex justify-end">
								<Button type="submit" disabled={creatingEdge}>
									{creatingEdge
										? 'Connecting…'
										: selectedTargets.length > 1
											? 'Connect items'
											: 'Connect item'}
								</Button>
							</div>
						</form>
					</Card.Content>
				</Card.Root>

				{#if !loading}
					<Card.Root>
						<Card.Header>
							<Card.Title class="font-heading">Files</Card.Title>
						</Card.Header>
						<Card.Content>
							<MediaGallery {nodeId} />
						</Card.Content>
					</Card.Root>
				{/if}
			</Shimmer>
		{/if}
	</div>
</main>

<Dialog.Root
	open={editingEdge !== null}
	onOpenChange={(v) => {
		if (!v) closeEditEdge();
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
		<Dialog.Content
			aria-label="Edit connection"
			onCloseAutoFocus={(e) => {
				e.preventDefault();
				editTrigger?.focus();
			}}
			class="fixed right-0 bottom-0 left-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-2xl border-t bg-background p-6 shadow-xl sm:inset-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-full sm:max-w-lg sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border"
		>
			<div class="mx-auto mb-5 h-1.5 w-12 rounded-full bg-muted sm:hidden"></div>
			<div class="flex items-center justify-between">
				<Dialog.Title class="text-lg font-semibold">Edit connection</Dialog.Title>
				<button
					type="button"
					onclick={closeEditEdge}
					class="rounded-md p-1 text-muted-foreground hover:text-foreground"
					aria-label="Close"
				>
					<X class="size-4" />
				</button>
			</div>
			{#if editingEdge}
				{@const editType = edgeTypesById.get(editingEdge.type)}
				{@const outgoing = editingEdge.source_id === nodeId}
				<Dialog.Description class="mt-1 truncate text-sm text-muted-foreground">
					{editType
						? outgoing
							? editType.label
							: (editType.reverse_label ?? editType.label)
						: editingEdge.type}
					{editingOther?.name ?? ''}
				</Dialog.Description>
				<form class="mt-4 space-y-4" onsubmit={handleSaveEdge}>
					<AttributesEditor bind:rows={editRows} schema={edgeSchema} serverErrors={editErrors} />
					<div class="flex justify-end gap-2">
						<Button type="button" variant="outline" onclick={closeEditEdge}>Cancel</Button>
						<Button type="submit" disabled={savingEdge || edgeBlocked}>
							{savingEdge ? 'Saving…' : 'Save'}
						</Button>
					</div>
				</form>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
