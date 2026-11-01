<script lang="ts">
	import { tick, untrack, type Snippet } from 'svelte';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import * as Command from '$lib/components/ui/command/index.js';
	import * as Popover from '$lib/components/ui/popover/index.js';
	import { cn } from '$lib/utils.js';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import {
		filterComboboxItems,
		groupComboboxItems,
		selectedComboboxItem,
		type ComboboxItem
	} from './combobox';

	type ComboboxProps = Omit<HTMLButtonAttributes, 'value' | 'children'> & {
		items: ComboboxItem[];
		value?: string;
		placeholder?: string;
		searchPlaceholder?: string;
		emptyText?: string;
		onValueChange?: (value: string) => void;
		/**
		 * Search on the server: the typed text is passed on (and "" when the list opens), and
		 * `items` is shown as given instead of being filtered here.
		 */
		onsearch?: (text: string) => void;
		/** Drawn before the label in each row and on the trigger, such as an icon. */
		leading?: Snippet<[ComboboxItem]>;
		/** Shown on the trigger when `value` is not among `items` (for example, filtered out by a search). */
		selectedItem?: ComboboxItem;
		ref?: HTMLButtonElement | null;
	};

	let {
		items,
		value = $bindable(''),
		placeholder = 'Choose…',
		searchPlaceholder = 'Search…',
		emptyText = 'Nothing found',
		onValueChange,
		onsearch,
		leading,
		selectedItem,
		ref = $bindable(null),
		class: className,
		disabled = false,
		...restProps
	}: ComboboxProps = $props();

	let open = $state(false);
	let query = $state('');
	let highlighted = $state('');
	const listId = $props.id();

	const selected = $derived(selectedComboboxItem(items, value) ?? selectedItem);
	const groups = $derived(groupComboboxItems(onsearch ? items : filterComboboxItems(items, query)));

	$effect(() => {
		const text = query;
		if (open) untrack(() => onsearch?.(text));
	});

	function setOpen(next: boolean) {
		if (next) {
			query = '';
			highlighted = selected?.value ?? '';
		}
		open = next;
	}

	function choose(item: ComboboxItem) {
		setOpen(false);
		if (item.value !== value) {
			value = item.value;
			onValueChange?.(item.value);
		}
		tick().then(() => ref?.focus());
	}

	function onTriggerKeydown(e: KeyboardEvent) {
		if (e.key === 'ArrowDown' && !open) {
			e.preventDefault();
			setOpen(true);
		}
	}
</script>

<button
	bind:this={ref}
	type="button"
	role="combobox"
	aria-haspopup="listbox"
	aria-expanded={open}
	aria-controls={open ? listId : undefined}
	data-slot="combobox-trigger"
	{disabled}
	class={cn(
		'flex h-8 w-full min-w-0 items-center justify-between gap-2 rounded-2xl border border-transparent bg-input/50 py-1 pr-2.5 pl-2.5 text-left text-sm transition-[color,box-shadow] duration-200 outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40',
		className
	)}
	onclick={() => setOpen(!open)}
	onkeydown={onTriggerKeydown}
	{...restProps}
>
	{#if selected && leading}{@render leading(selected)}{/if}
	<span class={cn('min-w-0 flex-1 truncate', !selected && 'text-muted-foreground')}>
		{selected ? (selected.selectedLabel ?? selected.label) : placeholder}
	</span>
	<ChevronDownIcon class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
</button>

<Popover.Root {open} onOpenChange={setOpen}>
	<Popover.Content
		customAnchor={ref}
		align="start"
		collisionPadding={8}
		class="max-h-(--bits-popover-content-available-height) w-(--bits-popover-anchor-width) min-w-48 gap-0 rounded-2xl p-1"
		onInteractOutside={(e) => {
			// The trigger's own click toggles; closing here as well would reopen it.
			if (ref?.contains(e.target as Node)) e.preventDefault();
		}}
		onCloseAutoFocus={(e) => {
			e.preventDefault();
			ref?.focus();
		}}
	>
		<Command.Root shouldFilter={false} loop bind:value={highlighted} class="bg-transparent p-0">
			<Command.Input bind:value={query} placeholder={searchPlaceholder} aria-label="Search" />
			<Command.List id={listId} class="mt-1 max-h-[min(18rem,50dvh)]">
				{#if groups.length === 0}
					<p class="py-6 text-center text-sm text-muted-foreground" role="status">{emptyText}</p>
				{/if}
				{#each groups as group (group.heading ?? '')}
					{#if group.heading}
						<Command.Group heading={group.heading}>
							{@render rows(group.items)}
						</Command.Group>
					{:else}
						<Command.Group>
							{@render rows(group.items)}
						</Command.Group>
					{/if}
				{/each}
			</Command.List>
		</Command.Root>
	</Popover.Content>
</Popover.Root>

{#snippet rows(list: ComboboxItem[])}
	{#each list as item (item.value)}
		<Command.Item
			value={item.value}
			disabled={item.disabled}
			data-checked={item.value === value}
			class="min-h-9"
			onSelect={() => choose(item)}
		>
			{#if leading}{@render leading(item)}{/if}
			<span class="min-w-0 flex-1 truncate">{item.label}</span>
			{#if item.description}
				<span class="shrink-0 text-xs text-muted-foreground tabular-nums">{item.description}</span>
			{/if}
		</Command.Item>
	{/each}
{/snippet}
