<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { tagNodes } from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { itemCount, parseTagInput, unknownItemIds } from '$lib/bulk-actions';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';

	let {
		open,
		ids,
		onOpenChange,
		ondone,
		onmissing
	}: {
		open: boolean;
		ids: string[];
		onOpenChange: (open: boolean) => void;
		/** The tags were changed; the page reloads its list. */
		ondone: () => void;
		/** The server named items that no longer exist, so the page can drop them. */
		onmissing: (ids: string[]) => void;
	} = $props();

	let add = $state('');
	let remove = $state('');
	let sending = $state(false);
	let error = $state<string | null>(null);

	const toAdd = $derived(parseTagInput(add));
	const toRemove = $derived(parseTagInput(remove));

	$effect(() => {
		if (open) {
			add = '';
			remove = '';
			error = null;
		}
	});

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		if (sending || (toAdd.length === 0 && toRemove.length === 0)) return;
		sending = true;
		error = null;
		const result = await tagNodes({ body: { ids, add: toAdd, remove: toRemove } });
		sending = false;
		if (result.error || !result.data) {
			if (!result.response) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
				return;
			}
			const detail = errorMessage(result.error);
			error = detail;
			const missing = unknownItemIds(detail);
			if (missing.length > 0) onmissing(missing);
			return;
		}
		toast.success(`Tagged ${itemCount(ids.length)}`);
		ondone();
		onOpenChange(false);
	}
</script>

<ResponsiveDialog.Root {open} onOpenChange={(value) => !sending && onOpenChange(value)}>
	<ResponsiveDialog.Content title="Tag {itemCount(ids.length)}">
		<form class="mt-4 space-y-4" onsubmit={submit}>
			<div class="space-y-1.5">
				<Label for="bulk-tags-add">Add tags</Label>
				<Input id="bulk-tags-add" bind:value={add} placeholder="to-watch, favourite" />
			</div>
			<div class="space-y-1.5">
				<Label for="bulk-tags-remove">Remove tags</Label>
				<Input id="bulk-tags-remove" bind:value={remove} placeholder="watched" />
			</div>
			<p class="text-xs text-muted-foreground">Separate tags with commas.</p>
			{#if error}
				<p role="alert" class="text-sm text-destructive">{error}</p>
			{/if}
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => onOpenChange(false)}>Cancel</Button>
				<Button type="submit" disabled={sending || (toAdd.length === 0 && toRemove.length === 0)}>
					{sending ? 'Saving…' : 'Apply'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
