<script lang="ts">
	import { resolve } from '$app/paths';
	import { Bookmark, ListChecks, Layers, Trash2 } from '@lucide/svelte';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { toast } from 'svelte-sonner';
	import { listPresets, deletePreset, type PresetResponse } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import BackButton from '$lib/components/back-button.svelte';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3];

	let fields = $state<PresetResponse[]>([]);
	let fieldsLoading = $state(false);
	let fieldsHasMore = $state(true);

	let lists = $state<PresetResponse[]>([]);
	let listsLoading = $state(false);
	let listsHasMore = $state(true);

	async function fetchFields(after?: string) {
		fieldsLoading = true;
		const result = await listPresets({ query: { kind: 'field', after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load saved fields", { description: errorMessage(result.error) });
		} else {
			fields = after ? [...fields, ...result.data] : result.data;
			fieldsHasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		fieldsLoading = false;
	}

	async function fetchLists(after?: string) {
		listsLoading = true;
		const result = await listPresets({ query: { kind: 'choice_list', after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load saved lists", { description: errorMessage(result.error) });
		} else {
			lists = after ? [...lists, ...result.data] : result.data;
			listsHasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		listsLoading = false;
	}

	function fieldsSentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && fieldsHasMore && !fieldsLoading)
					void fetchFields(fields.at(-1)?.id);
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

	function listsSentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && listsHasMore && !listsLoading)
					void fetchLists(lists.at(-1)?.id);
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

	function handleDelete(preset: PresetResponse, collection: 'fields' | 'lists') {
		const setItems =
			collection === 'fields'
				? (v: PresetResponse[]) => (fields = v)
				: (v: PresetResponse[]) => (lists = v);
		const current = collection === 'fields' ? fields : lists;

		// No items ever depend on a preset the way categories depend on connections — always
		// use the optimistic undo path.
		setItems(current.filter((p) => p.id !== preset.id));

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deletePreset({ path: { preset_id: preset.id } });
			if (result.error) {
				const restored = collection === 'fields' ? fields : lists;
				setItems([preset, ...restored]);
				toast.error("Couldn't delete", { description: errorMessage(result.error) });
			}
		}, 5000);

		toast(collection === 'fields' ? 'Field deleted' : 'List deleted', {
			action: {
				label: 'Undo',
				onClick: () => {
					undone = true;
					clearTimeout(timerId);
					const restored = collection === 'fields' ? fields : lists;
					setItems([preset, ...restored]);
				}
			},
			duration: 5000
		});
	}

	function listOptionCount(preset: PresetResponse): number | undefined {
		const options = (preset.definition as { options?: unknown }).options;
		return Array.isArray(options) ? options.length : undefined;
	}

	$effect(() => {
		void fetchFields();
	});

	$effect(() => {
		void fetchLists();
	});
</script>

<svelte:head>
	<title>Saved fields — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-6 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-8">
		<BackButton fallback={resolve('/settings')} />

		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Saved fields</h1>
			<p class="mt-1 text-muted-foreground">
				Reuse a field or a list of choices across item types instead of rebuilding it each time.
			</p>
		</div>

		<div class="flex flex-col gap-3">
			<h2 class="font-heading text-lg font-semibold">Fields</h2>

			{#if fieldsLoading && fields.length === 0}
				<Shimmer loading={true}>
					<div class="grid gap-3">
						{#each loadingSkeletons as s (s)}
							<div class="rounded-lg border p-4">
								<div class="space-y-1">
									<div class="h-5 w-48 rounded bg-muted"></div>
									<div class="h-4 w-32 rounded-full bg-muted"></div>
								</div>
							</div>
						{/each}
					</div>
				</Shimmer>
			{:else}
				<div class="grid gap-3">
					{#each fields as preset (preset.id)}
						<Card.Root>
							<Card.Header
								class="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4"
							>
								<div class="min-w-0 flex-1">
									<Card.Title>{preset.label}</Card.Title>
									{#if preset.description}
										<Card.Description>{preset.description}</Card.Description>
									{/if}
								</div>
								<div class="flex flex-wrap items-center gap-1 sm:shrink-0">
									<Button
										type="button"
										variant="ghost"
										size="icon"
										disabled={preset.builtin}
										title={preset.builtin ? "Built-in fields can't be deleted" : undefined}
										onclick={() => handleDelete(preset, 'fields')}
										aria-label="Delete field"
									>
										<Trash2 class="size-4" />
									</Button>
								</div>
							</Card.Header>
						</Card.Root>
					{/each}
				</div>

				{#if fields.length === 0 && !fieldsLoading}
					<div class="flex flex-col items-center gap-3 py-10 text-center">
						<Bookmark class="size-10 text-muted-foreground/50" />
						<p class="font-medium">No saved fields yet</p>
					</div>
				{/if}
			{/if}

			{#if fieldsHasMore}
				<div use:fieldsSentinel class="flex justify-center py-2" aria-hidden="true">
					{#if fieldsLoading}
						<div
							class="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground"
						></div>
					{/if}
				</div>
			{/if}
		</div>

		<div class="flex flex-col gap-3">
			<h2 class="font-heading text-lg font-semibold">Lists</h2>

			{#if listsLoading && lists.length === 0}
				<Shimmer loading={true}>
					<div class="grid gap-3">
						{#each loadingSkeletons as s (s)}
							<div class="rounded-lg border p-4">
								<div class="space-y-1">
									<div class="h-5 w-48 rounded bg-muted"></div>
									<div class="h-4 w-32 rounded-full bg-muted"></div>
								</div>
							</div>
						{/each}
					</div>
				</Shimmer>
			{:else}
				<div class="grid gap-3">
					{#each lists as preset (preset.id)}
						{@const optionCount = listOptionCount(preset)}
						<Card.Root>
							<Card.Header
								class="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4"
							>
								<div class="min-w-0 flex-1">
									<Card.Title>{preset.label}</Card.Title>
									{#if preset.description}
										<Card.Description>{preset.description}</Card.Description>
									{/if}
									{#if optionCount !== undefined}
										<p class="mt-0.5 text-xs text-muted-foreground">
											{optionCount}
											{optionCount === 1 ? 'option' : 'options'}
										</p>
									{/if}
								</div>
								<div class="flex flex-wrap items-center gap-1 sm:shrink-0">
									<Button
										type="button"
										variant="ghost"
										size="icon"
										disabled={preset.builtin}
										title={preset.builtin ? "Built-in fields can't be deleted" : undefined}
										onclick={() => handleDelete(preset, 'lists')}
										aria-label="Delete list"
									>
										<Trash2 class="size-4" />
									</Button>
								</div>
							</Card.Header>
						</Card.Root>
					{/each}
				</div>

				{#if lists.length === 0 && !listsLoading}
					<div class="flex flex-col items-center gap-3 py-10 text-center">
						<ListChecks class="size-10 text-muted-foreground/50" />
						<p class="font-medium">No saved lists yet</p>
					</div>
				{/if}
			{/if}

			{#if listsHasMore}
				<div use:listsSentinel class="flex justify-center py-2" aria-hidden="true">
					{#if listsLoading}
						<div
							class="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground"
						></div>
					{/if}
				</div>
			{/if}
		</div>

		<div class="flex flex-col gap-3">
			<h2 class="font-heading text-lg font-semibold">Field groups</h2>
			<Card.Root>
				<Card.Content class="flex items-center gap-3 py-6 text-muted-foreground">
					<Layers class="size-5 shrink-0" />
					<p class="text-sm">Field groups aren't available yet.</p>
				</Card.Content>
			</Card.Root>
		</div>
	</div>
</main>
