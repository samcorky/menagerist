<script lang="ts">
	import { untrack } from 'svelte';
	import { listPresets } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import CatalogueDialog from '$lib/components/catalogue-dialog.svelte';
	import type { Preset, PresetKind } from '$lib/presets';
	import type { EntrySection } from '$lib/api/client';

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
	// What the server was last asked for: the box, once typing has paused.
	let appliedSearch = $state('');
	let catalogueOpen = $state(false);
	let seq = 0;

	const catalogueSections = $derived<EntrySection[]>(
		kind === 'choice_list' ? ['choice_list'] : kind === 'field_set' ? ['field_group'] : ['field']
	);

	const emptyLabel = $derived(
		kind === 'choice_list'
			? 'No saved lists yet'
			: kind === 'field_set'
				? 'No saved field groups yet'
				: 'No saved fields yet'
	);
	const searchLabel = $derived(
		kind === 'choice_list'
			? 'Search saved lists'
			: kind === 'field_set'
				? 'Search saved field groups'
				: 'Search saved fields'
	);

	// The server matches the text (label and description, ignoring case and accents), so a
	// saved field past the first hundred is found too. The rows stay while it is asked.
	async function load(text = appliedSearch) {
		const mine = ++seq;
		loading = true;
		loadError = null;
		const result = await listPresets({ query: { kind, limit: 100, q: text || undefined } });
		if (mine !== seq) return;
		loading = false;
		if (result.error || !result.data) {
			loadError = errorMessage(result.error);
			return;
		}
		presets = result.data as unknown as Preset[];
	}

	const searching = $derived(appliedSearch !== '');
	// With nothing saved there is nothing to search; a search that finds nothing keeps its box.
	const canSearch = $derived(searching || presets.length > 0);

	$effect(() => {
		if (open) {
			untrack(() => {
				search = '';
				appliedSearch = '';
			});
		}
	});

	$effect(() => {
		const text = search.trim();
		const timer = setTimeout(() => (appliedSearch = text), 250);
		return () => clearTimeout(timer);
	});

	$effect(() => {
		if (open) void load(appliedSearch);
	});

	function pick(preset: Preset) {
		onPick(preset);
		onOpenChange(false);
	}
</script>

<ResponsiveDialog.Root {open} {onOpenChange}>
	<ResponsiveDialog.Content {title} size="lg">
		<div class="mt-4 space-y-3">
			<div class="flex flex-wrap items-center gap-2">
				<Input
					bind:value={search}
					placeholder="Search…"
					aria-label={searchLabel}
					disabled={!canSearch}
					class="min-w-48 flex-1"
				/>
				{#if canSearch}
					<Button type="button" variant="ghost" size="sm" onclick={() => (catalogueOpen = true)}>
						Install from catalogue
					</Button>
				{/if}
			</div>
			{#if loading && presets.length === 0}
				<p class="py-6 text-center text-sm text-muted-foreground">Loading…</p>
			{:else if loadError}
				<div class="flex flex-col items-center gap-2 py-6 text-center">
					<p class="text-sm text-destructive">{loadError}</p>
					<Button type="button" variant="outline" size="sm" onclick={() => void load()}>
						Retry
					</Button>
				</div>
			{:else if presets.length === 0}
				<p class="py-6 text-center text-sm text-muted-foreground">
					{searching ? 'No matches' : emptyLabel}
				</p>
				{#if !searching}
					<div class="flex justify-center">
						<Button type="button" size="sm" onclick={() => (catalogueOpen = true)}>
							Install from catalogue
						</Button>
					</div>
				{/if}
			{:else}
				<ul
					class="max-h-80 space-y-1 overflow-y-auto transition-opacity {loading
						? 'opacity-60'
						: ''}"
					aria-busy={loading}
				>
					{#each presets as preset (preset.id)}
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
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

<CatalogueDialog
	open={catalogueOpen}
	onOpenChange={(value) => (catalogueOpen = value)}
	onInstalled={() => void load()}
	sections={catalogueSections}
/>
