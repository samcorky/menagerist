<script lang="ts">
	import { listPresets } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Eye, EyeOff } from '@lucide/svelte';
	import { readShowBuiltins, visiblePresets, writeShowBuiltins } from '$lib/preset-packs';
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
	let showBuiltins = $state(readShowBuiltins());

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

	const visible = $derived(visiblePresets(presets, showBuiltins));
	const filtered = $derived(
		search.trim() === ''
			? visible
			: visible.filter((p) => p.label.toLowerCase().includes(search.trim().toLowerCase()))
	);

	function setShowBuiltins(show: boolean) {
		showBuiltins = show;
		writeShowBuiltins(show);
	}

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
					disabled={loading || presets.length === 0}
					class="min-w-48 flex-1"
				/>
				<Button
					type="button"
					size="sm"
					variant={showBuiltins ? 'default' : 'outline'}
					aria-pressed={showBuiltins}
					title={showBuiltins
						? 'Click to hide built-in fields, lists and groups'
						: 'Click to show built-in fields, lists and groups'}
					class="shrink-0"
					onclick={() => setShowBuiltins(!showBuiltins)}
				>
					{#if showBuiltins}
						<Eye class="size-4" />
						Built-in shown
					{:else}
						<EyeOff class="size-4" />
						Built-in hidden
					{/if}
				</Button>
			</div>
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
					{presets.length === 0
						? emptyLabel
						: visible.length === 0
							? 'Built-in items are hidden'
							: 'No matches'}
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
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
