<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import XIcon from '@lucide/svelte/icons/x';
	import * as Command from '$lib/components/ui/command/index.js';
	import * as Popover from '$lib/components/ui/popover/index.js';
	import ComboboxLabel from './combobox-label.svelte';
	import { cn } from '$lib/utils.js';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import {
		filterComboboxItems,
		groupComboboxItems,
		selectedComboboxItems,
		toggleComboboxValue,
		type ComboboxItem
	} from './combobox';

	// The multiple-choice sibling of Combobox: the same items and search, but several values.
	// The choices show as removable chips above the trigger, and the list stays open while you
	// pick more.
	type MultiComboboxProps = Omit<HTMLButtonAttributes, 'value' | 'children'> & {
		items: ComboboxItem[];
		value?: string[];
		placeholder?: string;
		searchPlaceholder?: string;
		emptyText?: string;
		onValueChange?: (value: string[]) => void;
		/** Search on the server, as on Combobox: `items` is then shown as given. */
		onsearch?: (text: string) => void;
		/** Drawn before the label in each row and chip, such as an icon. */
		leading?: Snippet<[ComboboxItem]>;
		/** Labels a chosen value that is not among `items`, so it can still be removed. */
		unknownLabel?: (value: string) => string;
		/** Names a chip's remove button: "Remove {label}" by default. */
		removeLabel?: (label: string) => string;
		ref?: HTMLButtonElement | null;
	};

	let {
		items,
		value = $bindable([]),
		placeholder = 'Add…',
		searchPlaceholder = 'Search…',
		emptyText = 'Nothing found',
		onValueChange,
		onsearch,
		leading,
		unknownLabel,
		removeLabel = (label) => `Remove ${label}`,
		ref = $bindable(null),
		class: className,
		disabled = false,
		...restProps
	}: MultiComboboxProps = $props();

	let open = $state(false);
	let query = $state('');
	let highlighted = $state('');
	const listId = $props.id();

	const chosen = $derived(selectedComboboxItems(items, value, unknownLabel));
	const groups = $derived(groupComboboxItems(onsearch ? items : filterComboboxItems(items, query)));

	$effect(() => {
		const text = query;
		if (open) untrack(() => onsearch?.(text));
	});

	function setOpen(next: boolean) {
		if (next) {
			query = '';
			highlighted = '';
		}
		open = next;
	}

	function change(next: string[]) {
		value = next;
		onValueChange?.(next);
	}

	function toggle(item: ComboboxItem) {
		change(toggleComboboxValue(value, item.value));
	}

	function onTriggerKeydown(e: KeyboardEvent) {
		if (e.key === 'ArrowDown' && !open) {
			e.preventDefault();
			setOpen(true);
		}
	}
</script>

<div class="space-y-1.5">
	{#if chosen.length > 0}
		<ul class="flex flex-wrap gap-1.5" data-slot="multi-combobox-chips">
			{#each chosen as item (item.value)}
				<li
					class="inline-flex max-w-full items-center gap-1 rounded-full bg-secondary py-0.5 pr-1 pl-2.5 text-xs text-secondary-foreground"
				>
					{#if leading}{@render leading(item)}{/if}
					<span class="min-w-0 truncate">
						<ComboboxLabel label={item.selectedLabel ?? item.label} crumb={item.crumb} />
					</span>
					<button
						type="button"
						{disabled}
						aria-label={removeLabel(item.selectedLabel ?? item.label)}
						class="relative rounded-full p-0.5 after:absolute after:-inset-2 after:content-[''] hover:bg-foreground/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
						onclick={() => change(value.filter((v) => v !== item.value))}
					>
						<XIcon class="size-3" aria-hidden="true" />
					</button>
				</li>
			{/each}
		</ul>
	{/if}

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
		<span class="min-w-0 flex-1 truncate text-muted-foreground">{placeholder}</span>
		<ChevronDownIcon class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
	</button>
</div>

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
			data-checked={value.includes(item.value)}
			class="min-h-9"
			onSelect={() => toggle(item)}
		>
			{#if leading}{@render leading(item)}{/if}
			<span class="min-w-0 flex-1 truncate">
				<ComboboxLabel
					label={item.label}
					crumb={item.crumb === item.group ? undefined : item.crumb}
				/>
			</span>
			{#if item.description}
				<span class="shrink-0 text-xs text-muted-foreground tabular-nums">{item.description}</span>
			{/if}
		</Command.Item>
	{/each}
{/snippet}
