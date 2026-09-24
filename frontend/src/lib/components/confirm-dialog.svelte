<script lang="ts">
	import { Dialog } from 'bits-ui';
	import { X } from '@lucide/svelte';
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

<Dialog.Root {open} {onOpenChange}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
		<Dialog.Content
			aria-label={title}
			class="fixed right-0 bottom-0 left-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-2xl border-t bg-background p-6 shadow-xl sm:inset-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-full sm:max-w-sm sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border"
		>
			<div class="mx-auto mb-5 h-1.5 w-12 rounded-full bg-muted sm:hidden"></div>
			<div class="flex items-center justify-between">
				<Dialog.Title class="text-lg font-semibold">{title}</Dialog.Title>
				<button
					type="button"
					onclick={() => onOpenChange(false)}
					class="relative rounded-md p-1 text-muted-foreground after:absolute after:-inset-2 after:content-[''] hover:text-foreground"
					aria-label="Close"
				>
					<X class="size-4" />
				</button>
			</div>
			{#if description}
				<Dialog.Description class="mt-1 text-sm text-muted-foreground">
					{#if typeof description === 'string'}
						{description}
					{:else}
						{@render description()}
					{/if}
				</Dialog.Description>
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
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
