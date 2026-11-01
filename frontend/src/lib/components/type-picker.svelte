<script lang="ts">
	import { Ban, Plus } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { countNodeTypes, createNodeType, type NodeTypeResponse } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import Combobox from '$lib/components/ui/combobox/combobox.svelte';
	import type { ComboboxItem } from '$lib/components/ui/combobox/combobox';
	import TypeIcon from '$lib/components/type-icon.svelte';
	import { loadItemTypes, resetItemTypeCache } from '$lib/palette-sources';
	import { CREATE_PREFIX, NONE_VALUE, buildTypeItems, createdLabel } from '$lib/type-picker';
	import { slugify } from '$lib/utils.js';

	// The one place an item type is chosen: search the types, the ones you use first, or type a
	// new name and create it in the same step.
	let {
		value = $bindable(null as string | null),
		nodeTypes = undefined,
		allowClear = true,
		disabled = false,
		onchange,
		oncreate,
		...restProps
	}: {
		value?: string | null;
		/** The types to offer, if the page already has them; otherwise they are loaded. */
		nodeTypes?: NodeTypeResponse[];
		/** Offer "No item type". */
		allowClear?: boolean;
		disabled?: boolean;
		onchange?: (slug: string | null) => void;
		/** Called with a type this picker just created, so the page can add it to its own list. */
		oncreate?: (type: NodeTypeResponse) => void;
		[key: string]: unknown;
	} = $props();

	// svelte-ignore state_referenced_locally
	let types = $state<NodeTypeResponse[]>(nodeTypes ?? []);
	let counts = $state(new Map<string, number>());
	let query = $state('');
	let comboValue = $derived(value ?? NONE_VALUE);

	$effect(() => {
		if (!nodeTypes)
			void loadItemTypes()
				.then((all) => (types = all))
				.catch(() => {});
		void countNodeTypes().then((result) => {
			counts = new Map(
				(result.data ?? []).filter((row) => row.type !== null).map((row) => [row.type!, row.count])
			);
		});
	});

	const bySlug = $derived(new Map(types.map((type) => [type.slug, type])));
	const items = $derived(buildTypeItems({ types, counts, query, allowClear }));
	const selectedType = $derived(value ? bySlug.get(value) : undefined);
	const selectedItem = $derived<ComboboxItem | undefined>(
		value ? { value, label: selectedType?.label ?? value } : undefined
	);

	function select(slug: string | null) {
		value = slug;
		comboValue = slug ?? NONE_VALUE;
		onchange?.(slug);
	}

	async function choose(next: string) {
		const label = createdLabel(next);
		if (label === null) return select(next === NONE_VALUE ? null : next);
		const result = await createNodeType({ body: { slug: slugify(label), label } });
		if (result.error || !result.data) {
			toast.error("Couldn't create item type", { description: errorMessage(result.error) });
			comboValue = value ?? NONE_VALUE;
			return;
		}
		types = [...types, result.data];
		resetItemTypeCache();
		oncreate?.(result.data);
		select(result.data.slug);
	}
</script>

{#snippet leading(item: ComboboxItem)}
	{#if item.value === NONE_VALUE}
		<Ban class="size-4 shrink-0 text-muted-foreground" />
	{:else if item.value.startsWith(CREATE_PREFIX)}
		<Plus class="size-4 shrink-0 text-muted-foreground" />
	{:else}
		{@const type = bySlug.get(item.value)}
		<TypeIcon icon={type?.icon} colour={type?.colour} class="size-4 text-base" />
	{/if}
{/snippet}

<Combobox
	{items}
	{selectedItem}
	{leading}
	{disabled}
	bind:value={comboValue}
	onValueChange={choose}
	onsearch={(text) => (query = text)}
	placeholder="Choose an item type…"
	searchPlaceholder="Search item types…"
	emptyText="No item types yet. Type a name to create one."
	aria-label="Item type"
	{...restProps}
/>
