<script lang="ts">
	import { onDestroy } from 'svelte';
	import * as Combobox from '$lib/components/ui/combobox/index.js';
	import type { ComboboxItem } from '$lib/components/ui/combobox/index.js';
	import type { BuilderView, ItemChoice } from '$lib/query/builder';
	import { typeLabel } from '$lib/query/fields';

	let {
		itemId,
		label,
		view,
		onpick
	}: {
		/** The chosen item's id, if any. */
		itemId: string | undefined;
		/** The control's accessible name. */
		label: string;
		view: BuilderView;
		onpick: (id: string) => void;
	} = $props();

	const SEARCH_DELAY_MS = 250;

	let choices = $state<ItemChoice[]>([]);
	let failed = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;
	let seq = 0;

	const chosenName = $derived(itemId ? view.itemName(itemId) : undefined);
	const items = $derived.by((): ComboboxItem[] => {
		const out: ComboboxItem[] = [];
		// The chosen item stays listed so the trigger can name it whatever was searched.
		if (itemId) {
			const name = chosenName ?? (chosenName === null ? 'Item that no longer exists' : 'Item');
			out.push({ value: itemId, label: name });
		}
		for (const c of choices) {
			if (c.id === itemId) continue;
			const type = c.type ? ` (${typeLabel(view.catalogue, c.type)})` : '';
			out.push({ value: c.id, label: `${c.name}${type}`, selectedLabel: c.name });
		}
		return out;
	});

	function search(text: string) {
		clearTimeout(timer);
		const mine = ++seq;
		timer = setTimeout(
			async () => {
				const found = await view.searchItems(text);
				if (mine !== seq) return;
				failed = found === null;
				if (found) choices = found;
			},
			text === '' ? 0 : SEARCH_DELAY_MS
		);
	}

	function pick(id: string) {
		const choice = choices.find((c) => c.id === id);
		if (choice) view.rememberItem(choice);
		onpick(id);
	}

	onDestroy(() => clearTimeout(timer));
</script>

<Combobox.Root
	class="h-9 max-w-80"
	aria-label={label}
	{items}
	value={itemId ?? ''}
	placeholder="Choose an item"
	searchPlaceholder="Search items…"
	emptyText={failed ? 'Could not search your items' : 'No matching items'}
	onsearch={search}
	onValueChange={pick}
/>
