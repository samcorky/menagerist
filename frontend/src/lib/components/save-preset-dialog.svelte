<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createPreset } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
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

<ResponsiveDialog.Root {open} {onOpenChange}>
	<ResponsiveDialog.Content title="Save for reuse" size="md">
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
				<Button type="button" variant="outline" onclick={() => onOpenChange(false)}>Cancel</Button>
				<Button type="submit" disabled={saving || label.trim() === ''}>
					{saving ? 'Saving…' : 'Save'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
