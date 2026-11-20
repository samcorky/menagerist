<script lang="ts">
	import { Select } from 'bits-ui';
	import { ChevronDown } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { optionLabel, staleChoice } from './stale-choice';
	import { readPropMeta } from '$lib/schema-meta';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let {
		value,
		onChange,
		ariaLabel,
		prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	let selected = $derived(typeof value === 'string' ? value : '');
	let options = $derived(prop.type === 'string' && 'enum' in prop ? prop.enum : []);
	let stale = $derived(staleChoice(value, options));
	let staleLabel = $derived(stale === null ? null : `${stale} (no longer an option)`);
	let variant = $derived(readPropMeta(prop).display);
	let labels = $derived(readPropMeta(prop).labels);
	// Options for radio and chips, with a stale stored value shown as an extra entry.
	let entries = $derived([
		...(stale !== null && staleLabel !== null ? [{ value: stale, label: staleLabel }] : []),
		...options.map((o) => ({ value: o, label: optionLabel(labels, o) }))
	]);
	const uid = $props.id();
</script>

{#if variant === 'radio'}
	<div role="radiogroup" aria-label={ariaLabel} class="flex flex-wrap items-center gap-x-4 gap-y-1">
		{#each entries as entry (entry.value)}
			<label class="flex items-center gap-1.5 text-sm">
				<input
					type="radio"
					name="choice-{uid}"
					value={entry.value}
					checked={selected === entry.value}
					onchange={() => onChange(entry.value)}
					class="h-4 w-4 accent-primary"
				/>
				{entry.label}
			</label>
		{/each}
		{#if selected !== ''}
			<Button
				type="button"
				variant="ghost"
				size="sm"
				class="h-7 text-xs"
				onclick={() => onChange('')}
			>
				Clear
			</Button>
		{/if}
	</div>
{:else if variant === 'chips'}
	<div role="group" aria-label={ariaLabel} class="flex flex-wrap gap-2">
		{#each entries as entry (entry.value)}
			{@const active = selected === entry.value}
			<button
				type="button"
				aria-pressed={active}
				class="rounded-full border px-3 py-1 text-sm transition-colors focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none {active
					? 'border-primary bg-primary text-primary-foreground'
					: 'border-input bg-background hover:bg-accent'}"
				onclick={() => onChange(active ? '' : entry.value)}
			>
				{entry.label}
			</button>
		{/each}
	</div>
{:else}
	<Select.Root type="single" value={selected} onValueChange={(v) => onChange(v ?? '')}>
		<Select.Trigger
			class="flex h-8 min-w-0 flex-1 cursor-pointer items-center justify-between gap-2 rounded-2xl border border-transparent bg-input/50 py-1 pr-2.5 pl-2.5 text-left text-sm transition-[color,box-shadow] duration-200 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
			aria-label={ariaLabel}
		>
			<span class="min-w-0 truncate {selected && stale === null ? '' : 'text-muted-foreground'}"
				>{staleLabel ?? (selected ? optionLabel(labels, selected) : '- select -')}</span
			>
			<ChevronDown class="size-4 shrink-0 text-muted-foreground" />
		</Select.Trigger>
		<Select.Content
			align="start"
			sideOffset={4}
			class="z-50 max-h-60 min-w-(--bits-select-anchor-width) overflow-auto rounded-2xl bg-popover p-1 text-popover-foreground shadow-lg ring-1 ring-foreground/5 dark:ring-foreground/10"
		>
			<Select.Item
				value=""
				label="- select -"
				class="flex min-h-7 cursor-pointer items-center rounded-xl px-2 py-1.5 text-sm text-muted-foreground outline-none data-[highlighted]:bg-muted"
			>
				- select -
			</Select.Item>
			{#if stale !== null && staleLabel !== null}
				<Select.Item
					value={stale}
					label={staleLabel}
					class="flex min-h-7 cursor-pointer items-center rounded-xl px-2 py-1.5 text-sm text-muted-foreground outline-none data-[highlighted]:bg-muted data-[selected]:font-medium"
				>
					{staleLabel}
				</Select.Item>
			{/if}
			{#each options as option (option)}
				<Select.Item
					value={option}
					label={optionLabel(labels, option)}
					class="flex min-h-7 cursor-pointer items-center rounded-xl px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-muted data-[selected]:font-medium"
				>
					{optionLabel(labels, option)}
				</Select.Item>
			{/each}
		</Select.Content>
	</Select.Root>
{/if}
