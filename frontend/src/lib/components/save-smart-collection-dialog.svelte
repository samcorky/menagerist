<script lang="ts">
	import { tick } from 'svelte';
	import type { CollectionResponse } from '$lib/api/client';
	import { MAX_COLLECTION_NAME_LENGTH, validateCollectionName } from '$lib/collections';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import type { Query } from '$lib/query/types';
	import {
		SmartCollectionError,
		describeSaveError,
		saveSmartCollection
	} from '$lib/smart-collections';

	let {
		open = $bindable(false),
		query,
		title = 'Save as smart collection',
		intro = 'Items that match the current conditions are added automatically.',
		onsaved
	}: {
		open?: boolean;
		/** The search to save. */
		query: Query;
		title?: string;
		intro?: string;
		onsaved: (collection: CollectionResponse) => void;
	} = $props();

	let name = $state('');
	let touched = $state(false);
	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let wasOpen = false;
	let nameEl = $state<HTMLInputElement | null>(null);

	const nameHint = $derived(validateCollectionName(name));
	const showNameHint = $derived(touched && nameHint !== null);
	const nameId = $props.id();

	// Start from a blank form each time the dialog opens.
	$effect(() => {
		if (open && !wasOpen) {
			name = '';
			touched = false;
			saveError = null;
		}
		wasOpen = open;
	});

	function handleOpenChange(next: boolean) {
		if (!next && saving) return;
		open = next;
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		touched = true;
		if (nameHint !== null || saving) return;
		saving = true;
		saveError = null;
		try {
			const collection = await saveSmartCollection(name, query);
			open = false;
			onsaved(collection);
		} catch (e) {
			saveError = e instanceof SmartCollectionError ? describeSaveError(e, query) : null;
			await tick();
			nameEl?.focus();
		} finally {
			saving = false;
		}
	}
</script>

<ResponsiveDialog.Root {open} onOpenChange={handleOpenChange}>
	<ResponsiveDialog.Content {title} size="md">
		<form class="mt-4 space-y-4" onsubmit={handleSubmit} novalidate>
			<p class="text-sm text-muted-foreground">
				{intro}
			</p>
			<div class="space-y-1.5">
				<Label for="{nameId}-name">Name</Label>
				<Input
					id="{nameId}-name"
					bind:ref={nameEl}
					bind:value={name}
					maxlength={MAX_COLLECTION_NAME_LENGTH}
					required
					autocomplete="off"
					aria-invalid={showNameHint}
					aria-describedby={showNameHint ? `${nameId}-hint` : undefined}
					onblur={() => (touched = true)}
				/>
				{#if showNameHint}
					<p id="{nameId}-hint" class="text-sm text-destructive">{nameHint}</p>
				{/if}
			</div>
			{#if saveError}
				<p role="alert" class="text-sm text-destructive">{saveError}</p>
			{/if}
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => handleOpenChange(false)}>
					Cancel
				</Button>
				<Button type="submit" disabled={saving}>
					{saving ? 'Saving…' : 'Save smart collection'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
