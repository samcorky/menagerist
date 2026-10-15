<script lang="ts">
	import { TriangleAlert, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import QueryValueInput from '$lib/components/query-value-input.svelte';
	import {
		conditionProblem,
		DATE_OPERATORS,
		fieldOf,
		fieldSubject,
		GENERAL_SUBJECTS,
		isBlank,
		operatorLabel,
		ARCHIVED_FIELD_MESSAGE,
		fieldStatus,
		STALE_FIELD_MESSAGE,
		strayValueText,
		subjectOf,
		TAG_MODES,
		withOperator,
		withSubject,
		type BuilderView
	} from '$lib/query/builder';
	import { fieldReferenceLabel, filterableFields, groupByType } from '$lib/query/fields';
	import { operatorsForKind } from '$lib/query/operators';
	import { pathKey } from '$lib/query/warnings';
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
	const warned = $derived(view.warned.has(key) || status === 'missing' || status === 'archived');
	const warning = $derived(status === 'archived' ? ARCHIVED_FIELD_MESSAGE : STALE_FIELD_MESSAGE);
	const problem = $derived(
		isBlank(condition) || status === 'loading' ? null : conditionProblem(condition, view.catalogue)
	);
	const stray = $derived(
		problem && field && condition.kind === 'field' && !Array.isArray(condition.value)
			? strayValueText(field.kind, condition.value)
			: null
	);
	const error = $derived(view.error?.key === key ? view.error.message : null);

	/** The operators to offer; one the field cannot use is still shown, flagged, so the row never misleads. */
	const operators = $derived.by((): { value: string; label: string }[] => {
		if (condition.kind === 'tag') return TAG_MODES.map((m) => ({ ...m }));
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
		condition.kind === 'tag' ? condition.mode : 'op' in condition ? condition.op : ''
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
		<NativeSelect.Root
			class="min-w-0 flex-1 basis-48 [&_select]:h-9"
			aria-label="{name}, field"
			data-row-subject={key}
			value={subject}
			onchange={(e) => onSubject(e.currentTarget.value)}
		>
			{#if subject === 'blank'}
				<NativeSelect.Option value="blank" disabled>Choose what to filter on</NativeSelect.Option>
			{/if}
			{#if status !== 'ok' && condition.kind === 'field'}
				<NativeSelect.Option value={subject}>
					{fieldReferenceLabel(
						view.catalogue,
						condition.type,
						condition.key,
						condition.sub_key
					)}{STATUS_SUFFIX[status]}
				</NativeSelect.Option>
			{/if}
			<NativeSelect.OptGroup label="Any item">
				{#each GENERAL_SUBJECTS as general (general.value)}
					<NativeSelect.Option value={general.value}>{general.label}</NativeSelect.Option>
				{/each}
			</NativeSelect.OptGroup>
			{#each fieldGroups as group (group.slug)}
				<NativeSelect.OptGroup label={group.label}>
					{#each group.fields as f (fieldSubject(f.type, f.key, f.subKey))}
						<NativeSelect.Option value={fieldSubject(f.type, f.key, f.subKey)}>
							{group.label} › {f.label}
						</NativeSelect.Option>
					{/each}
				</NativeSelect.OptGroup>
			{/each}
		</NativeSelect.Root>
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
			<QueryValueInput
				{condition}
				{name}
				{view}
				onchange={(next, debounce) => view.update(path, next, { debounce })}
			/>
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
