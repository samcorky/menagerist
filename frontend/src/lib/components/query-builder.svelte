<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { TriangleAlert } from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import QueryGroup from '$lib/components/query-group.svelte';
	import {
		applyDraft,
		conditionNumbers,
		draftPathFor,
		fieldSubject,
		parseFieldSubject,
		sortFromValue,
		sortValue,
		STALE_SORT_MESSAGE,
		type BuilderError,
		type BuilderView
	} from '$lib/query/builder';
	import { BuilderState } from '$lib/query/builder-state.svelte';
	import {
		fieldReferenceLabel,
		findField,
		groupByType,
		sortableFields,
		type Catalogue
	} from '$lib/query/fields';
	import { canAddCondition, canAddGroup } from '$lib/query/limits';
	import { pathKey } from '$lib/query/warnings';
	import type { Condition, Path, Query } from '$lib/query/types';

	let {
		open = $bindable(false),
		query,
		catalogue,
		warned = new Set<string>(),
		sortWarned = false,
		error = null,
		notice = null,
		focus = null,
		onchange
	}: {
		open?: boolean;
		/** The filter as applied (from the URL). */
		query: Query;
		catalogue: Catalogue;
		/** Filter path keys of conditions the server could not match. */
		warned?: ReadonlySet<string>;
		sortWarned?: boolean;
		/** The server's reason for refusing the filter. */
		error?: BuilderError | null;
		/** A page-level message, such as the filter being too large to add the page's own filters. */
		notice?: string | null;
		/** Filter path of the row to show when the panel opens. */
		focus?: Path | null;
		onchange: (query: Query, options: { debounce: boolean }) => void;
	} = $props();

	// The props are read through closures so the state follows them.
	const builder = new BuilderState(
		untrack(() => query),
		() => catalogue,
		(next, options) => onchange(next, options)
	);
	let announcement = $state('');
	const sortLabelId = $props.id();
	let contentEl = $state<HTMLElement | null>(null);

	// Follow the URL when it changes from elsewhere (Back, a chip removed on the page).
	$effect(() => {
		const current = query;
		untrack(() => builder.sync(current));
	});

	const shown = $derived(builder.shown);
	const draft = $derived(builder.draft);
	const applied = $derived(applyDraft(shown, catalogue));
	const numbers = $derived(conditionNumbers(shown));

	function toDraftKey(appliedPath: Path | null): string | null {
		if (!appliedPath) return null;
		const key = pathKey(appliedPath);
		const path = draftPathFor(applied.toApplied, key);
		if (path) return pathKey(path);
		// A row the server refused may not be applied locally; until edited, the draft is the URL's tree.
		return numbers.has(key) ? key : null;
	}

	const warnedDraft = $derived(
		new Set(
			[...warned]
				.map((key) => toDraftKey(key === '' ? [] : key.split('.').map(Number)))
				.filter((key): key is string => key !== null)
		)
	);
	const errorKey = $derived(toDraftKey(error?.path ?? null));
	const errorText = $derived.by(() => {
		if (!error) return null;
		const n = errorKey ? numbers.get(errorKey) : undefined;
		return n ? `Condition ${n}: ${error.message}` : error.message;
	});

	async function focusRow(key: string | null) {
		await tick();
		const target =
			(key && contentEl?.querySelector<HTMLElement>(`[data-row-key="${key}"] select`)) ||
			contentEl?.querySelector<HTMLElement>('[data-row-key] select') ||
			contentEl?.querySelector<HTMLElement>('[data-add-condition]');
		target?.focus();
		target?.scrollIntoView({ block: 'nearest' });
	}

	const view: BuilderView = $derived({
		catalogue,
		numbers,
		warned: warnedDraft,
		error: errorKey && error ? { key: errorKey, message: error.message } : null,
		canAddCondition: canAddCondition(shown),
		canAddGroup: (groupPath: Path) => canAddGroup(shown, groupPath),
		update(path: Path, condition: Condition, options?: { debounce?: boolean }) {
			builder.update(path, condition, options?.debounce ?? false);
		},
		remove(path: Path) {
			const n = builder.remove(path);
			announcement = n === undefined ? 'Group removed.' : `Condition ${n} removed.`;
			void focusRow(pathKey(path));
		},
		addCondition(groupPath: Path) {
			const at = builder.addCondition(groupPath);
			if (!at) return;
			announcement = `Condition ${conditionNumbers(builder.shown).get(pathKey(at)) ?? ''} added.`;
			void focusRow(pathKey(at));
		},
		addGroup(groupPath: Path) {
			const at = builder.addGroup(groupPath);
			if (!at) return;
			announcement = 'Group added. It matches any of its conditions.';
			void focusRow(pathKey(at));
		},
		setGroupOp(path: Path, op: 'and' | 'or') {
			builder.setGroupOp(path, op);
		}
	});

	function clearAll() {
		builder.clear();
		announcement = 'All conditions removed.';
		void focusRow('0');
	}

	const sortChoice = $derived(sortValue(draft.sort));
	const sortDir = $derived(draft.sort[0]?.dir ?? 'asc');
	const sortGroups = $derived(groupByType(catalogue, sortableFields(catalogue)));
	const sortIsKnown = $derived(
		!catalogue.loaded ||
			!sortChoice.startsWith('field:') ||
			sortGroups.some((g) => g.fields.some((f) => fieldSubject(f.type, f.key) === sortChoice))
	);
	const staleSort = $derived(sortIsKnown ? null : parseFieldSubject(sortChoice));

	function onOpenAutoFocus(event: Event) {
		const appliedKey = focus ? pathKey(focus) : null;
		const key = appliedKey !== null ? toDraftKey(focus) : null;
		const blankOnly = numbers.size === 1 && !applied.query.where;
		const target = key ?? (blankOnly ? '0' : null);
		if (target === null) return;
		event.preventDefault();
		void focusRow(target);
	}
</script>

<ResponsiveDialog.Root bind:open>
	<ResponsiveDialog.Content
		title="Filters"
		bind:ref={contentEl}
		{onOpenAutoFocus}
		class="flex flex-col pb-0 max-sm:h-dvh max-sm:max-h-dvh max-sm:rounded-none max-sm:border-t-0 sm:max-h-[85dvh] sm:max-w-2xl"
	>
		<ResponsiveDialog.Description>
			Show only the items that match. Changes apply as you go.
		</ResponsiveDialog.Description>

		<div class="mt-4 flex flex-1 flex-col gap-4">
			{#if errorText}
				<Alert.Root variant="destructive">
					<TriangleAlert />
					<Alert.Title>This filter can't be used</Alert.Title>
					<Alert.Description>{errorText}</Alert.Description>
				</Alert.Root>
			{/if}
			{#if notice}
				<Alert.Root>
					<TriangleAlert />
					<Alert.Description>{notice}</Alert.Description>
				</Alert.Root>
			{/if}

			{#if shown.where}
				<QueryGroup group={shown.where} path={[]} {view} />
			{/if}

			<div class="flex flex-col gap-2 border-t pt-4">
				<span class="text-sm font-medium" id={sortLabelId}>Sort by</span>
				<div class="flex flex-wrap gap-2" role="group" aria-labelledby={sortLabelId}>
					<NativeSelect.Root
						class="min-w-0 flex-1 basis-48 [&_select]:h-9"
						aria-label="Sort by"
						value={sortChoice}
						onchange={(e) => builder.setSort(sortFromValue(e.currentTarget.value, sortDir))}
					>
						<NativeSelect.Option value="default">Order added (default)</NativeSelect.Option>
						<NativeSelect.Option value="name">Name</NativeSelect.Option>
						<NativeSelect.Option value="created">Date added</NativeSelect.Option>
						<NativeSelect.Option value="updated">Date changed</NativeSelect.Option>
						{#if staleSort}
							<NativeSelect.Option value={sortChoice}>
								{fieldReferenceLabel(catalogue, staleSort.type, staleSort.key)}{findField(
									catalogue,
									staleSort.type,
									staleSort.key
								)?.archived
									? ' (archived)'
									: ' (no longer exists)'}
							</NativeSelect.Option>
						{/if}
						{#each sortGroups as group (group.slug)}
							<NativeSelect.OptGroup label={group.label}>
								{#each group.fields as f (f.key)}
									<NativeSelect.Option value={fieldSubject(f.type, f.key)}>
										{group.label} › {f.label}
									</NativeSelect.Option>
								{/each}
							</NativeSelect.OptGroup>
						{/each}
					</NativeSelect.Root>
					<NativeSelect.Root
						class="min-w-0 basis-36 [&_select]:h-9"
						aria-label="Sort direction"
						disabled={sortChoice === 'default'}
						value={sortDir}
						onchange={(e) =>
							builder.setSort(
								sortFromValue(sortChoice, e.currentTarget.value === 'desc' ? 'desc' : 'asc')
							)}
					>
						<NativeSelect.Option value="asc">Ascending</NativeSelect.Option>
						<NativeSelect.Option value="desc">Descending</NativeSelect.Option>
					</NativeSelect.Root>
				</div>
				{#if sortWarned || staleSort}
					<p class="flex items-start gap-1.5 text-sm">
						<TriangleAlert class="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
						<span>{STALE_SORT_MESSAGE}</span>
					</p>
				{/if}
			</div>
		</div>

		<p class="sr-only" role="status" aria-live="polite">{announcement}</p>

		<div
			class="sticky bottom-0 -mx-6 mt-6 flex items-center justify-between gap-2 border-t bg-background px-6 py-4"
		>
			<Button variant="ghost" onclick={clearAll}>Clear all</Button>
			<Button onclick={() => (open = false)}>Done</Button>
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
