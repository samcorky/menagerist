<script lang="ts">
	import { versionController } from '$lib/version.svelte.js';
	import { Alert, AlertTitle, AlertDescription } from '$lib/components/ui/alert/index.js';
	import { TriangleAlert } from '@lucide/svelte';
</script>

{#if versionController.mismatch}
	<Alert variant="destructive" class="rounded-none border-x-0 border-t-0">
		<TriangleAlert />
		<AlertTitle>Version mismatch</AlertTitle>
		<AlertDescription>
			This page was built against backend v{versionController.mismatch.frontend} but is talking to v{versionController
				.mismatch.backend}. Redeploy with matching image tags to resolve.
		</AlertDescription>
	</Alert>
{/if}
