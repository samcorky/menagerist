<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Alert from '$lib/components/ui/alert/index.js';

	let {
		notes = [],
		onrestore,
		ondiscard
	}: {
		/** Extra sentences, e.g. what the draft could not keep. */
		notes?: string[];
		onrestore: () => void;
		ondiscard: () => void;
	} = $props();
</script>

<Alert.Root data-testid="draft-restore">
	<Alert.Title>Restore your unsaved changes?</Alert.Title>
	<Alert.Description>
		<p>Your session ended before they were saved.</p>
		{#each notes as note (note)}
			<p>{note}</p>
		{/each}
	</Alert.Description>
	<div class="mt-2 flex flex-wrap gap-2">
		<Button type="button" size="sm" onclick={onrestore}>Restore</Button>
		<Button type="button" size="sm" variant="outline" onclick={ondiscard}>Discard</Button>
	</div>
</Alert.Root>
