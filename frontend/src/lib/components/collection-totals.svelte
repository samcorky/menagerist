<script lang="ts">
	import { Plus, RotateCcw, SlidersHorizontal, X } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import {
		aggregateNodes,
		updateCollection,
		type CollectionResponse,
		type NodeMeasureResponse
	} from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import IconButton from '$lib/components/icon-button.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import type { Catalogue } from '$lib/query/fields';
	import {
		MAX_TOTALS,
		automaticTotals,
		collectionTotalsQuery,
		describeTotal,
		formatResult,
		functionLabel,
		functionsFor,
		shownTotals,
		totalChoices,
		totalField,
		totalKey,
		type Total,
		type TotalFunction
	} from '$lib/totals';

	let {
		collection,
		catalogue,
		typeSlugs,
		onchange
	}: {
		collection: CollectionResponse;
		catalogue: Catalogue;
		/** The slugs of the item types on the collection, from the type counts. */
		typeSlugs: readonly string[];
		/** The collection as saved after the totals changed. */
		onchange: (collection: CollectionResponse) => void;
	} = $props();

	const chosen = $derived((collection.summary ?? null) as Total[] | null);
	const automatic = $derived(automaticTotals(catalogue, typeSlugs));
	const totals = $derived(shownTotals(chosen, automatic));
	const choices = $derived(totalChoices(catalogue));
	const hasItems = $derived(collection.item_count > 0);

	let editing = $state(false);
	let results = $state<NodeMeasureResponse[] | null>(null);
	let failed = $state(false);
	let saving = $state(false);
	let readSeq = 0;

	// Read the totals again whenever the collection, what it shows or its contents change.
	const readKey = $derived(
		`${collection.id}|${collection.updated_at}|${collection.item_count}|${JSON.stringify(totals.map(totalKey))}`
	);

	$effect(() => {
		void readKey;
		const measures = $state.snapshot(totals);
		const id = collection.id;
		if (measures.length === 0 || !catalogue.loaded) {
			results = null;
			failed = false;
			return;
		}
		void read(id, measures);
	});

	async function read(id: string, measures: Total[]) {
		const seq = ++readSeq;
		const result = await aggregateNodes({
			body: { query: collectionTotalsQuery(id), measures }
		});
		// A newer read has started: this answer is for totals that are no longer shown.
		if (seq !== readSeq) return;
		failed = !result.data;
		results = result.data?.measures ?? null;
	}

	async function save(next: { summary: Total[] } | { reset_summary: true }, done: string) {
		if (saving) return false;
		saving = true;
		const result = await updateCollection({
			path: { collection_id: collection.id },
			body: next
		});
		saving = false;
		if (result.error || !result.data) {
			if (result.response?.status === 412) {
				toast.error('This collection was changed elsewhere. Reload it and try again.');
			} else {
				const { title, description } = networkAwareError(result);
				toast.error(title === undefined ? "Couldn't change the totals" : title, { description });
			}
			return false;
		}
		onchange(result.data);
		toast.success(done);
		return true;
	}

	function remove(total: Total) {
		const key = totalKey(total);
		void save({ summary: totals.filter((t) => totalKey(t) !== key) }, 'Total removed');
	}

	function useAutomatic() {
		void save({ reset_summary: true }, 'Showing the automatic totals');
	}

	// Add a total.
	let addOpen = $state(false);
	let fieldValue = $state('');
	let fn = $state<TotalFunction>('sum');
	const addId = $props.id();

	const chosenField = $derived(choices.find((c) => c.value === fieldValue));
	const functions = $derived(chosenField ? functionsFor(chosenField.kind) : []);
	const alreadyShown = $derived(
		chosenField !== undefined &&
			totals.some((t) => totalKey(t) === totalKey({ fn, ...chosenField.field }))
	);
	const full = $derived(totals.length >= MAX_TOTALS);

	function openAdd() {
		fieldValue = choices[0]?.value ?? '';
		fn = functionsFor(choices[0]?.kind ?? '')[0] ?? 'sum';
		addOpen = true;
	}

	function pickField(value: string) {
		fieldValue = value;
		const options = functionsFor(choices.find((c) => c.value === value)?.kind ?? '');
		if (!options.includes(fn)) fn = options[0] ?? 'sum';
	}

	async function add(event: SubmitEvent) {
		event.preventDefault();
		if (!chosenField || alreadyShown || full) return;
		const added: Total = { fn, ...chosenField.field };
		if (await save({ summary: [...totals, added] }, 'Total added')) addOpen = false;
	}

	const rows = $derived(
		totals.map((total, index) => {
			const field = totalField(total, catalogue);
			return {
				total,
				label: describeTotal(total, catalogue),
				values: results?.[index] ? formatResult(results[index], field) : null
			};
		})
	);
</script>

{#if hasItems && (totals.length > 0 || choices.length > 0)}
	<section aria-label="Totals" class="mt-3 flex flex-col gap-2">
		<div class="flex flex-wrap items-start gap-x-8 gap-y-3">
			{#each rows as row (totalKey(row.total))}
				<div class="flex min-w-24 items-start gap-1">
					<div>
						<p class="text-xs text-muted-foreground">{row.label}</p>
						{#if row.values}
							<p class="flex flex-wrap gap-x-2 text-lg font-semibold tabular-nums">
								{#each row.values as value, i (value.currency ?? i)}
									{#if i > 0}<span class="text-muted-foreground" aria-hidden="true">·</span>{/if}
									<span>{value.text}</span>
								{/each}
							</p>
						{:else if failed}
							<p class="text-lg text-muted-foreground">–</p>
						{:else}
							<p class="h-7 w-16 animate-pulse rounded bg-muted" aria-hidden="true"></p>
						{/if}
					</div>
					{#if editing}
						<IconButton
							label="Remove {row.label}"
							labelOnTouch={false}
							disabled={saving}
							onclick={() => remove(row.total)}
						>
							<X />
						</IconButton>
					{/if}
				</div>
			{/each}
			<div class="flex flex-wrap items-center gap-1 self-center">
				{#if editing}
					{#if choices.length > 0 && !full}
						<Button variant="outline" size="sm" disabled={saving} onclick={openAdd}>
							<Plus /> Add a total
						</Button>
					{/if}
					{#if chosen !== null}
						<Button variant="ghost" size="sm" disabled={saving} onclick={useAutomatic}>
							<RotateCcw /> Use automatic totals
						</Button>
					{/if}
					<Button variant="ghost" size="sm" onclick={() => (editing = false)}>Done</Button>
				{:else}
					<IconButton
						label="Edit totals"
						labelOnTouch={false}
						aria-expanded={false}
						onclick={() => (editing = true)}
					>
						<SlidersHorizontal />
					</IconButton>
				{/if}
			</div>
		</div>
		{#if failed}
			<p class="text-sm text-muted-foreground">
				Couldn't work out the totals.
				<Button
					variant="link"
					class="h-auto p-0"
					onclick={() => read(collection.id, $state.snapshot(totals))}
				>
					Try again
				</Button>
			</p>
		{/if}
	</section>
{/if}

<ResponsiveDialog.Root bind:open={addOpen}>
	<ResponsiveDialog.Content title="Add a total" size="md">
		<form class="mt-4 space-y-4" onsubmit={add}>
			<div class="space-y-1.5">
				<Label for="{addId}-field">Field</Label>
				<NativeSelect.Root
					id="{addId}-field"
					value={fieldValue}
					onchange={(e) => pickField(e.currentTarget.value)}
				>
					{#each choices as choice (choice.value)}
						<NativeSelect.Option value={choice.value}>{choice.label}</NativeSelect.Option>
					{/each}
				</NativeSelect.Root>
			</div>
			<div class="space-y-1.5">
				<Label for="{addId}-fn">Show the</Label>
				<NativeSelect.Root
					id="{addId}-fn"
					value={fn}
					onchange={(e) => (fn = e.currentTarget.value as TotalFunction)}
				>
					{#each functions as option (option)}
						<NativeSelect.Option value={option}>
							{functionLabel(option, chosenField?.kind ?? null)}
						</NativeSelect.Option>
					{/each}
				</NativeSelect.Root>
			</div>
			{#if alreadyShown}
				<p class="text-sm text-muted-foreground">That total is already shown.</p>
			{/if}
			<p class="text-sm text-muted-foreground">
				Money is never converted: each currency gets its own total.
			</p>
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => (addOpen = false)}>Cancel</Button>
				<Button type="submit" disabled={saving || alreadyShown || !chosenField}>
					{saving ? 'Adding…' : 'Add total'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
