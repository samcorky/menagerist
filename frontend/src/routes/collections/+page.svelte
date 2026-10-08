<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { Library, Plus } from '@lucide/svelte';
	import { tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { createCollection, listCollections, type CollectionResponse } from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import {
		MAX_COLLECTION_NAME_LENGTH,
		collectionSaveErrorMessage,
		describeItemCount,
		validateCollectionName
	} from '$lib/collections';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';

	const PAGE_SIZE = 50;

	let collections = $state<CollectionResponse[]>([]);
	let loading = $state(true);
	let loadFailed = $state(false);
	let hasMore = $state(false);

	let dialogOpen = $state(false);
	let name = $state('');
	let description = $state('');
	let touched = $state(false);
	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let trigger: HTMLElement | null = null;

	// §13a: don't flash a skeleton for loads under 300ms
	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading);
	});

	const nameHint = $derived(validateCollectionName(name));
	const showNameHint = $derived(touched && nameHint !== null);

	async function fetchPage(after?: string) {
		loading = true;
		if (!after) loadFailed = false;
		const result = await listCollections({ query: { after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			if (after) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
			} else {
				loadFailed = true;
			}
			hasMore = false;
		} else {
			collections = after ? [...collections, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		loading = false;
	}

	$effect(() => {
		void fetchPage();
	});

	function sentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && hasMore && !loading)
					void fetchPage(collections.at(-1)?.id);
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

	function openDialog(event: MouseEvent) {
		trigger = event.currentTarget as HTMLElement;
		name = '';
		description = '';
		touched = false;
		saveError = null;
		dialogOpen = true;
	}

	function handleOpenChange(open: boolean) {
		if (!open && saving) return;
		dialogOpen = open;
		if (!open) void tick().then(() => trigger?.focus());
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		touched = true;
		if (nameHint !== null || saving) return;
		saving = true;
		saveError = null;
		const result = await createCollection({
			body: { name: name.trim(), description: description.trim() || null }
		});
		saving = false;
		if (result.error || !result.data) {
			const status = result.response?.status;
			if (status === undefined) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
			} else {
				saveError = collectionSaveErrorMessage(status);
			}
			return;
		}
		const { id } = result.data;
		dialogOpen = false;
		void goto(resolve('/collections/[id]', { id }));
	}
</script>

<svelte:head>
	<title>Collections - Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div>
				<h1 class="font-heading text-3xl font-semibold tracking-tight">Collections</h1>
				<p class="mt-1 text-muted-foreground">Group your items into named collections.</p>
			</div>
			{#if !loadFailed && (collections.length > 0 || loading)}
				<Button onclick={openDialog}>
					<Plus class="size-4" />
					New collection
				</Button>
			{/if}
		</div>

		{#if loadingDisplay.show && collections.length === 0}
			<div class="grid gap-4 sm:grid-cols-2" aria-hidden="true">
				{#each [1, 2, 3, 4] as s (s)}
					<div class="h-28 animate-pulse rounded-xl bg-muted"></div>
				{/each}
			</div>
		{:else if loadFailed}
			<div class="flex flex-col items-start gap-3 rounded-xl border border-dashed p-5">
				<p class="text-sm text-muted-foreground">Couldn't load your collections.</p>
				<Button variant="outline" onclick={() => void fetchPage()}>Try again</Button>
			</div>
		{:else if collections.length > 0}
			<ul class="grid gap-4 sm:grid-cols-2">
				{#each collections as collection (collection.id)}
					<li>
						<a
							href={resolve('/collections/[id]', { id: collection.id })}
							class="block h-full rounded-xl focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
						>
							<Card.Root class="h-full transition-colors hover:bg-muted/50">
								<Card.Header>
									<Card.Title class="truncate">{collection.name}</Card.Title>
									{#if collection.description}
										<Card.Description class="line-clamp-2"
											>{collection.description}</Card.Description
										>
									{/if}
								</Card.Header>
								<Card.Content class="text-sm text-muted-foreground">
									{describeItemCount(collection.item_count)}
								</Card.Content>
							</Card.Root>
						</a>
					</li>
				{/each}
			</ul>
		{:else if !loading}
			<div
				class="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center"
			>
				<Library class="size-10 text-muted-foreground" aria-hidden="true" />
				<h2 class="text-lg font-medium">No collections yet</h2>
				<p class="max-w-sm text-sm text-muted-foreground">
					A collection groups items together. Make one for your vinyl, your Funkos, or films to
					watch.
				</p>
				<Button onclick={openDialog}>
					<Plus class="size-4" />
					New collection
				</Button>
			</div>
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

<ResponsiveDialog.Root open={dialogOpen} onOpenChange={handleOpenChange}>
	<ResponsiveDialog.Content title="New collection" size="md">
		<form class="mt-4 space-y-4" onsubmit={handleSubmit} novalidate>
			<div class="space-y-1.5">
				<Label for="collection-name">Name</Label>
				<Input
					id="collection-name"
					bind:value={name}
					maxlength={MAX_COLLECTION_NAME_LENGTH}
					required
					autocomplete="off"
					aria-invalid={showNameHint}
					aria-describedby={showNameHint ? 'collection-name-hint' : undefined}
					onblur={() => (touched = true)}
				/>
				{#if showNameHint}
					<p id="collection-name-hint" class="text-sm text-destructive">{nameHint}</p>
				{/if}
			</div>
			<div class="space-y-1.5">
				<Label for="collection-description">Description</Label>
				<Textarea id="collection-description" bind:value={description} placeholder="Optional" />
			</div>
			{#if saveError}
				<p role="alert" class="text-sm text-destructive">{saveError}</p>
			{/if}
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => handleOpenChange(false)}>
					Cancel
				</Button>
				<Button type="submit" disabled={saving}>
					{saving ? 'Creating…' : 'Create collection'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
