<script lang="ts">
	import { Input } from '$lib/components/ui/input/index.js';
	import { NativeSelect, NativeSelectOption } from '$lib/components/ui/native-select/index.js';
	import { allDescriptors, getDescriptor } from '$lib/field-types';
	import { allowedKinds, changeKind, kindChangeWarning } from '$lib/field-types/kind-changes';
	import { displayChoices, displayValue, setDisplayValue } from '$lib/field-types/display-options';
	import type { EditorField } from '$lib/schema-types';

	let {
		field,
		allowGroup = true,
		onLabelChange,
		onFieldChange
	}: {
		field: EditorField;
		allowGroup?: boolean;
		onLabelChange: (value: string) => void;
		onFieldChange: (field: EditorField) => void;
	} = $props();

	function kindOptions() {
		const listed = allDescriptors().filter(
			(d) => d.selectable !== false && (allowGroup || d.kind !== 'group')
		);
		const permitted = allowedKinds(
			field.originalKind,
			listed.map((d) => d.kind)
		);
		return listed.filter((d) => permitted.includes(d.kind));
	}

	function displayOptionsFor() {
		return field.kind === 'opaque' ? [] : (getDescriptor(field.kind)?.displayOptions ?? []);
	}

	let warning = $derived(kindChangeWarning(field.originalKind, field.kind));
	let desc = $derived(getDescriptor(field.kind));
</script>

<div class="flex flex-wrap items-center gap-2">
	<Input
		value={field.label}
		placeholder="Label"
		class="w-full min-w-32 flex-1 sm:w-40 sm:flex-none"
		aria-label="Field label"
		oninput={(e) => onLabelChange((e.target as HTMLInputElement).value)}
	/>
	{#if field.kind === 'opaque'}
		<span class="rounded border border-input px-1.5 text-xs text-muted-foreground">custom</span>
	{:else}
		<NativeSelect
			value={field.kind}
			onchange={(e) => onFieldChange(changeKind(field, (e.target as HTMLSelectElement).value))}
			aria-label="Field type"
		>
			{#each kindOptions() as d (d.kind)}
				<NativeSelectOption value={d.kind}>{d.label}</NativeSelectOption>
			{/each}
		</NativeSelect>
	{/if}
	{#each displayOptionsFor() as option (option.key)}
		<span class="inline-flex items-center gap-1.5">
			<span class="text-xs text-muted-foreground">{option.label}</span>
			<NativeSelect
				value={displayValue(field, option)}
				onchange={(e) =>
					onFieldChange(setDisplayValue(field, option, (e.target as HTMLSelectElement).value))}
				aria-label={option.label}
			>
				{#each displayChoices(field, option) as choice (choice.value)}
					<NativeSelectOption value={choice.value}>{choice.label}</NativeSelectOption>
				{/each}
			</NativeSelect>
		</span>
	{/each}
	<label class="flex items-center gap-1.5 text-sm">
		<input
			type="checkbox"
			checked={field.required}
			onchange={(e) =>
				onFieldChange({ ...field, required: (e.target as HTMLInputElement).checked })}
			class="h-4 w-4 rounded border-input accent-primary"
		/>
		Required
	</label>
</div>
{#if warning}
	<p class="text-xs text-muted-foreground" role="status">{warning}</p>
{/if}
{#if desc?.EditorExtras}
	{@const Extras = desc.EditorExtras}
	<Extras {field} onChange={onFieldChange} />
{/if}
