<script lang="ts">
	import { Check } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { createNodeType, listNodeTypes, type NodeTypeResponse } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { slugify } from '$lib/utils.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';

	let {
		value = $bindable(null as string | null),
		nodeTypes: externalTypes = undefined,
		onchange
	}: {
		value?: string | null;
		nodeTypes?: NodeTypeResponse[];
		onchange?: (slug: string | null) => void;
	} = $props();

	// Initialise from the parent-provided list if given; otherwise start empty and fetch.
	// Using a single local list means newly-created categories always appear immediately,
	// regardless of whether the parent provided an initial set.
	// svelte-ignore state_referenced_locally
	let allTypes = $state<NodeTypeResponse[]>(externalTypes ?? []);
	let search = $state('');
	let showNewForm = $state(false);
	let newLabel = $state('');
	let creating = $state(false);

	$effect(() => {
		if (!externalTypes) {
			listNodeTypes({ query: { limit: 200 } }).then((r) => {
				if (r.data) allTypes = r.data;
			});
		}
	});

	let filtered = $derived(
		search.trim()
			? allTypes.filter(
					(t) =>
						t.label.toLowerCase().includes(search.toLowerCase()) ||
						t.slug.includes(search.toLowerCase())
				)
			: allTypes
	);

	function select(slug: string) {
		const next = value === slug ? null : slug;
		value = next;
		onchange?.(next);
		search = '';
	}

	async function createAndSelect() {
		if (!newLabel.trim() || creating) return;
		creating = true;
		const slug = slugify(newLabel.trim());
		const result = await createNodeType({ body: { slug, label: newLabel.trim() } });
		if (result.error || !result.data) {
			toast.error("Couldn't create category", { description: errorMessage(result.error) });
			creating = false;
			return;
		}
		allTypes = [...allTypes, result.data];
		select(slug);
		showNewForm = false;
		newLabel = '';
		creating = false;
	}
</script>

<div class="space-y-2">
	<Input bind:value={search} placeholder="Search categories…" />

	{#if filtered.length > 0}
		<div class="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto">
			{#each filtered as nt (nt.slug)}
				<button
					type="button"
					onclick={() => select(nt.slug)}
					class="flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs transition-colors {value ===
					nt.slug
						? 'border-primary bg-primary text-primary-foreground'
						: 'border-border bg-background hover:border-primary/50'}"
				>
					{#if value === nt.slug}<Check class="size-3" />{/if}
					{nt.label}
				</button>
			{/each}
		</div>
	{:else if search && !showNewForm}
		<p class="text-xs text-muted-foreground">No matching categories</p>
	{/if}

	{#if !showNewForm}
		<button
			type="button"
			onclick={() => (showNewForm = true)}
			class="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
		>
			+ New category
		</button>
	{:else}
		<form
			class="flex gap-2"
			onsubmit={(e) => {
				e.preventDefault();
				void createAndSelect();
			}}
		>
			<Input
				bind:value={newLabel}
				placeholder="Category label…"
				class="h-7 flex-1 text-xs"
				autofocus
			/>
			<Button type="submit" size="sm" disabled={!newLabel.trim() || creating}>
				{creating ? '…' : 'Create'}
			</Button>
			<Button
				type="button"
				size="sm"
				variant="ghost"
				onclick={() => {
					showNewForm = false;
					newLabel = '';
				}}
			>
				Cancel
			</Button>
		</form>
	{/if}
</div>
