<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { updatePreset, type PresetResponse } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';

	let {
		preset,
		open,
		onOpenChange,
		onsaved
	}: {
		preset: PresetResponse;
		open: boolean;
		onOpenChange: (open: boolean) => void;
		onsaved: (preset: PresetResponse) => void;
	} = $props();

	/** Reads the stored options defensively, keeping only strings. */
	function storedOptions(definition: PresetResponse['definition']): string[] {
		const options: unknown = definition.options;
		return Array.isArray(options) ? options.filter((o): o is string => typeof o === 'string') : [];
	}

	// The parent keys this component per edit session, so the form starts from the preset.
	function initialForm(source: PresetResponse) {
		return {
			label: source.label,
			description: source.description ?? '',
			optionsText: storedOptions(source.definition).join('\n')
		};
	}

	// svelte-ignore state_referenced_locally
	let form = $state(initialForm(preset));
	let labelError = $state('');
	let optionsError = $state('');
	let saving = $state(false);

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		const trimmedLabel = form.label.trim();
		const options = form.optionsText
			.split(/\r?\n/)
			.map((line) => line.trim())
			.filter((line) => line !== '');

		labelError = trimmedLabel === '' ? 'Enter a label.' : '';
		optionsError = options.length === 0 ? 'Add at least one option, one per line.' : '';
		if (labelError || optionsError) return;

		saving = true;
		const result = await updatePreset({
			path: { preset_id: preset.id },
			body: {
				label: trimmedLabel,
				description: form.description.trim() || null,
				definition: { options }
			}
		});
		saving = false;
		if (result.error || !result.data) {
			toast.error("Couldn't save list", { description: errorMessage(result.error) });
			return;
		}
		toast.success('List saved');
		onsaved(result.data);
		onOpenChange(false);
	}
</script>

<ResponsiveDialog.Root {open} {onOpenChange}>
	<ResponsiveDialog.Content title="Edit list" size="md">
		<form class="mt-4 space-y-4" onsubmit={handleSubmit} novalidate>
			<div class="space-y-1.5">
				<Label for="edit-list-label">Label</Label>
				<Input
					id="edit-list-label"
					bind:value={form.label}
					required
					aria-invalid={labelError !== '' || undefined}
					aria-describedby={labelError ? 'edit-list-label-error' : undefined}
				/>
				{#if labelError}
					<p id="edit-list-label-error" class="text-sm text-destructive">{labelError}</p>
				{/if}
			</div>
			<div class="space-y-1.5">
				<Label for="edit-list-description">Description</Label>
				<Input id="edit-list-description" bind:value={form.description} placeholder="Optional" />
			</div>
			<div class="space-y-1.5">
				<Label for="edit-list-options">Options</Label>
				<Textarea
					id="edit-list-options"
					bind:value={form.optionsText}
					placeholder="One option per line"
					aria-invalid={optionsError !== '' || undefined}
					aria-describedby={optionsError ? 'edit-list-options-error' : undefined}
				/>
				{#if optionsError}
					<p id="edit-list-options-error" class="text-sm text-destructive">{optionsError}</p>
				{/if}
			</div>
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => onOpenChange(false)}>Cancel</Button>
				<Button type="submit" disabled={saving}>
					{saving ? 'Saving…' : 'Save'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
