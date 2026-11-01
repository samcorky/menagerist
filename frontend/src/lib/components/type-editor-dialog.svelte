<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Button } from '$lib/components/ui/button/index.js';

	// The create/edit shell for item types and relationship types: a large dialog around a form.
	// `value` is everything the person can change; once it differs from what it was when the dialog
	// opened, closing asks before throwing the edits away.
	let {
		open,
		title,
		submitLabel,
		busyLabel = 'Saving…',
		busy = false,
		value,
		onSubmit,
		onClose,
		children
	}: {
		open: boolean;
		title: string;
		submitLabel: string;
		busyLabel?: string;
		busy?: boolean;
		value: unknown;
		onSubmit: (event: SubmitEvent) => void;
		onClose: () => void;
		children?: Snippet;
	} = $props();

	let snapshot = $state('');
	// The dialog primitive closes its own copy of `open` when dismissed; this mirror lets a dismissal
	// be refused (an unsaved editor) by putting it back to what the page says.
	let dialogOpen = $derived(open);
	let confirming = $state(false);
	let formEl = $state<HTMLFormElement | null>(null);

	const current = $derived(JSON.stringify(value));
	const dirty = $derived(open && current !== snapshot);

	// What the form held when it opened is the baseline for "changed".
	$effect(() => {
		if (open) {
			snapshot = untrack(() => current);
			confirming = false;
		}
	});

	// Focus goes back into the form first: hiding the panel removes the button that holds it, and
	// a dialog that sees focus drop to the page treats that as the person leaving.
	function keepEditing() {
		formEl?.querySelector<HTMLElement>('input, textarea')?.focus();
		confirming = false;
	}

	function onDialogChange(next: boolean) {
		if (next) return;
		requestClose();
		queueMicrotask(() => (dialogOpen = open));
	}

	function requestClose() {
		if (busy) return;
		if (dirty) confirming = true;
		else onClose();
	}
</script>

<ResponsiveDialog.Root bind:open={dialogOpen} onOpenChange={onDialogChange}>
	<ResponsiveDialog.Content {title} size="xl">
		<form bind:this={formEl} class="mt-3 space-y-4" onsubmit={onSubmit}>
			{@render children?.()}
			{#if confirming}
				<div
					role="group"
					aria-label="Discard changes?"
					class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-3"
				>
					<div>
						<p class="font-medium">Discard changes?</p>
						<p class="text-sm text-muted-foreground">What you changed here has not been saved.</p>
					</div>
					<div class="flex gap-2">
						<Button
							type="button"
							variant="outline"
							class="pointer-coarse:h-11"
							autofocus
							onclick={keepEditing}
						>
							Keep editing
						</Button>
						<Button
							type="button"
							variant="destructive"
							class="pointer-coarse:h-11"
							onclick={() => {
								confirming = false;
								onClose();
							}}
						>
							Discard
						</Button>
					</div>
				</div>
			{:else}
				<div class="flex justify-end gap-2">
					<Button
						type="button"
						variant="ghost"
						class="pointer-coarse:h-11"
						disabled={busy}
						onclick={requestClose}
					>
						Cancel
					</Button>
					<Button type="submit" class="pointer-coarse:h-11" disabled={busy}>
						{busy ? busyLabel : submitLabel}
					</Button>
				</div>
			{/if}
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
