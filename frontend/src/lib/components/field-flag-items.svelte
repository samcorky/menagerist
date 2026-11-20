<script lang="ts">
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import { flagsFor, setFlag } from '$lib/field-flags';
	import type { EditorField } from '$lib/schema-types';

	/** Required and the type-level switches, as checkbox rows in a field's actions menu. */
	let { field, onChange }: { field: EditorField; onChange: (field: EditorField) => void } =
		$props();

	let flags = $derived(flagsFor(field.kind));
	const itemClass = 'pointer-coarse:min-h-11';
</script>

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
