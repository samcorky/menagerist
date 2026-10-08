<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { Check } from '@lucide/svelte';
	import { tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		installExamplePack,
		listExamplePacks,
		uninstallExamplePack,
		type ExamplePackResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import {
		describeCounts,
		describeRemoval,
		groupKept,
		invalidateExampleIds,
		reasonLabel
	} from '$lib/examples';
	import BackButton from '$lib/components/back-button.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	let packs = $state<ExamplePackResponse[]>([]);
	let loading = $state(true);
	let loadFailed = $state(false);
	let busyId = $state<string | null>(null);
	let confirmPack = $state<ExamplePackResponse | null>(null);
	let keptNotes = $state<Record<string, { reason: string; count: number }[]>>({});
	let buttons: Record<string, HTMLElement | null> = {};

	// §13a: don't flash a skeleton for loads under 300ms
	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading);
	});

	const isInstalled = (pack: ExamplePackResponse) => pack.installation?.status === 'installed';

	async function load() {
		loading = true;
		loadFailed = false;
		const result = await listExamplePacks();
		if (result.error || !result.data) {
			loadFailed = true;
		} else {
			packs = result.data;
		}
		loading = false;
	}

	$effect(() => {
		void load();
	});

	async function install(pack: ExamplePackResponse) {
		busyId = pack.id;
		keptNotes = {};
		const result = await installExamplePack({ path: { pack_id: pack.id } });
		if (result.error || !result.data) {
			if (result.response?.status === 409) {
				toast.error("Couldn't add these examples", { description: errorMessage(result.error) });
			} else {
				const { title, description } = networkAwareError(result);
				toast.error(title, {
					description,
					action: { label: 'Try again', onClick: () => void install(pack) }
				});
			}
		} else {
			invalidateExampleIds();
			const refreshed = await listExamplePacks();
			if (refreshed.data) packs = refreshed.data;
			toast.success('Examples added', {
				action: { label: 'View items', onClick: () => void goto(resolve('/items')) }
			});
		}
		busyId = null;
	}

	async function remove() {
		const pack = confirmPack;
		if (!pack) return;
		busyId = pack.id;
		keptNotes = {};
		const result = await uninstallExamplePack({ path: { pack_id: pack.id } });
		busyId = null;
		if (result.error || !result.data) {
			const { title, description } = networkAwareError(result);
			toast.error(title, { description });
			return;
		}
		confirmPack = null;
		invalidateExampleIds();
		toast.success(describeRemoval(result.data));
		const refreshed = await listExamplePacks();
		if (refreshed.data) packs = refreshed.data;
		if (result.data.kept.length > 0) keptNotes = { [pack.id]: groupKept(result.data.kept) };
		await tick();
		buttons[pack.id]?.focus();
	}

	function closeConfirm(open: boolean) {
		if (open || busyId) return;
		const id = confirmPack?.id;
		confirmPack = null;
		if (id) void tick().then(() => buttons[id]?.focus());
	}
</script>

<svelte:head>
	<title>Examples - Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-2xl flex-col gap-8">
		<div>
			<BackButton fallback={resolve('/settings')} />
			<h1 class="mt-2 font-heading text-3xl font-semibold tracking-tight">Examples</h1>
			<p class="mt-1 text-muted-foreground">
				Try Menagerist with some ready-made items. Remove them whenever you like.
			</p>
		</div>

		{#if loadingDisplay.show}
			<div class="grid gap-4">
				{#each [1, 2] as s (s)}
					<div class="h-32 animate-pulse rounded-xl bg-muted"></div>
				{/each}
			</div>
		{:else if !loading && loadFailed}
			<div class="flex flex-col items-start gap-3 rounded-xl border border-dashed p-5">
				<p class="text-sm text-muted-foreground">Couldn't load the examples.</p>
				<Button variant="outline" onclick={() => void load()}>Try again</Button>
			</div>
		{:else if !loading && packs.length === 0}
			<p class="text-sm text-muted-foreground">There are no examples available right now.</p>
		{:else if !loading}
			<div class="grid gap-4">
				{#each packs as pack (pack.id)}
					{@const installed = isInstalled(pack)}
					{@const busy = busyId === pack.id}
					<Card.Root>
						<Card.Header>
							<Card.Title>{pack.name}</Card.Title>
							<Card.Description>{pack.description}</Card.Description>
						</Card.Header>
						<Card.Content class="text-sm text-muted-foreground">
							{describeCounts(pack.counts)}
							{#if keptNotes[pack.id]}
								<ul class="mt-3 list-disc space-y-1 pl-5">
									{#each keptNotes[pack.id] as note (note.reason)}
										<li>
											{note.count}
											{note.count === 1 ? 'item was' : 'items were'} kept because {reasonLabel(
												note.reason
											)}.
										</li>
									{/each}
								</ul>
							{/if}
						</Card.Content>
						<Card.Footer class="flex items-center gap-3">
							{#if installed}
								<span class="flex items-center gap-1 text-sm text-muted-foreground">
									<Check class="size-4" />
									Added
								</span>
								<Button
									variant="outline"
									disabled={busy}
									class="min-h-11"
									aria-label="Remove {pack.name}"
									bind:ref={() => buttons[pack.id] ?? null, (el) => (buttons[pack.id] = el)}
									onclick={() => (confirmPack = pack)}
								>
									Remove
								</Button>
							{:else}
								<Button
									disabled={busy}
									class="min-h-11"
									aria-label="Add {pack.name}"
									bind:ref={() => buttons[pack.id] ?? null, (el) => (buttons[pack.id] = el)}
									onclick={() => void install(pack)}
								>
									{#if busy}
										<Spinner class="size-4" />
										Adding...
									{:else}
										Add examples
									{/if}
								</Button>
							{/if}
						</Card.Footer>
					</Card.Root>
				{/each}
			</div>
		{/if}
	</div>
</main>

<ConfirmDialog
	open={confirmPack !== null}
	title="Remove these examples?"
	description={confirmPack?.installation
		? `This removes ${describeCounts(confirmPack.installation.counts)}. Anything you've changed or connected to your own items will be kept.`
		: undefined}
	busy={busyId !== null}
	busyLabel="Removing..."
	confirmLabel="Remove"
	onOpenChange={closeConfirm}
	onConfirm={() => void remove()}
/>
