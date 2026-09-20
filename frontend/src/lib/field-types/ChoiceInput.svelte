<script lang="ts">
	import { Select } from 'bits-ui';
	import { ChevronDown } from '@lucide/svelte';
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
</script>

<Select.Root type="single" value={selected} onValueChange={(v) => onChange(v ?? '')}>
	<Select.Trigger
		class="flex h-9 flex-1 cursor-pointer items-center justify-between rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors hover:bg-accent/10 focus:ring-1 focus:ring-ring focus:outline-none"
		aria-label={ariaLabel}
	>
		<span class={selected ? '' : 'text-muted-foreground'}>{selected || '— select —'}</span>
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
