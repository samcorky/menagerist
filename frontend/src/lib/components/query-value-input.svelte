<script lang="ts">
	import { untrack } from 'svelte';
	import { descriptorForProp } from '$lib/field-types';
	import DateInput from '$lib/field-types/date/DateInput.svelte';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Combobox from '$lib/components/ui/combobox/index.js';
	import type { ComboboxItem } from '$lib/components/ui/combobox/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import TagsInput from '$lib/components/tags-input.svelte';
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import {
		fieldOf,
		fieldOptions,
		fromWidget,
		isRef,
		isRel,
		isTypedKind,
		relative,
		relativeParts,
		RELATIVE_MODES,
		stringList,
		toWidget,
		valueShape,
		type BuilderView,
		type RelativeMode
	} from '$lib/query/builder';
	import { Button } from '$lib/components/ui/button/index.js';
	import { canCompareWithField, refCandidates, typeLabel, type FieldInfo } from '$lib/query/fields';
	import type { Condition, Operand, Value } from '$lib/query/types';

	type SetOperand = (operand: Operand | undefined, debounce: boolean) => void;

	let {
		condition,
		name,
		view,
		onchange
	}: {
		condition: Condition;
		/** The row's accessible name, e.g. "Condition 2". */
		name: string;
		view: BuilderView;
		onchange: (condition: Condition, debounce: boolean) => void;
	} = $props();

	const label = $derived(`${name}, value`);
	const DATE_PROP: JsonSchemaProperty = { title: 'Date', type: 'string', format: 'date' };

	const field = $derived(fieldOf(condition, view.catalogue));
	// A per-item choice field has no option list to pick from, so its values are typed.
	const typedChoice = $derived(
		condition.kind === 'field' &&
			condition.field_kind !== undefined &&
			(field?.kind === 'choice' || field?.kind === 'multichoice')
	);
	const shape = $derived.by(() => {
		if (condition.kind !== 'field' || !field) return 'none';
		const base = valueShape(field.kind, condition.op);
		return typedChoice && base === 'multi' ? 'list' : base;
	});
	const candidates = $derived(field ? refCandidates(view.catalogue, field) : []);

	function refItems(current: string): ComboboxItem[] {
		const items = candidates.map((c) => ({ value: c.key, label: c.label }));
		return items.some((i) => i.value === current)
			? items
			: [{ value: current, label: `${current} (no longer exists)` }, ...items];
	}
	const canRef = $derived(shape === 'single' && canCompareWithField(view.catalogue, field));

	function setValue(value: Value | undefined, debounce: boolean) {
		if (condition.kind === 'field') {
			const { value: _old, ...rest } = condition;
			onchange(value === undefined ? rest : { ...rest, value }, debounce);
		} else if (condition.kind === 'date') {
			onchange({ ...condition, value: value ?? '' }, debounce);
		}
	}

	/** The value as a two-item range; anything else becomes two empty ends. */
	function rangeOf(value: unknown): [unknown, unknown] {
		return Array.isArray(value) && value.length === 2 ? [value[0], value[1]] : ['', ''];
	}

	function setEnd(index: 0 | 1, operand: Operand | undefined, debounce: boolean) {
		const value = condition.kind === 'field' || condition.kind === 'date' ? condition.value : '';
		const range = rangeOf(value).map((v) => v as Operand);
		range[index] = operand ?? '';
		setValue(range, debounce);
	}

	function toggleListValue(current: string[], option: string) {
		const next = current.includes(option)
			? current.filter((o) => o !== option)
			: [...current, option];
		setValue(next, false);
	}

	let listDraft = $state(
		untrack(() =>
			condition.kind === 'field' && Array.isArray(condition.value)
				? stringList(condition.value).join(', ')
				: ''
		)
	);

	const splitList = (text: string) =>
		text
			.split(',')
			.map((p) => p.trim())
			.filter(Boolean);

	// Keep the typed text (with its commas) unless the value changed from elsewhere.
	$effect(() => {
		const incoming =
			condition.kind === 'field' && Array.isArray(condition.value)
				? stringList(condition.value).join(', ')
				: '';
		untrack(() => {
			if (splitList(listDraft).join(', ') !== incoming) listDraft = incoming;
		});
	});

	function onListInput(text: string) {
		listDraft = text;
		setValue(splitList(text), true);
	}

	function onModeChange(operand: unknown, mode: string, set: SetOperand) {
		if (mode === 'date') return set(undefined, false);
		const count = isRel(operand) ? relativeParts(operand).count : '';
		set(relative(count || '1', mode as RelativeMode), false);
	}

	function toggleRef(f: FieldInfo) {
		if (condition.kind !== 'field') return;
		if (isRef(condition.value)) setValue(undefined, false);
		else setValue({ ref: refCandidates(view.catalogue, f)[0]?.key ?? '' }, false);
	}

	const segment =
		'min-h-9 px-3 text-sm transition-colors focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none';
	const chip =
		'min-h-9 rounded-full border px-3 py-1 text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none';
</script>

{#snippet yesNo(value: unknown, ariaLabel: string, set: (v: boolean) => void)}
	<div
		role="group"
		aria-label={ariaLabel}
		class="inline-flex w-fit overflow-hidden rounded-md border border-input"
	>
		{#each [true, false] as option (option)}
			<button
				type="button"
				aria-pressed={value === option}
				class="{segment} {option ? '' : 'border-l border-input'} {value === option
					? 'bg-primary text-primary-foreground'
					: 'bg-background hover:bg-accent'}"
				onclick={() => set(option)}
			>
				{option ? 'Yes' : 'No'}
			</button>
		{/each}
	</div>
{/snippet}

{#snippet chips(
	options: string[],
	selected: string[],
	ariaLabel: string,
	pick: (o: string) => void,
	optionLabel: (o: string) => string = (o) => o
)}
	<div role="group" aria-label={ariaLabel} class="flex flex-wrap gap-2">
		{#each [...selected.filter((s) => !options.includes(s)), ...options] as option (option)}
			{@const active = selected.includes(option)}
			<button
				type="button"
				aria-pressed={active}
				class="{chip} {active
					? 'border-primary bg-primary text-primary-foreground'
					: 'border-input bg-background hover:bg-accent'}"
				onclick={() => pick(option)}
			>
				{optionLabel(option)}{options.includes(option) ? '' : ' (no longer an option)'}
			</button>
		{:else}
			<p class="text-sm text-muted-foreground">This field has no options to choose from.</p>
		{/each}
	</div>
{/snippet}

{#snippet dateOperand(operand: unknown, ariaLabel: string, set: SetOperand, f?: FieldInfo)}
	{@const mode = isRel(operand) ? relativeParts(operand).mode : 'date'}
	<div class="flex min-w-0 flex-wrap items-center gap-2">
		{#if mode !== 'date'}
			<Input
				type="number"
				inputmode="numeric"
				min="0"
				max="999"
				class="h-9 w-20"
				aria-label="{ariaLabel}, how many"
				value={relativeParts(operand).count}
				oninput={(e) => set(relative(e.currentTarget.value, relativeParts(operand).mode), true)}
			/>
		{/if}
		<NativeSelect.Root
			class="[&_select]:h-9"
			aria-label="{ariaLabel}, a date or a time from today"
			value={mode}
			onchange={(e) => onModeChange(operand, e.currentTarget.value, set)}
		>
			<NativeSelect.Option value="date">a date</NativeSelect.Option>
			{#each RELATIVE_MODES as option (option.value)}
				<NativeSelect.Option value={option.value}>{option.label}</NativeSelect.Option>
			{/each}
		</NativeSelect.Root>
		{#if mode === 'date'}
			{@const Widget = f ? descriptorForProp(f.prop)?.InputWidget : undefined}
			<div class="min-w-40 flex-1">
				{#if f && f.kind === 'partialdate' && Widget}
					<Widget
						value={toWidget(f.kind, operand)}
						onChange={(raw) => set(fromWidget(f.kind, raw), true)}
						{ariaLabel}
						prop={f.prop}
					/>
				{:else}
					<DateInput
						value={typeof operand === 'string' ? operand : ''}
						onChange={(raw) => set(fromWidget('date', raw), false)}
						{ariaLabel}
						prop={DATE_PROP}
					/>
				{/if}
			</div>
		{/if}
	</div>
{/snippet}

{#snippet operandInput(f: FieldInfo, operand: unknown, ariaLabel: string, set: SetOperand)}
	{#if f.kind === 'date' || f.kind === 'partialdate'}
		{@render dateOperand(operand, ariaLabel, set, f)}
	{:else}
		{@const Widget = descriptorForProp(f.prop)?.InputWidget}
		{#if Widget}
			<div class="flex min-w-0 flex-1">
				<Widget
					value={toWidget(f.kind, operand)}
					onChange={(raw) => set(fromWidget(f.kind, raw), isTypedKind(f.kind))}
					{ariaLabel}
					prop={f.prop}
				/>
			</div>
		{/if}
	{/if}
{/snippet}

<div class="flex min-w-0 flex-col gap-2">
	{#if condition.kind === 'text'}
		<Input
			type="search"
			class="h-9"
			aria-label={label}
			placeholder="Words to look for"
			value={typeof condition.q === 'string' ? condition.q : ''}
			oninput={(e) => onchange({ kind: 'text', q: e.currentTarget.value }, true)}
		/>
	{:else if condition.kind === 'type'}
		{@render chips(
			view.catalogue.types.map((t) => t.slug),
			stringList(condition.in),
			label,
			(slug) => {
				const current = stringList(condition.kind === 'type' ? condition.in : []);
				const next = current.includes(slug)
					? current.filter((s) => s !== slug)
					: [...current, slug];
				onchange({ kind: 'type', in: next }, false);
			},
			(slug) => typeLabel(view.catalogue, slug)
		)}
	{:else if condition.kind === 'favourite'}
		{@render yesNo(condition.value, label, (value) =>
			onchange({ kind: 'favourite', value }, false)
		)}
	{:else if condition.kind === 'tag'}
		<TagsInput
			{label}
			labelClass="sr-only"
			bind:tags={
				() => stringList(condition.kind === 'tag' ? condition.tags : []),
				(tags) => {
					if (condition.kind === 'tag') onchange({ ...condition, tags }, false);
				}
			}
		/>
	{:else if condition.kind === 'date'}
		{#if condition.op === 'between'}
			{@const [from, to] = rangeOf(condition.value)}
			{@render dateOperand(from, `${label} from`, (o, d) => setEnd(0, o, d))}
			<span class="text-sm text-muted-foreground">and</span>
			{@render dateOperand(to, `${label} to`, (o, d) => setEnd(1, o, d))}
		{:else}
			{@render dateOperand(condition.value, label, (o, d) => setValue(o, d))}
		{/if}
	{:else if condition.kind === 'field' && !field}
		{#if 'value' in condition && condition.value !== undefined}
			<p class="text-sm text-muted-foreground">
				{JSON.stringify(condition.value)}
			</p>
		{/if}
	{:else if field && condition.kind === 'field'}
		{#if shape === 'range'}
			{@const [from, to] = rangeOf(condition.value)}
			{@render operandInput(field, from, `${label} from`, (o, d) => setEnd(0, o, d))}
			<span class="text-sm text-muted-foreground">and</span>
			{@render operandInput(field, to, `${label} to`, (o, d) => setEnd(1, o, d))}
		{:else if shape === 'multi'}
			{@const selected = stringList(condition.value)}
			{@render chips(fieldOptions(field), selected, label, (o) => toggleListValue(selected, o))}
		{:else if shape === 'list'}
			<Input
				class="h-9"
				aria-label={label}
				placeholder="Separate values with commas"
				value={listDraft}
				oninput={(e) => onListInput(e.currentTarget.value)}
			/>
		{:else if shape === 'boolean'}
			{@render yesNo(condition.value, label, (value) => setValue(value, false))}
		{:else if shape === 'single'}
			{#if isRef(condition.value)}
				<Combobox.Root
					class="h-9"
					aria-label="{label}, other field"
					items={refItems(condition.value.ref)}
					value={condition.value.ref}
					searchPlaceholder="Search fields…"
					emptyText="No matching fields"
					onValueChange={(ref) => setValue({ ref }, false)}
				/>
			{:else if typedChoice}
				<Input
					class="h-9"
					aria-label={label}
					placeholder="Type a value"
					value={typeof condition.value === 'string' ? condition.value : ''}
					oninput={(e) => setValue(e.currentTarget.value, true)}
				/>
			{:else}
				{@render operandInput(field, condition.value, label, (o, d) => setValue(o, d))}
			{/if}
		{/if}
		{#if canRef}
			{@const comparing = isRef(condition.value)}
			<Button
				variant="outline"
				size="sm"
				class="min-h-9 w-fit"
				aria-label="{name}, {comparing
					? 'compare with a value instead'
					: 'compare with another field'}"
				onclick={() => toggleRef(field)}
			>
				{comparing ? 'Compare with a value instead' : 'Compare with another field'}
			</Button>
		{/if}
	{/if}
</div>
