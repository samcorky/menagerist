<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import { ArrowLeftRight, Pencil, Plus, Trash2 } from '@lucide/svelte';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { toast } from 'svelte-sonner';
	import {
		listEdgeTypes,
		createEdgeType,
		updateEdgeType,
		deleteEdgeType,
		type EdgeTypeResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { slugify } from '$lib/utils.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { auth } from '$lib/auth.svelte.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import BackButton from '$lib/components/back-button.svelte';
	import IconButton from '$lib/components/icon-button.svelte';
	import TypeEditorDialog from '$lib/components/type-editor-dialog.svelte';
	import SchemaEditor from '$lib/components/schema-editor.svelte';
	import type { AttributesSchema } from '$lib/schema-types';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3];

	let relTypes = $state<EdgeTypeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(true);

	// One editor serves both creating (editingId null) and editing.
	let editorOpen = $state(false);
	let editingId = $state<string | null>(null);
	let label = $state('');
	let reverseLabel = $state('');
	let description = $state('');
	let directional = $state(true);
	let schema = $state<AttributesSchema | null>(null);
	let saving = $state(false);

	async function fetchPage(after?: string) {
		loading = true;
		const result = await listEdgeTypes({ query: { after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load relationship types", { description: errorMessage(result.error) });
		} else {
			relTypes = after ? [...relTypes, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		loading = false;
	}

	function sentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && hasMore && !loading) void fetchPage(relTypes.at(-1)?.id);
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
		reverseLabel = '';
		description = '';
		directional = true;
		schema = null;
		editorOpen = true;
	}

	function openEdit(et: EdgeTypeResponse) {
		editingId = et.id;
		label = et.label;
		reverseLabel = et.reverse_label ?? '';
		description = et.description ?? '';
		directional = et.directional;
		schema = (et.attributes_schema as AttributesSchema | null) ?? null;
		editorOpen = true;
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		if (editingId) {
			const id = editingId;
			const result = await updateEdgeType({
				path: { edge_type_id: id },
				body: {
					label,
					reverse_label: reverseLabel || null,
					description: description || null,
					directional,
					attributes_schema: schema
				}
			});
			if (result.error || !result.data) {
				toast.error("Couldn't save changes", { description: errorMessage(result.error) });
			} else {
				relTypes = relTypes.map((et) => (et.id === id ? result.data! : et));
				editorOpen = false;
				toast.success('Saved');
			}
		} else {
			const result = await createEdgeType({
				body: {
					slug: slugify(label),
					label,
					reverse_label: reverseLabel || undefined,
					description: description || undefined,
					directional,
					attributes_schema: schema
				}
			});
			if (result.error || !result.data) {
				toast.error("Couldn't create relationship type", {
					description: errorMessage(result.error)
				});
			} else {
				relTypes = [result.data, ...relTypes];
				editorOpen = false;
				toast.success('Relationship type created');
			}
		}
		saving = false;
	}

	function handleDelete(et: EdgeTypeResponse) {
		// Optimistically remove with undo window; restore if the server rejects (e.g. 409 in use)
		relTypes = relTypes.filter((r) => r.id !== et.id);

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deleteEdgeType({ path: { edge_type_id: et.id } });
			if (result.response?.status === 409) {
				relTypes = [et, ...relTypes];
				toast.error("Can't delete - connections still use this type", {
					description: 'Remove those connections first, or keep this relationship type.'
				});
			} else if (result.error) {
				relTypes = [et, ...relTypes];
				toast.error("Couldn't delete relationship type", {
					description: errorMessage(result.error)
				});
			}
		}, 5000);

		toast('Relationship type deleted', {
			action: {
				label: 'Undo',
				onClick: () => {
					undone = true;
					clearTimeout(timerId);
					relTypes = [et, ...relTypes];
				}
			},
			duration: 5000
		});
	}

	$effect(() => {
		void fetchPage();
	});
</script>

<svelte:head>
	<title>Relationship types - Menagerist</title>
</svelte:head>

<Page width="reading">
	<BackButton fallback={resolve('/settings')} />

	<div class="flex items-start justify-between gap-4">
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Relationship types</h1>
			<p class="mt-1 text-muted-foreground">
				Define how items connect - "Directed by", "Signed by", "Part of".
			</p>
		</div>
		<IconButton label="New relationship type" variant="default" onclick={openCreate}>
			<Plus />
		</IconButton>
	</div>

	{#if loading && relTypes.length === 0}
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
		{#if relTypes.length > 0}
			<ul class="divide-y rounded-xl border bg-card">
				{#each relTypes as et (et.id)}
					<li class="flex items-center gap-3 px-3 py-2">
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-2">
								<span class="truncate font-medium">{et.label}</span>
								{#if et.reverse_label}
									<span class="truncate text-sm text-muted-foreground">← {et.reverse_label}</span>
								{/if}
								<span class="shrink-0 font-mono text-xs text-muted-foreground">{et.slug}</span>
							</div>
							{#if et.description}
								<p class="truncate text-sm text-muted-foreground">{et.description}</p>
							{/if}
						</div>
						<Badge variant="outline" class="hidden shrink-0 sm:inline-flex">
							{et.directional ? 'Directional →' : 'Symmetric ↔'}
						</Badge>
						<IconButton
							labelOnTouch={false}
							label="Edit relationship type"
							onclick={() => openEdit(et)}
						>
							<Pencil />
						</IconButton>
						{#if auth.can('graph:edge_type:delete')}
							<IconButton
								labelOnTouch={false}
								label="Delete relationship type"
								onclick={() => handleDelete(et)}
							>
								<Trash2 />
							</IconButton>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}

		{#if relTypes.length === 0 && !loading}
			<div class="flex flex-col items-center gap-3 py-12 text-center">
				<ArrowLeftRight class="size-10 text-muted-foreground/50" />
				<div>
					<p class="font-medium">No relationship types yet</p>
					<p class="text-sm text-muted-foreground">
						Connections still work - relationship types just add labels and meaning.
					</p>
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
	title={editingId ? 'Edit relationship type' : 'New relationship type'}
	submitLabel={editingId ? 'Save' : 'Add relationship type'}
	busyLabel={editingId ? 'Saving…' : 'Adding…'}
	busy={saving}
	value={{ label, reverseLabel, description, directional, schema }}
	onSubmit={handleSubmit}
	onClose={() => (editorOpen = false)}
>
	<div class="space-y-1.5">
		<Label for="rel-label">Label</Label>
		<Input
			id="rel-label"
			bind:value={label}
			type="text"
			placeholder="e.g. Directed by, Related to"
			required
		/>
	</div>
	<div class="space-y-1.5">
		<Label for="rel-reverse">Reverse label</Label>
		<Input
			id="rel-reverse"
			bind:value={reverseLabel}
			type="text"
			placeholder="e.g. Director of (optional)"
		/>
	</div>
	<div class="space-y-1.5">
		<Label for="rel-description">Description</Label>
		<Textarea id="rel-description" bind:value={description} placeholder="Optional description" />
	</div>
	<div class="flex items-center gap-2">
		<input
			id="rel-directional"
			type="checkbox"
			bind:checked={directional}
			class="h-4 w-4 rounded border-input accent-primary"
		/>
		<div>
			<Label for="rel-directional">Directional</Label>
			<p class="text-xs text-muted-foreground">Uncheck for symmetric (A ↔ B)</p>
		</div>
	</div>
	<SchemaEditor
		bind:schema
		typeId={editingId ?? undefined}
		typeKind={editingId ? 'edge' : undefined}
		highlights
		highlightList="connection"
	/>
</TypeEditorDialog>
