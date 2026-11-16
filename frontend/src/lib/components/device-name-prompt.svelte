<script lang="ts">
	import type { DeviceNameSuggestionResponse } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	let {
		label,
		suggestions,
		onname,
		onadopt,
		ondismiss
	}: {
		/** The generated label, the starting text for a new name. */
		label: string;
		/** Older devices of the same kind of browser whose names could be reused. */
		suggestions: DeviceNameSuggestionResponse[];
		/** Resolves true when the name was saved. */
		onname: (name: string) => Promise<boolean>;
		/** Resolves true when the name was taken; the older device is then removed. */
		onadopt: (deviceId: string) => Promise<boolean>;
		ondismiss: () => void;
	} = $props();

	let draft = $state('');
	let busy = $state<string | null>(null);

	// Start from the generated label, so a one-tap save is possible.
	$effect.pre(() => {
		if (draft === '') draft = label;
	});

	async function save(event: SubmitEvent) {
		event.preventDefault();
		const name = draft.trim();
		if (!name || busy) return;
		busy = 'new';
		await onname(name);
		busy = null;
	}

	async function adopt(id: string) {
		if (busy) return;
		busy = id;
		await onadopt(id);
		busy = null;
	}
</script>

<div class="flex flex-col gap-4" data-testid="device-name-prompt">
	{#if suggestions.length > 0}
		<div class="space-y-2">
			<p class="text-sm">Is this one of your earlier devices? Reuse its name:</p>
			<ul class="flex flex-wrap gap-2">
				{#each suggestions as suggestion (suggestion.id)}
					<li>
						<Button
							type="button"
							variant="outline"
							class="pointer-coarse:h-11"
							disabled={busy !== null}
							onclick={() => adopt(suggestion.id)}
						>
							{#if busy === suggestion.id}<Spinner class="size-4" />{/if}
							{suggestion.name}
						</Button>
					</li>
				{/each}
			</ul>
			<p class="text-xs text-muted-foreground">
				Reusing a name signs out and forgets the earlier device.
			</p>
		</div>
	{/if}

	<form class="flex flex-col gap-2 sm:flex-row sm:items-end" onsubmit={save}>
		<div class="flex-1 space-y-1.5">
			<Label for="new-device-name">
				{suggestions.length > 0 ? 'Or choose a new name' : 'Device name'}
			</Label>
			<Input id="new-device-name" bind:value={draft} maxlength={60} />
		</div>
		<div class="flex gap-2">
			<Button type="submit" class="pointer-coarse:h-11" disabled={busy !== null || !draft.trim()}>
				{#if busy === 'new'}<Spinner class="size-4" />{/if}
				Save name
			</Button>
			<Button
				type="button"
				variant="ghost"
				class="pointer-coarse:h-11"
				disabled={busy !== null}
				onclick={ondismiss}
			>
				Not now
			</Button>
		</div>
	</form>
</div>
