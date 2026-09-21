<script lang="ts">
	import { Select } from 'bits-ui';
	import { ChevronDown } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { staleChoice } from './stale-choice';
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
	// Options for radio and chips, with a stale stored value shown as an extra entry.
	let entries = $derived([
		...(stale !== null && staleLabel !== null ? [{ value: stale, label: staleLabel }] : []),
		...options.map((o) => ({ value: o, label: o }))
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
			class="flex h-9 flex-1 cursor-pointer items-center justify-between rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors hover:bg-accent/10 focus:ring-1 focus:ring-ring focus:outline-none"
			aria-label={ariaLabel}
		>
			<span class={selected && stale === null ? '' : 'text-muted-foreground'}
				>{staleLabel ?? (selected || '— select —')}</span
			>
			<ChevronDown class="size-4 shrink-0 text-muted-foreground" />
		</Select.Trigger>
		<Select.Content
			class="z-50 max-h-60 min-w-[8rem] overflow-auto rounded-md border bg-popover p-1 shadow-md"
		>
			<Select.Item
				value=""
				label="— select —"
				class="flex cursor-pointer items-center rounded px-2 py-1.5 text-sm text-muted-foreground outline-none data-[highlighted]:bg-accent"
			>
				— select —
			</Select.Item>
			{#if stale !== null && staleLabel !== null}
				<Select.Item
					value={stale}
					label={staleLabel}
					class="flex cursor-pointer items-center rounded px-2 py-1.5 text-sm text-muted-foreground outline-none data-[highlighted]:bg-accent data-[selected]:font-medium"
				>
					{staleLabel}
				</Select.Item>
			{/if}
			{#each options as option (option)}
				<Select.Item
					value={option}
					label={option}
					class="flex cursor-pointer items-center rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-accent data-[selected]:font-medium"
				>
					{option}
				</Select.Item>
			{/each}
		</Select.Content>
	</Select.Root>
{/if}
