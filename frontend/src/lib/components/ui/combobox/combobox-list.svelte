<script lang="ts">
	import type { Snippet } from 'svelte';
	import * as Command from '$lib/components/ui/command/index.js';
	import { cn } from '$lib/utils.js';
	import ComboboxLabel from './combobox-label.svelte';
	import type { ComboboxGroup, ComboboxItem } from './combobox';

	// The list inside a combobox's popover, shared by the single and the multiple-choice one so
	// groups, headings, indented rows, crumbs and counts look and behave the same in every picker.
	// The search box and the open state stay with the combobox; this draws and reports a choice.
	let {
		id,
		groups,
		emptyText,
		checked,
		leading,
		onselect
	}: {
		id: string;
		groups: ComboboxGroup[];
		emptyText: string;
		/** Whether an item is chosen now. */
		checked: (item: ComboboxItem) => boolean;
		/** Drawn before the label in each row, such as an icon. */
		leading?: Snippet<[ComboboxItem]>;
		onselect: (item: ComboboxItem) => void;
	} = $props();
</script>

<Command.List {id} class="mt-1 max-h-[min(18rem,50dvh)]">
	{#if groups.length === 0}
		<p class="py-6 text-center text-sm text-muted-foreground" role="status">{emptyText}</p>
	{/if}
	{#each groups as group, index (group.heading ?? '')}
		<!-- A rule between groups, so each one reads as a block of its own. -->
		<Command.Group
			heading={group.heading ?? undefined}
			class={cn(index > 0 && 'mt-1 border-t border-border/60 pt-1')}
		>
			{#each group.items as item (item.value)}
				<Command.Item
					value={item.value}
					disabled={item.disabled}
					data-checked={checked(item)}
					class={cn('min-h-9', item.nested && 'pl-6')}
					onSelect={() => onselect(item)}
				>
					{#if leading}{@render leading(item)}{/if}
					<span class="min-w-0 flex-1 truncate">
						<!-- Under a heading that already names the crumb, the label stands alone. -->
						<ComboboxLabel
							label={item.label}
							crumb={item.crumb === item.group ? undefined : item.crumb}
						/>
					</span>
					{#if item.description}
						<span class="shrink-0 text-xs text-muted-foreground tabular-nums">
							{item.description}
						</span>
					{/if}
				</Command.Item>
			{/each}
		</Command.Group>
	{/each}
</Command.List>
