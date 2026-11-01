<script lang="ts">
	import { untrack } from 'svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import { ExactCount } from '$lib/exact-count.svelte';
	import { formatTotal } from '$lib/query/items-page';
	import { describeCollectionCount, EXACT_COUNT_ERROR } from '$lib/smart-collections';
	import type { CollectionResponse } from '$lib/api/client';

	let {
		collection,
		ready = true
	}: {
		collection: Pick<
			CollectionResponse,
			'id' | 'kind' | 'definition' | 'item_count' | 'item_count_capped'
		>;
		/** True once the first page of results has loaded; the count waits for it. */
		ready?: boolean;
	} = $props();

	const exact = new ExactCount();
	const scope = $derived(`${collection.id}:${JSON.stringify(collection.definition ?? null)}`);
	const capped = $derived(collection.item_count_capped ?? false);
	const label = $derived(
		exact.count === null ? describeCollectionCount(collection) : formatTotal(exact.count, false)
	);

	$effect(() => {
		const current = scope;
		const isReady = ready;
		const isCapped = capped;
		untrack(() => {
			exact.track(current);
			if (isReady && isCapped) exact.auto(collection.id);
		});
	});

	$effect(() => () => exact.cancel());
</script>

<div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
	<p aria-live="polite" aria-atomic="true">{label}</p>
	{#if exact.loading}
		<Spinner class="size-3" aria-label="Counting the items" />
	{/if}
	{#if exact.failed}
		<p role="alert" class="text-destructive">{EXACT_COUNT_ERROR}</p>
		<Button
			variant="outline"
			size="sm"
			class="h-7 px-2 text-xs"
			onclick={() => exact.retry(collection.id)}
		>
			Count exactly
		</Button>
	{/if}
</div>
