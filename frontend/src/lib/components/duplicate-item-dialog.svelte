<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { duplicateNode, type NodeResponse } from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import {
		DEFAULT_DUPLICATE_CHOICES,
		defaultCopyName,
		duplicateBody,
		type DuplicateChoices
	} from '$lib/duplicate-item';

	let {
		open,
		node,
		onOpenChange,
		onDuplicated
	}: {
		open: boolean;
		node: Pick<NodeResponse, 'id' | 'name'>;
		onOpenChange: (open: boolean) => void;
		onDuplicated: (copy: NodeResponse) => void;
	} = $props();

	let name = $state('');
	let choices = $state<DuplicateChoices>({ ...DEFAULT_DUPLICATE_CHOICES });
	let saving = $state(false);
	let nameInput = $state<HTMLInputElement | null>(null);

	// Each opening starts from the defaults, with the name selected for quick overtyping.
	$effect(() => {
		if (!open) return;
		name = defaultCopyName(node.name);
		choices = { ...DEFAULT_DUPLICATE_CHOICES };
		nameInput?.focus();
		nameInput?.select();
	});

	const options: { key: keyof DuplicateChoices; label: string; hint: string }[] = [
		{ key: 'connections', label: 'Connections', hint: 'Links to other items' },
		{ key: 'media', label: 'Photos and files', hint: 'Copied, so each item keeps its own' },
		{ key: 'cover', label: 'Cover image', hint: 'Copied from the original' },
		{ key: 'collections', label: 'Collections', hint: 'Added to the same collections' }
	];

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		const result = await duplicateNode({
			path: { node_id: node.id },
			body: duplicateBody(name, choices)
		});
		saving = false;
		if (result.error || !result.data) {
			const { title, description } = networkAwareError(result);
			toast.error(title, { description });
			return;
		}
		onOpenChange(false);
		onDuplicated(result.data);
	}
</script>

<ResponsiveDialog.Root {open} {onOpenChange}>
	<ResponsiveDialog.Content title="Duplicate item" size="md">
		<form class="mt-4 space-y-4" onsubmit={handleSubmit}>
			<div class="space-y-1.5">
				<Label for="duplicate-name">Name</Label>
				<Input id="duplicate-name" bind:value={name} bind:ref={nameInput} required />
				<p class="text-sm text-muted-foreground">
					The copy keeps this item's type, details and tags, and starts with its own history.
				</p>
			</div>
			<fieldset class="space-y-2">
				<legend class="text-sm font-medium">Also copy</legend>
				{#each options as option (option.key)}
					<label class="flex items-start gap-2 text-sm">
						<input
							type="checkbox"
							bind:checked={choices[option.key]}
							class="mt-0.5 h-4 w-4 accent-primary"
						/>
						<span>
							{option.label}
							<span class="block text-muted-foreground">{option.hint}</span>
						</span>
					</label>
				{/each}
			</fieldset>
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => onOpenChange(false)}>Cancel</Button>
				<Button type="submit" disabled={saving || name.trim() === ''}>
					{saving ? 'Duplicating…' : 'Duplicate'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
