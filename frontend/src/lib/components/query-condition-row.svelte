<script lang="ts">
	import { TriangleAlert, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Combobox from '$lib/components/ui/combobox/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import QueryConnectionInput from '$lib/components/query-connection-input.svelte';
	import QueryValueInput from '$lib/components/query-value-input.svelte';
	import {
		conditionProblem,
		DATE_OPERATORS,
		fieldOf,
		fieldSubject,
		GENERAL_SUBJECTS,
		isBlank,
		MEDIA_MODES,
		operatorLabel,
		ARCHIVED_FIELD_MESSAGE,
		COLLECTION_MODES,
		CONNECTION_MODES,
		withConnectionMode,
		fieldStatus,
		itemFieldPickerItems,
		missingFieldMessage,
		NO_ITEM_FIELD_NOTE,
		strayValueText,
		subjectOf,
		TAG_MODES,
		withCollectionMode,
		withMediaMode,
		withOperator,
		withSubject,
		type BuilderView
	} from '$lib/query/builder';
	import { fieldReferenceLabel, filterableFields, groupByType } from '$lib/query/fields';
	import { operatorsForCondition, operatorsForKind } from '$lib/query/operators';
	import { pathKey } from '$lib/query/warnings';
	import type { ComboboxItem } from '$lib/components/ui/combobox/index.js';
	import type { Condition, Path } from '$lib/query/types';

	let { condition, path, view }: { condition: Condition; path: Path; view: BuilderView } = $props();

	const STATUS_SUFFIX = {
		ok: '',
		loading: '',
		missing: ' (no longer exists)',
		archived: ' (archived)'
	} as const;

	const key = $derived(pathKey(path));
	const number = $derived(view.numbers.get(key) ?? 0);
	const name = $derived(`Condition ${number}`);
	const subject = $derived(subjectOf(condition));
	const field = $derived(fieldOf(condition, view.catalogue));
	const fieldGroups = $derived(groupByType(view.catalogue, filterableFields(view.catalogue)));
	const status = $derived(fieldStatus(condition, view.catalogue));
	const subjectItems = $derived.by((): ComboboxItem[] => {
		const items: ComboboxItem[] = [];
		if (status !== 'ok' && condition.kind === 'field') {
			const label = fieldReferenceLabel(
				view.catalogue,
				condition.type,
				condition.key,
				condition.sub_key
			);
			const suffix =
				status === 'missing' && condition.field_kind !== undefined
					? ` (${NO_ITEM_FIELD_NOTE})`
					: STATUS_SUFFIX[status];
			items.push({ value: subject, label: `${label}${suffix}` });
		}
		for (const general of GENERAL_SUBJECTS) {
			// A connection cannot sit inside another connection's filter on the linked item.
			if (general.value === 'connection' && !view.canNestConnection(path)) continue;
			items.push({ value: general.value, label: general.label, group: general.group });
		}
		for (const group of fieldGroups) {
			for (const f of group.fields) {
				items.push({
					value: fieldSubject(f.type, f.key, f.subKey),
					label: f.label,
					group: group.label,
					selectedLabel: `${group.label} › ${f.label}`
				});
			}
		}
		items.push(...itemFieldPickerItems(view.catalogue));
		// A per-item row chosen before the listing was read still needs a label on the trigger.
		if (condition.kind === 'field' && condition.field_kind !== undefined && status === 'ok') {
			if (!items.some((i) => i.value === subject)) {
				const label = fieldReferenceLabel(view.catalogue, undefined, condition.key);
				items.push({ value: subject, label });
			}
		}
		return items;
	});
	// A collection the person no longer has: known as soon as the list of collections is in.
	const goneCollection = $derived(
		condition.kind === 'collection' &&
			view.collections !== null &&
			condition.in.some((id) => !view.collections?.some((c) => c.id === id))
	);
	// A relationship that is not among the loaded ones: known as soon as they are in.
	const goneRelationship = $derived(
		condition.kind === 'connection' &&
			condition.relationship !== undefined &&
			view.relationships !== null &&
			!view.relationships.some((r) => r.slug === condition.relationship)
	);
	const warned = $derived(
		view.warned.has(key) ||
			status === 'missing' ||
			status === 'archived' ||
			goneCollection ||
			goneRelationship
	);
	const warning = $derived(
		status === 'archived'
			? ARCHIVED_FIELD_MESSAGE
			: condition.kind === 'connection'
				? (view.warningMessages.get(key) ??
					(goneRelationship
						? `The relationship '${condition.relationship}' no longer exists.`
						: missingFieldMessage(condition)))
				: missingFieldMessage(condition)
	);
	const problem = $derived(
		isBlank(condition) || status === 'loading' ? null : conditionProblem(condition, view.catalogue)
	);
	const stray = $derived(
		problem && field && condition.kind === 'field' && !Array.isArray(condition.value)
			? strayValueText(field.kind, condition.value)
			: null
	);
	const error = $derived(view.error?.key === key ? view.error.message : null);

	/** Show all operators, but flag the ones that a field cannot use. */
	const operators = $derived.by((): { value: string; label: string }[] => {
		if (condition.kind === 'tag') return TAG_MODES.map((m) => ({ ...m }));
		if (condition.kind === 'media') return MEDIA_MODES.map((m) => ({ ...m }));
		if (condition.kind === 'collection') return COLLECTION_MODES.map((m) => ({ ...m }));
		if (condition.kind === 'connection') return CONNECTION_MODES.map((m) => ({ ...m }));
		if (condition.kind === 'description' || condition.kind === 'name') {
			return operatorsForCondition(condition.kind).map((op) => ({
				value: op,
				label: operatorLabel(condition.kind, op)
			}));
		}
		let kind: string;
		let ops: readonly string[];
		if (condition.kind === 'date') {
			kind = 'date';
			ops = DATE_OPERATORS;
		} else if (condition.kind === 'field' && !isBlank(condition)) {
			kind = field?.kind ?? '';
			ops = field ? operatorsForKind(field.kind) : [condition.op];
		} else return [];
		const options = ops.map((op) => ({ value: op, label: operatorLabel(kind, op) }));
		if (!condition.op || ops.includes(condition.op)) return options;
		const unsuitable = `${operatorLabel(kind, condition.op)} (not available here)`;
		return [{ value: condition.op, label: unsuitable }, ...options];
	});
	const operatorValue = $derived(
		condition.kind === 'tag' ||
			condition.kind === 'media' ||
			condition.kind === 'collection' ||
			condition.kind === 'connection'
			? condition.mode
			: 'op' in condition
				? condition.op
				: ''
	);
	const fixedOperator = $derived(
		condition.kind === 'text'
			? 'contains'
			: condition.kind === 'type'
				? 'is one of'
				: condition.kind === 'favourite'
					? 'is'
					: null
	);

	function onSubject(value: string) {
		view.update(path, withSubject(condition, value, view.catalogue));
	}

	function onOperator(value: string) {
		if (condition.kind === 'tag') {
			const mode = TAG_MODES.find((m) => m.value === value)?.value ?? 'any';
			view.update(path, { ...condition, mode });
		} else if (condition.kind === 'media') {
			view.update(path, withMediaMode(condition, value === 'none' ? 'none' : 'has'));
		} else if (condition.kind === 'collection') {
			view.update(path, withCollectionMode(condition, value === 'none' ? 'none' : 'any'));
		} else if (condition.kind === 'connection') {
			view.update(
				path,
				withConnectionMode(condition, value === 'none' ? 'none' : value === 'to' ? 'to' : 'exists')
			);
		} else view.update(path, withOperator(condition, value, view.catalogue));
	}
</script>

<li
	class="rounded-xl border bg-card p-3 {warned || error ? 'border-destructive/40' : ''}"
	data-row-key={key}
>
	<div class="flex flex-wrap items-center gap-2">
		<span
			class="w-6 shrink-0 text-xs font-medium text-muted-foreground tabular-nums"
			aria-hidden="true">{number}</span
		>
		<Combobox.Root
			class="h-9 min-w-0 flex-1 basis-48"
			aria-label="{name}, field"
			data-row-subject={key}
			items={subjectItems}
			value={subject}
			placeholder="Choose what to filter on"
			searchPlaceholder="Search fields…"
			emptyText="No matching fields"
			onValueChange={onSubject}
		/>
		{#if operators.length > 0}
			<NativeSelect.Root
				class="min-w-0 flex-1 basis-36 [&_select]:h-9"
				aria-label="{name}, operator"
				value={operatorValue}
				onchange={(e) => onOperator(e.currentTarget.value)}
			>
				{#each operators as op (op.value)}
					<NativeSelect.Option value={op.value}>{op.label}</NativeSelect.Option>
				{/each}
			</NativeSelect.Root>
		{:else if fixedOperator}
			<span class="text-sm text-muted-foreground">{fixedOperator}</span>
		{/if}
		<Button
			variant="ghost"
			size="icon"
			class="ml-auto shrink-0"
			aria-label="Remove condition {number}"
			onclick={() => view.remove(path)}
		>
			<X />
		</Button>
	</div>

	{#if status === 'loading'}
		<p class="mt-2 text-sm text-muted-foreground sm:pl-8">Loading fields…</p>
	{:else if !isBlank(condition)}
		<div class="mt-2 sm:pl-8">
			{#if condition.kind === 'connection'}
				<QueryConnectionInput
					{condition}
					{path}
					{name}
					{view}
					onchange={(next) => view.update(path, next)}
				/>
			{:else}
				<QueryValueInput
					{condition}
					{name}
					{view}
					onchange={(next, debounce) => view.update(path, next, { debounce })}
				/>
			{/if}
		</div>
	{/if}

	{#if warned}
		<p class="mt-2 flex items-start gap-1.5 text-sm sm:pl-8">
			<TriangleAlert class="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
			<span>{warning}</span>
		</p>
	{/if}
	{#if error}
		<p class="mt-2 flex items-start gap-1.5 text-sm text-destructive sm:pl-8">
			<TriangleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
			<span>{error}</span>
		</p>
	{/if}
	{#if problem}
		<p class="mt-2 text-sm text-muted-foreground sm:pl-8">
			{#if stray}The current value “{stray}” does not fit.{/if}
			{problem}
			{#if condition.kind !== 'field' || field}<span class="sr-only">
					This condition is not applied yet.</span
				>{/if}
		</p>
	{/if}
</li>
