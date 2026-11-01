<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';

	const MAX_SLUG_LENGTH = 120;

	let {
		value = $bindable(),
		error = null,
		regenerating = false,
		disabled = false,
		nameUnsaved = false,
		onRegenerate
	}: {
		value: string;
		error?: string | null;
		regenerating?: boolean;
		/** Another save is in flight. */
		disabled?: boolean;
		/** The name was edited but not saved, so the server would rebuild from the old one. */
		nameUnsaved?: boolean;
		onRegenerate: () => void;
	} = $props();
</script>

<div class="space-y-1.5">
	<Label for="edit-collection-slug">Slug</Label>
	<div class="flex flex-wrap gap-2">
		<Input
			id="edit-collection-slug"
			bind:value
			maxlength={MAX_SLUG_LENGTH}
			class="w-auto min-w-48 flex-1"
			autocomplete="off"
			autocapitalize="off"
			spellcheck={false}
			aria-invalid={error !== null}
			aria-describedby={error
				? 'edit-collection-slug-help edit-collection-slug-error'
				: 'edit-collection-slug-help'}
		/>
		<Button
			type="button"
			variant="outline"
			disabled={regenerating || disabled || nameUnsaved}
			onclick={onRegenerate}
		>
			{regenerating ? 'Regenerating…' : 'Regenerate from name'}
		</Button>
	</div>
	<p id="edit-collection-slug-help" class="text-sm text-muted-foreground">
		Changing the slug changes this collection's link. Links that use the old slug will stop working.
		{#if nameUnsaved}Save the new name first to regenerate the slug from it.{/if}
	</p>
	{#if error}
		<p id="edit-collection-slug-error" class="text-sm text-destructive">{error}</p>
	{/if}
</div>
