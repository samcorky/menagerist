<script lang="ts">
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import type { Snippet } from 'svelte';

	let {
		open,
		title,
		description,
		confirmLabel = 'Confirm',
		busyLabel = 'Working…',
		cancelLabel = 'Cancel',
		destructive = true,
		busy = false,
		onOpenChange,
		onConfirm
	}: {
		open: boolean;
		title: string;
		description?: string | Snippet;
		confirmLabel?: string;
		busyLabel?: string;
		cancelLabel?: string;
		destructive?: boolean;
		busy?: boolean;
		onOpenChange: (open: boolean) => void;
		onConfirm: () => void;
	} = $props();
</script>

<ResponsiveDialog.Root {open} {onOpenChange}>
	<ResponsiveDialog.Content {title} size="sm">
		{#if description}
			<ResponsiveDialog.Description>
				{#if typeof description === 'string'}
					{description}
				{:else}
					{@render description()}
				{/if}
			</ResponsiveDialog.Description>
		{/if}
		<div class="mt-4 flex justify-end gap-2">
			<Button type="button" variant="outline" disabled={busy} onclick={() => onOpenChange(false)}>
				{cancelLabel}
			</Button>
			<Button
				type="button"
				variant={destructive ? 'destructive' : 'default'}
				disabled={busy}
				onclick={onConfirm}
			>
				{busy ? busyLabel : confirmLabel}
			</Button>
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
