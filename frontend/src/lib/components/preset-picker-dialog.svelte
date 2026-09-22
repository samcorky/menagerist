<script lang="ts">
	import { Dialog } from 'bits-ui';
	import { X } from '@lucide/svelte';
	import { listPresets } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import type { Preset, PresetKind } from '$lib/presets';

	let {
		open,
		kind,
		title,
		onOpenChange,
		onPick
	}: {
		open: boolean;
		kind: PresetKind;
		title: string;
		onOpenChange: (open: boolean) => void;
		onPick: (preset: Preset) => void;
	} = $props();

	let presets = $state<Preset[]>([]);
	let loading = $state(false);
	let loadError = $state<string | null>(null);
	let search = $state('');

	const emptyLabel = $derived(
		kind === 'choice_list' ? 'No saved lists yet' : 'No saved fields yet'
	);
	const searchLabel = $derived(
		kind === 'choice_list' ? 'Search saved lists' : 'Search saved fields'
	);

	async function load() {
		loading = true;
		loadError = null;
		const result = await listPresets({ query: { kind, limit: 100 } });
		loading = false;
		if (result.error || !result.data) {
			loadError = errorMessage(result.error);
			return;
		}
		presets = result.data as unknown as Preset[];
	}

	$effect(() => {
		if (open) {
			search = '';
			void load();
		}
	});

	const filtered = $derived(
		search.trim() === ''
			? presets
			: presets.filter((p) => p.label.toLowerCase().includes(search.trim().toLowerCase()))
	);

	function pick(preset: Preset) {
		onPick(preset);
		onOpenChange(false);
	}
</script>

<Dialog.Root {open} {onOpenChange}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
		<Dialog.Content
			aria-label={title}
			class="fixed right-0 bottom-0 left-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-2xl border-t bg-background p-6 shadow-xl sm:inset-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-full sm:max-w-lg sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border"
		>
			<div class="mx-auto mb-5 h-1.5 w-12 rounded-full bg-muted sm:hidden"></div>
			<div class="flex items-center justify-between">
				<Dialog.Title class="text-lg font-semibold">{title}</Dialog.Title>
				<button
					type="button"
					onclick={() => onOpenChange(false)}
					class="rounded-md p-1 text-muted-foreground hover:text-foreground"
					aria-label="Close"
				>
					<X class="size-4" />
				</button>
			</div>
			<div class="mt-4 space-y-3">
				<Input
					bind:value={search}
					placeholder="Search…"
					aria-label={searchLabel}
					disabled={loading || presets.length === 0}
				/>
				{#if loading}
					<p class="py-6 text-center text-sm text-muted-foreground">Loading…</p>
				{:else if loadError}
					<div class="flex flex-col items-center gap-2 py-6 text-center">
						<p class="text-sm text-destructive">{loadError}</p>
						<Button type="button" variant="outline" size="sm" onclick={() => void load()}>
							Retry
						</Button>
					</div>
				{:else if filtered.length === 0}
					<p class="py-6 text-center text-sm text-muted-foreground">
						{presets.length === 0 ? emptyLabel : 'No matches'}
					</p>
				{:else}
					<ul class="max-h-80 space-y-1 overflow-y-auto">
						{#each filtered as preset (preset.id)}
							<li class="flex items-center gap-2 rounded-md border border-input p-2">
								<div class="min-w-0 flex-1">
									<p class="truncate text-sm font-medium">{preset.label}</p>
									{#if preset.description}
										<p class="truncate text-xs text-muted-foreground">{preset.description}</p>
									{/if}
								</div>
								<Button type="button" variant="outline" size="sm" onclick={() => pick(preset)}>
									Add
								</Button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
