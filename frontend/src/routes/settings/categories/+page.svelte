<script lang="ts">
	import { resolve } from '$app/paths';
	import { Tag, Pencil, Trash2, X } from '@lucide/svelte';
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
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import BackButton from '$lib/components/back-button.svelte';
	import SchemaEditor, { type Schema } from '$lib/components/schema-editor.svelte';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3];

	let categories = $state<NodeTypeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(true);

	let label = $state('');
	let description = $state('');
	let submitting = $state(false);
	let createSchema = $state<Schema | null>(null);

	let editingId = $state<string | null>(null);
	let editLabel = $state('');
	let editDescription = $state('');
	let editSchema = $state<Schema | null>(null);
	let savingId = $state<string | null>(null);
	let confirmingDeleteId = $state<string | null>(null);
	let deletingId = $state<string | null>(null);

	async function fetchPage(after?: string) {
		loading = true;
		const result = await listNodeTypes({ query: { after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load categories", { description: errorMessage(result.error) });
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

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		submitting = true;
		const result = await createNodeType({
			body: {
				slug: slugify(label),
				label,
				description: description || undefined,
				attributes_schema: createSchema
			}
		});
		if (result.error || !result.data) {
			toast.error("Couldn't create category", { description: errorMessage(result.error) });
		} else {
			categories = [result.data, ...categories];
			label = '';
			description = '';
			createSchema = null;
			toast.success('Category created');
		}
		submitting = false;
	}

	function startEdit(cat: NodeTypeResponse) {
		editingId = cat.id;
		editLabel = cat.label;
		editDescription = cat.description ?? '';
		editSchema = (cat.attributes_schema as Schema | null) ?? null;
		confirmingDeleteId = null;
	}

	function cancelEdit() {
		editingId = null;
		editSchema = null;
	}

	async function handleUpdate(event: SubmitEvent, id: string) {
		event.preventDefault();
		savingId = id;
		const result = await updateNodeType({
			path: { node_type_id: id },
			body: {
				label: editLabel,
				description: editDescription || null,
				attributes_schema: editSchema
			}
		});
		if (result.error || !result.data) {
			toast.error("Couldn't save changes", { description: errorMessage(result.error) });
		} else {
			categories = categories.map((c) => (c.id === id ? result.data! : c));
			editingId = null;
			toast.success('Category updated');
		}
		savingId = null;
	}

	async function handleDelete(cat: NodeTypeResponse) {
		const inUse = await listNodes({ query: { type: cat.slug, limit: 1 } });
		const hasItems = (inUse.data?.length ?? 0) > 0;

		if (hasItems) {
			// Destructive — items will lose their category. Require explicit confirmation.
			if (confirmingDeleteId !== cat.id) {
				confirmingDeleteId = cat.id;
				editingId = null;
				return;
			}
			confirmingDeleteId = null;
			deletingId = cat.id;
			const result = await deleteNodeType({ path: { node_type_id: cat.id } });
			if (result.error) {
				toast.error("Couldn't delete category", { description: errorMessage(result.error) });
			} else {
				categories = categories.filter((c) => c.id !== cat.id);
				toast.success('Category deleted');
			}
			deletingId = null;
			return;
		}

		// No items — optimistic removal with undo window
		editingId = null;
		confirmingDeleteId = null;
		categories = categories.filter((c) => c.id !== cat.id);

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deleteNodeType({ path: { node_type_id: cat.id } });
			if (result.error) {
				categories = [cat, ...categories];
				toast.error("Couldn't delete category", { description: errorMessage(result.error) });
			}
		}, 5000);

		toast('Category deleted', {
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

	$effect(() => {
		void fetchPage();
	});
</script>

<svelte:head>
	<title>Categories — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<BackButton fallback={resolve('/settings')} />

		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Categories</h1>
			<p class="mt-1 text-muted-foreground">
				Organise your collection with types like "Film", "Person", or "Event".
			</p>
		</div>

		<Card.Root>
			<Card.Header>
				<Card.Title class="font-heading">New category</Card.Title>
			</Card.Header>
			<Card.Content>
				<form class="space-y-4" onsubmit={handleSubmit}>
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
						<Textarea
							id="cat-description"
							bind:value={description}
							placeholder="Optional description"
						/>
					</div>
					<SchemaEditor bind:schema={createSchema} />
					<div class="flex justify-end">
						<Button type="submit" disabled={submitting}>
							{submitting ? 'Adding…' : 'Add category'}
						</Button>
					</div>
				</form>
			</Card.Content>
		</Card.Root>

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
			<div class="grid gap-3">
				{#each categories as cat (cat.id)}
					<Card.Root>
						<Card.Header class="flex flex-row items-start justify-between gap-4 space-y-0">
							<div class="min-w-0 flex-1">
								<Card.Title>{cat.label}</Card.Title>
								{#if cat.description}
									<Card.Description>{cat.description}</Card.Description>
								{/if}
							</div>
							<div class="flex shrink-0 items-center gap-1">
								<Badge variant="secondary">{cat.slug}</Badge>
								{#if confirmingDeleteId === cat.id}
									<span class="text-xs text-destructive">Items will lose this category</span>
									<Button
										type="button"
										variant="ghost"
										size="sm"
										onclick={() => (confirmingDeleteId = null)}
									>
										Cancel
									</Button>
									<Button
										type="button"
										variant="destructive"
										size="sm"
										disabled={deletingId === cat.id}
										onclick={() => handleDelete(cat)}
									>
										Delete anyway
									</Button>
								{:else}
									<Button
										type="button"
										variant="ghost"
										size="icon"
										onclick={() => startEdit(cat)}
										aria-label="Edit category"
									>
										<Pencil class="size-4" />
									</Button>
									<Button
										type="button"
										variant="ghost"
										size="icon"
										disabled={deletingId === cat.id}
										onclick={() => handleDelete(cat)}
										aria-label="Delete category"
									>
										<Trash2 class="size-4" />
									</Button>
								{/if}
							</div>
						</Card.Header>

						{#if editingId === cat.id}
							<Card.Content class="border-t pt-4">
								<form class="space-y-3" onsubmit={(e) => handleUpdate(e, cat.id)}>
									<div class="space-y-1.5">
										<Label for="edit-label-{cat.id}">Label</Label>
										<Input id="edit-label-{cat.id}" bind:value={editLabel} required />
									</div>
									<div class="space-y-1.5">
										<Label for="edit-desc-{cat.id}">Description</Label>
										<Textarea
											id="edit-desc-{cat.id}"
											bind:value={editDescription}
											placeholder="Optional description"
										/>
									</div>
									<SchemaEditor bind:schema={editSchema} />
									<div class="flex justify-end gap-2">
										<Button type="button" variant="ghost" size="sm" onclick={cancelEdit}>
											<X class="size-4" />
											Cancel
										</Button>
										<Button type="submit" size="sm" disabled={savingId === cat.id}>
											{savingId === cat.id ? 'Saving…' : 'Save'}
										</Button>
									</div>
								</form>
							</Card.Content>
						{/if}
					</Card.Root>
				{/each}
			</div>

			{#if categories.length === 0 && !loading}
				<div class="flex flex-col items-center gap-3 py-12 text-center">
					<Tag class="size-10 text-muted-foreground/50" />
					<div>
						<p class="font-medium">No categories yet</p>
						<p class="text-sm text-muted-foreground">
							Create one to start organising your collection.
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
	</div>
</main>
