<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import { Tag, Pencil, Plus, Trash2 } from '@lucide/svelte';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { toast } from 'svelte-sonner';
	import {
		listNodes,
		listNodeTypes,
		createNodeType,
		updateNodeType,
		deleteNodeType,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { slugify } from '$lib/utils.js';
	import { loadExampleIds } from '$lib/examples';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import { auth } from '$lib/auth.svelte.js';
	import BackButton from '$lib/components/back-button.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import IconButton from '$lib/components/icon-button.svelte';
	import TypeAppearanceFields from '$lib/components/type-appearance-fields.svelte';
	import TypeEditorDialog from '$lib/components/type-editor-dialog.svelte';
	import TypeIcon from '$lib/components/type-icon.svelte';
	import SchemaEditor from '$lib/components/schema-editor.svelte';
	import type { AttributesSchema } from '$lib/schema-types';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3];

	let categories = $state<NodeTypeResponse[]>([]);
	let loading = $state(false);
	let exampleTypeIds = $state<ReadonlySet<string>>(new Set());
	let hasMore = $state(true);

	// One editor serves both creating (editingId null) and editing.
	let editorOpen = $state(false);
	let editingId = $state<string | null>(null);
	let label = $state('');
	let description = $state('');
	let schema = $state<AttributesSchema | null>(null);
	let icon = $state<string | null>(null);
	let colour = $state<string | null>(null);
	let saving = $state(false);
	let query = $state('');

	let confirmTarget = $state<NodeTypeResponse | null>(null);
	let deletingId = $state<string | null>(null);

	async function fetchPage(after?: string) {
		loading = true;
		const result = await listNodeTypes({ query: { after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load item types", { description: errorMessage(result.error) });
		} else {
			categories = after ? [...categories, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		loading = false;
	}

	function sentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && hasMore && !loading) void fetchPage(categories.at(-1)?.id);
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

	function openCreate() {
		editingId = null;
		label = '';
		description = '';
		schema = null;
		icon = null;
		colour = null;
		editorOpen = true;
	}

	function openEdit(cat: NodeTypeResponse) {
		editingId = cat.id;
		label = cat.label;
		description = cat.description ?? '';
		schema = (cat.attributes_schema as AttributesSchema | null) ?? null;
		icon = cat.icon ?? null;
		colour = cat.colour ?? null;
		editorOpen = true;
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		if (editingId) {
			const id = editingId;
			const result = await updateNodeType({
				path: { node_type_id: id },
				// null removes an icon or colour; leaving the field out would keep it.
				body: {
					label,
					description: description || null,
					attributes_schema: schema,
					icon,
					colour
				}
			});
			if (result.error || !result.data) {
				toast.error("Couldn't save changes", { description: errorMessage(result.error) });
			} else {
				categories = categories.map((c) => (c.id === id ? result.data! : c));
				editorOpen = false;
				toast.success('Item type updated');
			}
		} else {
			const result = await createNodeType({
				body: {
					slug: slugify(label),
					label,
					description: description || undefined,
					attributes_schema: schema,
					icon: icon ?? undefined,
					colour: colour ?? undefined
				}
			});
			if (result.error || !result.data) {
				toast.error("Couldn't create item type", { description: errorMessage(result.error) });
			} else {
				categories = [result.data, ...categories];
				editorOpen = false;
				toast.success('Item type created');
			}
		}
		saving = false;
	}

	const fieldCount = (cat: NodeTypeResponse) =>
		Object.keys((cat.attributes_schema as AttributesSchema | null)?.properties ?? {}).length;

	// Searching only helps once the list is long enough to scan.
	const SEARCH_FROM = 8;
	const shown = $derived(
		query.trim() === ''
			? categories
			: categories.filter((c) =>
					`${c.label} ${c.slug}`.toLowerCase().includes(query.trim().toLowerCase())
				)
	);

	async function handleDelete(cat: NodeTypeResponse) {
		const inUse = await listNodes({ query: { type: cat.slug, limit: 1 } });
		const hasItems = (inUse.data?.length ?? 0) > 0;

		if (hasItems) {
			// Destructive - items will lose their item type. Require explicit confirmation.
			confirmTarget = cat;
			return;
		}

		// No items - optimistic removal with undo window
		categories = categories.filter((c) => c.id !== cat.id);

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deleteNodeType({ path: { node_type_id: cat.id } });
			if (result.error) {
				categories = [cat, ...categories];
				toast.error("Couldn't delete item type", { description: errorMessage(result.error) });
			}
		}, 5000);

		toast('Item type deleted', {
			action: {
				label: 'Undo',
				onClick: () => {
					undone = true;
					clearTimeout(timerId);
					categories = [cat, ...categories];
				}
			},
			duration: 5000
		});
	}

	async function confirmDelete() {
		const cat = confirmTarget;
		if (!cat) return;
		deletingId = cat.id;
		const result = await deleteNodeType({ path: { node_type_id: cat.id } });
		if (result.error) {
			toast.error("Couldn't delete item type", { description: errorMessage(result.error) });
		} else {
			categories = categories.filter((c) => c.id !== cat.id);
			toast.success('Item type deleted');
		}
		deletingId = null;
		confirmTarget = null;
	}

	$effect(() => {
		void fetchPage();
		void loadExampleIds().then((ids) => (exampleTypeIds = ids.itemTypes));
	});
</script>

<svelte:head>
	<title>Item types - Menagerist</title>
</svelte:head>

<Page width="reading">
	<BackButton fallback={resolve('/settings')} />

	<div class="flex items-start justify-between gap-4">
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Item types</h1>
			<p class="mt-1 text-muted-foreground">
				Organise your items with types like "Film", "Person", or "Event".
			</p>
		</div>
		<IconButton label="New item type" variant="default" onclick={openCreate}>
			<Plus />
		</IconButton>
	</div>

	{#if categories.length > SEARCH_FROM}
		<Input type="search" bind:value={query} placeholder="Search item types…" class="sm:max-w-sm" />
	{/if}

	{#if loading && categories.length === 0}
		<Shimmer loading={true}>
			<div class="grid gap-3">
				{#each loadingSkeletons as s (s)}
					<div class="rounded-lg border p-4">
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
		{#if shown.length > 0}
			<ul class="divide-y rounded-xl border bg-card">
				{#each shown as cat (cat.id)}
					<li class="flex items-center gap-3 px-3 py-2">
						<TypeIcon
							icon={cat.icon}
							colour={cat.colour}
							boxed
							class="size-8 rounded-lg text-base"
						/>
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-2">
								<span class="truncate font-medium">{cat.label}</span>
								{#if exampleTypeIds.has(cat.id)}
									<Badge variant="outline" class="shrink-0 text-muted-foreground">Example</Badge>
								{/if}
								<span class="shrink-0 font-mono text-xs text-muted-foreground">{cat.slug}</span>
							</div>
							{#if cat.description}
								<p class="truncate text-sm text-muted-foreground">{cat.description}</p>
							{/if}
						</div>
						<span class="hidden shrink-0 text-xs text-muted-foreground sm:inline">
							{fieldCount(cat) === 1 ? '1 field' : `${fieldCount(cat)} fields`}
						</span>
						<IconButton labelOnTouch={false} label="Edit item type" onclick={() => openEdit(cat)}>
							<Pencil />
						</IconButton>
						{#if auth.can('graph:node_type:delete')}
							<IconButton
								labelOnTouch={false}
								label="Delete item type"
								disabled={deletingId === cat.id}
								onclick={() => handleDelete(cat)}
							>
								<Trash2 />
							</IconButton>
						{/if}
					</li>
				{/each}
			</ul>
		{:else if query.trim() !== ''}
			<p class="py-8 text-center text-sm text-muted-foreground">
				No item types match "{query.trim()}".
			</p>
		{/if}

		{#if categories.length === 0 && !loading}
			<div class="flex flex-col items-center gap-3 py-12 text-center">
				<Tag class="size-10 text-muted-foreground/50" />
				<div>
					<p class="font-medium">No item types yet</p>
					<p class="text-sm text-muted-foreground">Create one to start organising your items.</p>
				</div>
			</div>
		{/if}
	{/if}

	{#if hasMore}
		<div use:sentinel class="flex justify-center py-4" aria-hidden="true">
			{#if loading}
				<div
					class="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground"
				></div>
			{/if}
		</div>
	{/if}
</Page>

<TypeEditorDialog
	open={editorOpen}
	title={editingId ? 'Edit item type' : 'New item type'}
	submitLabel={editingId ? 'Save' : 'Add item type'}
	busyLabel={editingId ? 'Saving…' : 'Adding…'}
	busy={saving}
	value={{ label, description, schema, icon, colour }}
	onSubmit={handleSubmit}
	onClose={() => (editorOpen = false)}
>
	<div class="space-y-1.5">
		<Label for="cat-label">Name</Label>
		<Input
			id="cat-label"
			bind:value={label}
			type="text"
			placeholder="e.g. Film, Person, Place"
			required
		/>
	</div>
	<div class="space-y-1.5">
		<Label for="cat-description">Description</Label>
		<Textarea id="cat-description" bind:value={description} placeholder="Optional description" />
	</div>
	<TypeAppearanceFields bind:icon bind:colour />
	<SchemaEditor
		bind:schema
		typeId={editingId ?? undefined}
		typeKind={editingId ? 'node' : undefined}
		highlights
	/>
</TypeEditorDialog>

<ConfirmDialog
	open={confirmTarget !== null}
	title="Delete item type?"
	description={confirmTarget
		? `Items using "${confirmTarget.label}" will lose this item type.`
		: undefined}
	busy={deletingId !== null}
	busyLabel="Deleting…"
	confirmLabel="Delete anyway"
	onOpenChange={(v) => {
		if (!v) confirmTarget = null;
	}}
	onConfirm={confirmDelete}
/>
