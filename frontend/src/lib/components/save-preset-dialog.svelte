<script lang="ts">
	import { Dialog } from 'bits-ui';
	import { X } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { createPreset } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import type { ChoiceListDefinition, FieldDefinition, Preset } from '$lib/presets';

	let {
		open,
		kind,
		definition,
		onOpenChange,
		onSaved
	}: {
		open: boolean;
		kind: 'field' | 'choice_list';
		definition: FieldDefinition | ChoiceListDefinition;
		onOpenChange: (open: boolean) => void;
		onSaved: (preset: Preset) => void;
	} = $props();

	let label = $state('');
	let description = $state('');
	let saving = $state(false);
	let labelInput = $state<HTMLInputElement | null>(null);

	$effect(() => {
		if (open) labelInput?.focus();
	});

	function reset() {
		label = '';
		description = '';
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		const result = await createPreset({
			body: { kind, label, description: description || null, definition }
		});
		saving = false;
		if (result.error || !result.data) {
			toast.error("Couldn't save", { description: errorMessage(result.error) });
			return;
		}
		toast.success('Saved for reuse');
		onSaved(result.data as unknown as Preset);
		reset();
		onOpenChange(false);
	}
</script>

<Dialog.Root {open} {onOpenChange}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
		<Dialog.Content
			aria-label="Save for reuse"
			class="fixed right-0 bottom-0 left-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-2xl border-t bg-background p-6 shadow-xl sm:inset-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-full sm:max-w-md sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border"
		>
			<div class="mx-auto mb-5 h-1.5 w-12 rounded-full bg-muted sm:hidden"></div>
			<div class="flex items-center justify-between">
				<Dialog.Title class="text-lg font-semibold">Save for reuse</Dialog.Title>
				<button
					type="button"
					onclick={() => onOpenChange(false)}
					class="rounded-md p-1 text-muted-foreground hover:text-foreground"
					aria-label="Close"
				>
					<X class="size-4" />
				</button>
			</div>
			<form class="mt-4 space-y-4" onsubmit={handleSubmit}>
				<div class="space-y-1.5">
					<Label for="preset-label">Label</Label>
					<Input id="preset-label" bind:value={label} bind:ref={labelInput} required />
				</div>
				<div class="space-y-1.5">
					<Label for="preset-description">Description</Label>
					<Textarea
						id="preset-description"
						bind:value={description}
						placeholder="Optional description"
					/>
				</div>
				<div class="flex justify-end gap-2">
					<Button type="button" variant="outline" onclick={() => onOpenChange(false)}>
						Cancel
					</Button>
					<Button type="submit" disabled={saving || label.trim() === ''}>
						{saving ? 'Saving…' : 'Save'}
					</Button>
				</div>
			</form>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
