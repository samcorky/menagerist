<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { ImagePlus, X } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import {
		attachMedia,
		createNode,
		listNodeTypes,
		uploadAndAttachMedia,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import { captureController, type StagedPhoto } from '$lib/capture.svelte.js';
	import AttributesEditor, {
		rowsToAttributes,
		type AttributeRow
	} from '$lib/components/attributes-editor.svelte';
	import type { AttributesSchema } from '$lib/schema-types';
	import BackButton from '$lib/components/back-button.svelte';
	import CategorySelect from '$lib/components/category-select.svelte';
	import TagsInput from '$lib/components/tags-input.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';

	let name = $state('');
	let description = $state('');
	let selectedType = $state<string | null>(null);
	let tags = $state<string[]>([]);
	let attrRows = $state<AttributeRow[]>([]);
	let attrServerErrors = $state<Record<string, string> | null>(null);
	let saving = $state(false);
	let photo = $state<File | null>(null);
	let photoPreview = $state<string | null>(null);
	let stagedAsset = $state<StagedPhoto | null>(null);
	let nodeTypes = $state<NodeTypeResponse[]>([]);

	let nodeSchema = $derived(
		(nodeTypes.find((nt) => nt.slug === selectedType)
			?.attributes_schema as AttributesSchema | null) ?? null
	);

	$effect(() => {
		listNodeTypes({ query: { limit: 200 } }).then((r) => {
			if (r.data) nodeTypes = r.data;
		});
		return () => {
			if (photoPreview) URL.revokeObjectURL(photoPreview);
		};
	});

	onMount(() => {
		const pending = captureController.consumePendingHandoff();
		if (pending) {
			name = pending.name;
			selectedType = pending.selectedType;
			if (pending.stagedPhoto) {
				stagedAsset = pending.stagedPhoto;
				photoPreview = pending.stagedPhoto.previewUrl;
			}
		}
	});

	function handlePhotoChange(e: Event) {
		const file = (e.target as HTMLInputElement).files?.[0] ?? null;
		if (photoPreview) URL.revokeObjectURL(photoPreview);
		stagedAsset = null;
		photo = file;
		photoPreview = file ? URL.createObjectURL(file) : null;
	}

	function clearPhoto() {
		if (photoPreview) URL.revokeObjectURL(photoPreview);
		photo = null;
		photoPreview = null;
		stagedAsset = null;
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!name.trim() || saving) return;
		saving = true;
		const result = await createNode({
			body: {
				name: name.trim(),
				type: selectedType || null,
				description: description || null,
				tags,
				attributes: rowsToAttributes(attrRows, nodeSchema)
			}
		});
		if (result.error || !result.data) {
			const fieldErrors =
				(result.error as { errors?: Array<{ path?: string; message?: string }> } | null)?.errors ??
				[];
			const placed = fieldErrors.filter((e) => e.path && e.path !== '/');
			if (placed.length) {
				attrServerErrors = Object.fromEntries(
					placed.map((e) => [e.path!.replace(/^\//, ''), e.message ?? 'Invalid value'])
				);
			}
			const { title, description: desc } = networkAwareError(result);
			toast.error(title, { description: desc });
			saving = false;
			return;
		}
		if (stagedAsset) {
			await attachMedia({
				path: { asset_id: stagedAsset.id },
				body: { target_type: 'node', target_id: result.data.id, attribute_key: 'cover' }
			});
		} else if (photo) {
			await uploadAndAttachMedia({
				body: {
					file: photo,
					target_type: 'node',
					target_id: result.data.id,
					attribute_key: 'cover'
				}
			});
		}
		await goto(resolve('/collection/[id]', { id: result.data.id }));
	}
</script>

<svelte:head>
	<title>New item — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-2xl flex-col gap-6">
		<BackButton fallback={resolve('/collection')} />

		<Card.Root>
			<Card.Header>
				<Card.Title class="font-heading text-xl">New item</Card.Title>
			</Card.Header>
			<Card.Content>
				<form class="space-y-4" onsubmit={handleSubmit}>
					<!-- Photo -->
					{#if photoPreview}
						<div class="relative">
							<img
								src={photoPreview}
								alt="Cover photo preview"
								class="max-h-48 w-full rounded-lg object-cover"
							/>
							<button
								type="button"
								onclick={clearPhoto}
								aria-label="Remove photo"
								class="absolute top-2 right-2 rounded-full bg-black/50 p-1 text-white hover:bg-black/70"
							>
								<X class="size-3" />
							</button>
						</div>
					{:else}
						<label
							class="flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border px-4 py-6 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
						>
							<ImagePlus class="size-4" />
							Add cover photo
							<input type="file" accept="image/*" class="sr-only" onchange={handlePhotoChange} />
						</label>
					{/if}

					<!-- Name -->
					<div class="space-y-2">
						<Label for="name">Name</Label>
						<Input id="name" bind:value={name} required autofocus />
					</div>

					<!-- Category -->
					<div class="space-y-2">
						<Label>Category</Label>
						<CategorySelect bind:value={selectedType} />
					</div>

					<!-- Description -->
					<div class="space-y-2">
						<Label for="description">Description</Label>
						<Textarea id="description" bind:value={description} />
					</div>

					<TagsInput bind:tags />

					<!-- Attributes (schema-aware when category selected) -->
					<AttributesEditor
						bind:rows={attrRows}
						schema={nodeSchema}
						serverErrors={attrServerErrors}
					/>

					<div class="flex justify-end">
						<Button type="submit" disabled={!name.trim() || saving}>
							{saving ? 'Saving…' : 'Save'}
						</Button>
					</div>
				</form>
			</Card.Content>
		</Card.Root>
	</div>
</main>
