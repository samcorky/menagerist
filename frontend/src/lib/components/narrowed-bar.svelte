<script lang="ts">
	import { BookmarkPlus } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';

	let {
		text,
		blockReason,
		updating = false,
		onsave,
		onupdate,
		onclear
	}: {
		/** "Narrowed by 2 filters: 3 of 12 items". */
		text: string;
		/** Why the combined conditions cannot be saved; null when they can. */
		blockReason: string | null;
		updating?: boolean;
		onsave: () => void;
		onupdate: () => void;
		onclear: () => void;
	} = $props();

	const reasonId = $props.id();
</script>

<section
	aria-label="Narrowed view"
	class="flex flex-col gap-3 rounded-xl border bg-muted/40 p-3 sm:p-4"
>
	<p class="text-sm font-medium" aria-live="polite" aria-atomic="true">{text}</p>
	<div class="flex flex-wrap items-center gap-2">
		<Button
			variant="outline"
			size="sm"
			class="max-sm:h-11"
			aria-haspopup="dialog"
			disabled={blockReason !== null}
			aria-describedby={blockReason ? reasonId : undefined}
			onclick={onsave}
		>
			<BookmarkPlus />
			Save as new smart collection
		</Button>
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
		<Button variant="ghost" size="sm" class="max-sm:h-11" onclick={onclear}>Clear</Button>
	</div>
	{#if blockReason}
		<p id={reasonId} class="text-sm text-muted-foreground">{blockReason}</p>
	{/if}
</section>
