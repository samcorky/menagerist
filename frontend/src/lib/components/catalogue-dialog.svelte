<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { listCatalogueEntries, installCatalogueEntry, type EntrySection } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { describeInstall, entryNote, groupBySection, type CatalogueEntry } from '$lib/catalogue';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';

	let {
		open,
		onOpenChange,
		onInstalled,
		sections
	}: {
		open: boolean;
		onOpenChange: (open: boolean) => void;
		onInstalled: () => void;
		/** Limit what is offered; omitted means every section. */
		sections?: EntrySection[];
	} = $props();

	const MAX_CONTENTS = 6;

	let entries = $state<CatalogueEntry[]>([]);
	let loading = $state(false);
	let loadError = $state<string | null>(null);
	let installError = $state<string | null>(null);
	let busyId = $state<string | null>(null);

	const groups = $derived(
		groupBySection(entries.filter((e) => !sections || sections.includes(e.section)))
	);

	async function load() {
		loading = true;
		loadError = null;
		const result = await listCatalogueEntries();
		loading = false;
		if (result.error || !result.data) {
			loadError = errorMessage(result.error);
			return;
		}
		entries = result.data;
	}

	$effect(() => {
		if (open) {
			installError = null;
			void load();
		}
	});

	async function install(entry: CatalogueEntry) {
		busyId = entry.id;
		installError = null;
		const result = await installCatalogueEntry({ path: { entry_id: entry.id } });
		busyId = null;
		if (result.error || !result.data) {
			installError = errorMessage(result.error);
			return;
		}
		toast.success(entry.title, { description: describeInstall(result.data) });
		onInstalled();
		await load();
	}

	function contentsLine(entry: CatalogueEntry): string {
		const shown = entry.contents.slice(0, MAX_CONTENTS).join(', ');
		const more = entry.contents.length - MAX_CONTENTS;
		return more > 0 ? `${shown} and ${more} more` : shown;
	}
</script>

<ResponsiveDialog.Root {open} {onOpenChange}>
	<ResponsiveDialog.Content title="Install from catalogue" size="lg">
		<div class="mt-4 space-y-4">
			<p class="text-sm text-muted-foreground">
				Add ready-made saved fields and starter types. What you add is yours to edit or delete.
			</p>
			{#if installError}
				<p class="text-sm text-destructive" role="alert">{installError}</p>
			{/if}
			{#if loading && entries.length === 0}
				<p class="py-6 text-center text-sm text-muted-foreground">Loading…</p>
			{:else if loadError}
				<div class="flex flex-col items-center gap-2 py-6 text-center">
					<p class="text-sm text-destructive">{loadError}</p>
					<Button type="button" variant="outline" size="sm" onclick={() => void load()}>
						Retry
					</Button>
				</div>
			{:else}
				<div class="max-h-96 space-y-4 overflow-y-auto">
					{#each groups as group (group.section)}
						<section class="space-y-1">
							<h3 class="text-sm font-medium">{group.label}</h3>
							<ul class="space-y-1">
								{#each group.entries as entry (entry.id)}
									{@const note = entryNote(entry)}
									<li class="flex items-center gap-2 rounded-md border border-input p-2">
										<div class="min-w-0 flex-1">
											<p class="truncate text-sm font-medium">{entry.title}</p>
											<p class="text-xs text-muted-foreground">{entry.description}</p>
											{#if entry.contents.length > 1}
												<p class="truncate text-xs text-muted-foreground">{contentsLine(entry)}</p>
											{/if}
										</div>
										{#if entry.installed}
											<span class="text-xs text-muted-foreground">{note}</span>
										{:else}
											{#if note}
												<span class="text-xs text-muted-foreground">{note}</span>
											{/if}
											<Button
												type="button"
												variant="outline"
												size="sm"
												class="pointer-coarse:min-h-11"
												disabled={busyId !== null}
												aria-label="Install {entry.title}"
												onclick={() => install(entry)}
											>
												{busyId === entry.id ? 'Adding…' : 'Add'}
											</Button>
										{/if}
									</li>
								{/each}
							</ul>
						</section>
					{/each}
				</div>
			{/if}
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
