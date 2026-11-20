<script lang="ts">
	import { Ellipsis } from '@lucide/svelte';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { flagsFor, setFlag } from '$lib/field-flags';
	import type { EditorField } from '$lib/schema-types';

	let { field, onChange }: { field: EditorField; onChange: (field: EditorField) => void } =
		$props();

	let flags = $derived(flagsFor(field.kind));
	const itemClass = 'pointer-coarse:min-h-11';
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger>
		{#snippet child({ props })}
			<Button
				{...props}
				type="button"
				variant="ghost"
				size="icon"
				class="shrink-0 pointer-coarse:size-11"
				aria-label="Field options for {field.label || 'this field'}"
			>
				<Ellipsis class="size-4" />
			</Button>
		{/snippet}
	</DropdownMenu.Trigger>
	<DropdownMenu.Content align="end">
		<DropdownMenu.CheckboxItem
			class={itemClass}
			closeOnSelect={false}
			checked={field.required}
			onCheckedChange={(on) => onChange({ ...field, required: on })}
		>
			Required
		</DropdownMenu.CheckboxItem>
		{#each flags as flag (flag.member)}
			<DropdownMenu.CheckboxItem
				class={itemClass}
				closeOnSelect={false}
				checked={field.meta?.[flag.member] === true}
				onCheckedChange={(on) => onChange(setFlag(field, flag.member, on))}
			>
				{flag.label}
			</DropdownMenu.CheckboxItem>
		{/each}
	</DropdownMenu.Content>
</DropdownMenu.Root>
