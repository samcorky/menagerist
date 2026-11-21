<script lang="ts">
	import { resolve } from '$app/paths';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Item from '$lib/components/ui/item/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import { fetchContents, mayHaveMore, pickChoice, type ReachChoice } from '$lib/item-reach';
	import type { NodeContentsEntryResponse } from '$lib/api/client';

	let {
		nodeId,
		choices,
		refreshKey
	}: {
		nodeId: string;
		/** The relationships through which this item holds others, worded as "Contains". */
		choices: ReachChoice[];
		/** Changes when the item's connections do, to fetch again. */
		refreshKey: unknown;
	} = $props();

	let picked = $state('');
	const choice = $derived(pickChoice(choices, picked));
	let entries = $state<NodeContentsEntryResponse[]>([]);
	let more = $state(false);
	let loading = $state(false);
	let failed = $state(false);

	// Only the latest request may land, so switching relationship quickly cannot show stale rows.
	let requestId = 0;

	async function load(slug: string, after?: string) {
		const mine = ++requestId;
		loading = true;
		const page = await fetchContents(nodeId, slug, after);
		if (mine !== requestId) return;
		loading = false;
		failed = page === null;
		if (page === null) return;
		entries = after ? [...entries, ...page] : page;
		more = mayHaveMore(page);
	}

	$effect(() => {
		void refreshKey;
		const slug = choice?.slug;
		entries = [];
		more = false;
		if (!slug) return;
		void load(slug);
	});
</script>

{#if choice}
	<Card.Root>
		<Card.Header>
			<Card.Title class="font-heading">
				{#if choices.length > 1}
					<NativeSelect.Root
						class="w-auto [&_select]:h-8"
						aria-label="Show what this item holds by"
						value={choice.slug}
						onchange={(e) => (picked = e.currentTarget.value)}
					>
						{#each choices as c (c.slug)}
							<NativeSelect.Option value={c.slug}>{c.label}</NativeSelect.Option>
						{/each}
					</NativeSelect.Root>
				{:else}
					{choice.label}
				{/if}
			</Card.Title>
		</Card.Header>
		<Card.Content class="space-y-3">
			{#if failed}
				<p role="alert" class="text-sm text-destructive">Could not load what is inside.</p>
				<Button variant="outline" size="sm" onclick={() => void load(choice.slug)}>
					Try again
				</Button>
			{:else if entries.length === 0 && !loading}
				<p class="text-sm text-muted-foreground">Nothing inside yet.</p>
			{:else}
				<ul class="space-y-2" aria-label="Inside this item">
					{#each entries as entry (entry.item.id)}
						<li>
							<Item.Root variant="outline">
								<Item.Content class="text-sm">
									<a
										href={resolve('/items/[id]', { id: entry.item.id })}
										class="min-w-0 break-words underline"
									>
										{entry.item.name}
									</a>
									{#if entry.depth > 1}
										<span class="text-xs text-muted-foreground">{entry.depth} levels in</span>
									{/if}
								</Item.Content>
							</Item.Root>
						</li>
					{/each}
				</ul>
				{#if more}
					<Button
						variant="outline"
						size="sm"
						disabled={loading}
						onclick={() => void load(choice.slug, entries.at(-1)?.item.id)}
					>
						{loading ? 'Loading…' : 'Show more'}
					</Button>
				{/if}
			{/if}
		</Card.Content>
	</Card.Root>
{/if}
