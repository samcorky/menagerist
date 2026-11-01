<script lang="ts">
	import { BookmarkPlus, Link } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';

	let {
		text,
		blockReason,
		linkedBlockReason = null,
		updating = false,
		onsave,
		onlinked,
		onupdate,
		onclear
	}: {
		/** "Narrowed by 2 filters: 3 of 12 items". */
		text: string;
		/** Why the combined conditions cannot be saved; null when they can. */
		blockReason: string | null;
		/** Why the linked collection cannot be saved; null when it can. */
		linkedBlockReason?: string | null;
		updating?: boolean;
		/** Leave out where the saved conditions cannot be copied (a manual collection). */
		onsave?: () => void;
		onlinked?: () => void;
		onupdate?: () => void;
		onclear: () => void;
	} = $props();

	const id = $props.id();
	const reasonId = `${id}-reason`;
	const linkedReasonId = `${id}-linked-reason`;
	const explainId = `${id}-explain`;
</script>

<section
	aria-label="Narrowed view"
	class="flex flex-col gap-3 rounded-xl border bg-muted/40 p-3 sm:p-4"
>
	<p class="text-sm font-medium" aria-live="polite" aria-atomic="true">{text}</p>
	<div class="flex flex-wrap items-center gap-2">
		{#if onsave}
			<Button
				variant="outline"
				size="sm"
				class="max-sm:h-11"
				aria-haspopup="dialog"
				disabled={blockReason !== null}
				aria-describedby={blockReason ? reasonId : onlinked ? explainId : undefined}
				onclick={onsave}
			>
				<BookmarkPlus />
				Save as new smart collection
			</Button>
		{/if}
		{#if onlinked}
			<Button
				variant="outline"
				size="sm"
				class="max-sm:h-11"
				aria-haspopup="dialog"
				disabled={linkedBlockReason !== null}
				aria-describedby={linkedBlockReason ? linkedReasonId : explainId}
				onclick={onlinked}
			>
				<Link />
				Save as new, linked to this collection
			</Button>
		{/if}
		{#if onupdate}
			<Button
				variant="outline"
				size="sm"
				class="max-sm:h-11"
				aria-haspopup="dialog"
				disabled={blockReason !== null || updating}
				aria-describedby={blockReason ? reasonId : undefined}
				onclick={onupdate}
			>
				Update this collection
			</Button>
		{/if}
		<Button variant="ghost" size="sm" class="max-sm:h-11" onclick={onclear}>Clear</Button>
	</div>
	{#if onlinked}
		<p id={explainId} class="text-sm text-muted-foreground">
			{#if onsave}A new smart collection copies these conditions. A linked one is always the items
				in this collection that match your filters, so it follows this collection as it changes.{:else}A
				linked collection is always the items in this collection that match your filters, so it
				follows this collection as it changes.{/if}
		</p>
	{/if}
	{#if linkedBlockReason}
		<p id={linkedReasonId} class="text-sm text-muted-foreground">{linkedBlockReason}</p>
	{/if}
	{#if blockReason}
		<p id={reasonId} class="text-sm text-muted-foreground">{blockReason}</p>
	{/if}
</section>
