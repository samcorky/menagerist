<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { Pencil, Star, Trash2, X } from '@lucide/svelte';
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
	import { archivedKeys, mergeAttributeSchemas, readSchemaMeta } from '$lib/schema-meta';
	import { normalise, isSectionItem } from '$lib/layout';
	import { descriptorForProp } from '$lib/field-types';
	import { formatDateTime, formatRelativeTime } from '$lib/format-date';
	import BackButton from '$lib/components/back-button.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import TagList from '$lib/components/tag-list.svelte';
	import TagsInput from '$lib/components/tags-input.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import NotFound from '$lib/components/not-found.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Toggle } from '$lib/components/ui/toggle/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Item from '$lib/components/ui/item/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import ShimmerSlot from '$lib/components/shimmer-slot.svelte';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import * as Tooltip from '$lib/components/ui/popover-tooltip/index.js';
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
	let schemaLayout = $derived(
		nodeSchema ? normalise(readSchemaMeta(nodeSchema).layout, nodeSchema.properties) : []
	);
	let now = $state(new Date());
	$effect(() => {
		const id = setInterval(() => (now = new Date()), 60_000);
		return () => clearInterval(id);
	});

	let createdAt = $derived(
		node
			? {
					relative: formatRelativeTime(node.created_at, now),
					utc: formatDateTime(node.created_at).utc
				}
			: null
	);
	let updatedAt = $derived(
		node
			? {
					relative: formatRelativeTime(node.updated_at, now),
					utc: formatDateTime(node.updated_at).utc
				}
			: null
	);
	let wasEdited = $derived(node ? node.updated_at !== node.created_at : false);
	let loading = $state(true);
	let notFound = $state(false);
	let mode = $state<'read' | 'edit'>('read');

	let name = $state('');
	let description = $state('');
	let tags = $state<string[]>([]);
	let attributeRows = $state<AttributeRow[]>([]);
	let extraSchema = $state<AttributesSchema | null>(null);
	let extraLayout = $derived(
		extraSchema ? normalise(readSchemaMeta(extraSchema).layout, extraSchema.properties) : []
	);
	let attributeServerErrors = $state<Record<string, string> | null>(null);
	let saving = $state(false);
	let deletingNode = $state(false);
	let confirmDeleteNode = $state(false);

	let editingEdge = $state<EdgeResponse | null>(null);
	let editRows = $state<AttributeRow[]>([]);
	let editErrors = $state<Record<string, string> | null>(null);
	let savingEdge = $state(false);
	let edgeSchema = $derived(editingEdge ? edgeTypeSchemaOf(editingEdge) : null);
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
		edges = edgesResult.data ?? [];
		otherNodes = (nodesResult.data ?? []).filter((candidate) => candidate.id !== nodeId);
		edgeTypes = edgeTypesResult.data ?? [];
		nodeTypes = nodeTypesResult.data ?? [];
		// nodeSchema is a $derived and hasn't reacted to the nodeTypes assignment above
		// yet within this synchronous block, so use schemaOfType (reads nodeTypes directly)
		// rather than nodeSchema here.
		extraSchema = (node.extra_schema as AttributesSchema | null) ?? null;
		attributeRows = attributesToRows(
			node.attributes,
			mergeAttributeSchemas(schemaOfType(node.type), extraSchema)
		);
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
				attributes: rowsToAttributes(attributeRows, mergeAttributeSchemas(nodeSchema, extraSchema)),
				extra_schema: extraSchema
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
			extraSchema = (node.extra_schema as AttributesSchema | null) ?? null;
			attributeRows = attributesToRows(
				node.attributes,
				mergeAttributeSchemas(nodeSchema, extraSchema)
			);
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
		editRows = attributesToRows(edge.attributes, edgeTypeSchemaOf(edge));
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
													class="relative rounded-full border border-border bg-background px-2.5 py-1 text-xs transition-colors after:absolute after:-inset-1 after:content-[''] hover:border-primary/50 hover:bg-muted disabled:opacity-50"
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
									bind:extraSchema
									schema={nodeSchema}
									supportsExtraFields={true}
									nodeId={node?.id}
									nodeTypeId={nodeTypes.find((nt) => nt.slug === node?.type)?.id}
									serverErrors={attributeServerErrors}
									onPromoted={load}
								/>

								<div class="flex flex-wrap items-center justify-between gap-2">
									{#if !loading}
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
									<div class="ml-auto flex items-center gap-2">
										<Button type="button" variant="outline" onclick={handleCancelEdit}>
											Cancel
										</Button>
										<Button type="submit" disabled={saving || loading}>
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

								{#if !loading && node}
									<TagList tags={node.tags} />
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

								{#if !loading && (schemaLayout.length > 0 || extraLayout.length > 0)}
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

										{#if extraSchema && extraLayout.length > 0}
											{#each extraLayout as layoutItem (isSectionItem(layoutItem) ? layoutItem.id : layoutItem.key)}
												{#if !isSectionItem(layoutItem) && layoutItem.key in extraSchema.properties}
													{@render attrField(
														layoutItem.key,
														extraSchema.properties[layoutItem.key]
													)}
												{/if}
											{/each}
										{/if}
									</div>
								{/if}

								{#if !loading && createdAt && updatedAt}
									<p class="border-t border-input/60 pt-3 text-xs text-muted-foreground">
										<Tooltip.Root>
											<Tooltip.Trigger>
												{#snippet child({ props })}
													<span {...props} tabindex="-1">Added {createdAt.relative}</span>
												{/snippet}
											</Tooltip.Trigger>
											<Tooltip.Content>{createdAt.utc}</Tooltip.Content>
										</Tooltip.Root>
										{#if wasEdited}
											·
											<Tooltip.Root>
												<Tooltip.Trigger>
													{#snippet child({ props })}
														<span {...props} tabindex="-1">Updated {updatedAt.relative}</span>
													{/snippet}
												</Tooltip.Trigger>
												<Tooltip.Content>{updatedAt.utc}</Tooltip.Content>
											</Tooltip.Root>
										{/if}
									</p>
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
									<li>
										<Item.Root variant="outline">
											<Item.Content class="text-sm">
												<Item.Title class="truncate">{relationLabel}</Item.Title>
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
											</Item.Content>
											<Item.Actions>
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
											</Item.Actions>
										</Item.Root>
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
										<div
											class="fixed inset-0 z-40 bg-black/40 sm:hidden"
											onmousedown={() => (edgeTypeOpen = false)}
											aria-hidden="true"
										></div>
										<ul
											class="fixed inset-x-0 bottom-0 z-50 max-h-[60dvh] overflow-auto rounded-t-2xl border-t bg-popover p-2 shadow-xl sm:absolute sm:inset-x-auto sm:bottom-auto sm:mt-1 sm:max-h-40 sm:w-full sm:rounded-md sm:border sm:p-1 sm:shadow-md"
										>
											<li class="mx-auto mb-2 h-1.5 w-12 rounded-full bg-muted sm:hidden"></li>
											{#each filteredEdgeTypes as et (et.slug)}
												<li>
													<button
														type="button"
														class="flex w-full items-center justify-between rounded px-2 py-2.5 text-sm hover:bg-accent sm:py-1.5"
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
														class="relative rounded-full p-0.5 after:absolute after:-inset-2 after:content-[''] hover:bg-foreground/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
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
										<div
											class="fixed inset-0 z-40 bg-black/40 sm:hidden"
											onmousedown={() => (edgeTargetOpen = false)}
											aria-hidden="true"
										></div>
										<ul
											class="fixed inset-x-0 bottom-0 z-50 max-h-[60dvh] overflow-auto rounded-t-2xl border-t bg-popover p-2 shadow-xl sm:absolute sm:inset-x-auto sm:bottom-auto sm:mt-1 sm:max-h-52 sm:w-full sm:rounded-md sm:border sm:p-1 sm:shadow-md"
										>
											<li class="mx-auto mb-2 h-1.5 w-12 rounded-full bg-muted sm:hidden"></li>
											{#each filteredNodes as candidate (candidate.id)}
												<li>
													<button
														type="button"
														class="flex w-full items-center justify-between rounded px-2 py-2.5 text-sm hover:bg-accent sm:py-1.5"
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

<ResponsiveDialog.Root
	open={editingEdge !== null}
	onOpenChange={(v) => {
		if (!v) closeEditEdge();
	}}
>
	<ResponsiveDialog.Content
		title="Edit connection"
		size="lg"
		onCloseAutoFocus={(e) => {
			e.preventDefault();
			editTrigger?.focus();
		}}
	>
		{#if editingEdge}
			{@const editType = edgeTypesById.get(editingEdge.type)}
			{@const outgoing = editingEdge.source_id === nodeId}
			<ResponsiveDialog.Description class="truncate">
				{editType
					? outgoing
						? editType.label
						: (editType.reverse_label ?? editType.label)
					: editingEdge.type}
				{editingOther?.name ?? ''}
			</ResponsiveDialog.Description>
			<form class="mt-4 space-y-4" onsubmit={handleSaveEdge}>
				<AttributesEditor bind:rows={editRows} schema={edgeSchema} serverErrors={editErrors} />
				<div class="flex justify-end gap-2">
					<Button type="button" variant="outline" onclick={closeEditEdge}>Cancel</Button>
					<Button type="submit" disabled={savingEdge}>
						{savingEdge ? 'Saving…' : 'Save'}
					</Button>
				</div>
			</form>
		{/if}
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

<ConfirmDialog
	open={confirmDeleteNode}
	title="Delete item?"
	description={node ? `"${node.name}" and its connections will be permanently deleted.` : undefined}
	busy={deletingNode}
	busyLabel="Deleting…"
	confirmLabel="Delete"
	onOpenChange={(v) => (confirmDeleteNode = v)}
	onConfirm={handleDeleteNode}
/>
