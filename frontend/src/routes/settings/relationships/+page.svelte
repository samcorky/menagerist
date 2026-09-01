<script lang="ts">
	import { resolve } from '$app/paths';
	import { ArrowLeftRight, Pencil, Trash2, X } from '@lucide/svelte';
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

	let relTypes = $state<EdgeTypeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(true);

	let slug = $state('');
	let label = $state('');
	let reverseLabel = $state('');
	let description = $state('');
	let directional = $state(true);
	let submitting = $state(false);
	let createSchema = $state<Schema | null>(null);

	let editingId = $state<string | null>(null);
	let editLabel = $state('');
	let editReverseLabel = $state('');
	let editDescription = $state('');
	let editDirectional = $state(true);
	let editSchema = $state<Schema | null>(null);
	let savingId = $state<string | null>(null);
	let confirmingDeleteId = $state<string | null>(null);
	let deletingId = $state<string | null>(null);

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

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		submitting = true;
		const result = await createEdgeType({
			body: {
				slug,
				label,
				reverse_label: reverseLabel || undefined,
				description: description || undefined,
				directional,
				attributes_schema: createSchema
			}
		});
		if (result.error || !result.data) {
			toast.error("Couldn't create relationship type", { description: errorMessage(result.error) });
		} else {
			relTypes = [result.data, ...relTypes];
			slug = '';
			label = '';
			reverseLabel = '';
			description = '';
			directional = true;
			createSchema = null;
			toast.success('Relationship type created');
		}
		submitting = false;
	}

	function startEdit(et: EdgeTypeResponse) {
		editingId = et.id;
		editLabel = et.label;
		editReverseLabel = et.reverse_label ?? '';
		editDescription = et.description ?? '';
		editDirectional = et.directional;
		editSchema = (et.attributes_schema as Schema | null) ?? null;
		confirmingDeleteId = null;
	}

	function cancelEdit() {
		editingId = null;
		editSchema = null;
	}

	async function handleUpdate(event: SubmitEvent, id: string) {
		event.preventDefault();
		savingId = id;
		const result = await updateEdgeType({
			path: { edge_type_id: id },
			body: {
				label: editLabel,
				reverse_label: editReverseLabel || null,
				description: editDescription || null,
				directional: editDirectional,
				attributes_schema: editSchema
			}
		});
		if (result.error || !result.data) {
			toast.error("Couldn't save changes", { description: errorMessage(result.error) });
		} else {
			relTypes = relTypes.map((et) => (et.id === id ? result.data! : et));
			editingId = null;
			toast.success('Saved');
		}
		savingId = null;
	}

	async function handleDelete(et: EdgeTypeResponse) {
		if (confirmingDeleteId !== et.id) {
			confirmingDeleteId = et.id;
			editingId = null;
			return;
		}
		confirmingDeleteId = null;
		deletingId = et.id;
		const result = await deleteEdgeType({ path: { edge_type_id: et.id } });
		if (result.response?.status === 409) {
			toast.error("Can't delete — connections still use this type", {
				description: 'Remove those connections first, or keep this relationship type.'
			});
		} else if (result.error) {
			toast.error("Couldn't delete relationship type", { description: errorMessage(result.error) });
		} else {
			relTypes = relTypes.filter((r) => r.id !== et.id);
			toast.success('Relationship type deleted');
		}
		deletingId = null;
	}

	$effect(() => {
		void fetchPage();
	});
</script>

<svelte:head>
	<title>Relationship types — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<BackButton fallback={resolve('/settings')} />

		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Relationship types</h1>
			<p class="mt-1 text-muted-foreground">
				Define how items connect — "Directed by", "Signed by", "Part of".
			</p>
		</div>

		<Card.Root>
			<Card.Header>
				<Card.Title class="font-heading">New relationship type</Card.Title>
			</Card.Header>
			<Card.Content>
				<form class="space-y-4" onsubmit={handleSubmit}>
					<div class="space-y-1.5">
						<Label for="rel-slug">Identifier</Label>
						<Input
							id="rel-slug"
							bind:value={slug}
							type="text"
							placeholder="e.g. directed-by, related-to"
							required
						/>
					</div>
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
						<Textarea
							id="rel-description"
							bind:value={description}
							placeholder="Optional description"
						/>
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
					<SchemaEditor bind:schema={createSchema} />
					<div class="flex justify-end">
						<Button type="submit" disabled={submitting}>
							{submitting ? 'Adding…' : 'Add relationship type'}
						</Button>
					</div>
				</form>
			</Card.Content>
		</Card.Root>

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
			<div class="grid gap-3">
				{#each relTypes as et (et.id)}
					<Card.Root>
						<Card.Header class="flex flex-row items-start justify-between gap-4 space-y-0">
							<div class="min-w-0 flex-1">
								<Card.Title>{et.label}</Card.Title>
								{#if et.reverse_label}
									<p class="mt-0.5 text-sm text-muted-foreground">← {et.reverse_label}</p>
								{/if}
								{#if et.description}
									<Card.Description>{et.description}</Card.Description>
								{/if}
							</div>
							<div class="flex shrink-0 flex-wrap items-center gap-1">
								<Badge variant="secondary">{et.slug}</Badge>
								<Badge variant="outline">
									{et.directional ? 'Directional →' : 'Symmetric ↔'}
								</Badge>
								{#if confirmingDeleteId === et.id}
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
										disabled={deletingId === et.id}
										onclick={() => handleDelete(et)}
									>
										Confirm delete
									</Button>
								{:else}
									<Button
										type="button"
										variant="ghost"
										size="icon"
										onclick={() => startEdit(et)}
										aria-label="Edit relationship type"
									>
										<Pencil class="size-4" />
									</Button>
									<Button
										type="button"
										variant="ghost"
										size="icon"
										disabled={deletingId === et.id}
										onclick={() => handleDelete(et)}
										aria-label="Delete relationship type"
									>
										<Trash2 class="size-4" />
									</Button>
								{/if}
							</div>
						</Card.Header>

						{#if editingId === et.id}
							<Card.Content class="border-t pt-4">
								<form class="space-y-3" onsubmit={(e) => handleUpdate(e, et.id)}>
									<div class="space-y-1.5">
										<Label for="edit-label-{et.id}">Label</Label>
										<Input id="edit-label-{et.id}" bind:value={editLabel} required />
									</div>
									<div class="space-y-1.5">
										<Label for="edit-reverse-{et.id}">Reverse label</Label>
										<Input
											id="edit-reverse-{et.id}"
											bind:value={editReverseLabel}
											placeholder="Optional"
										/>
									</div>
									<div class="space-y-1.5">
										<Label for="edit-desc-{et.id}">Description</Label>
										<Textarea
											id="edit-desc-{et.id}"
											bind:value={editDescription}
											placeholder="Optional description"
										/>
									</div>
									<div class="flex items-center gap-2">
										<input
											id="edit-directional-{et.id}"
											type="checkbox"
											bind:checked={editDirectional}
											class="h-4 w-4 rounded border-input accent-primary"
										/>
										<Label for="edit-directional-{et.id}">Directional</Label>
									</div>
									<SchemaEditor bind:schema={editSchema} />
									<div class="flex justify-end gap-2">
										<Button type="button" variant="ghost" size="sm" onclick={cancelEdit}>
											<X class="size-4" />
											Cancel
										</Button>
										<Button type="submit" size="sm" disabled={savingId === et.id}>
											{savingId === et.id ? 'Saving…' : 'Save'}
										</Button>
									</div>
								</form>
							</Card.Content>
						{/if}
					</Card.Root>
				{/each}
			</div>

			{#if relTypes.length === 0 && !loading}
				<div class="flex flex-col items-center gap-3 py-12 text-center">
					<ArrowLeftRight class="size-10 text-muted-foreground/50" />
					<div>
						<p class="font-medium">No relationship types yet</p>
						<p class="text-sm text-muted-foreground">
							Connections still work — relationship types just add labels and meaning.
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
