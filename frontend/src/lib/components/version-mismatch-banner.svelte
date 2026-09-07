<script lang="ts">
	import { versionController } from '$lib/version.svelte.js';
	import { Alert, AlertTitle, AlertDescription } from '$lib/components/ui/alert/index.js';
	import { TriangleAlert } from '@lucide/svelte';
</script>

{#if versionController.mismatch}
	{@const { frontend, backend } = versionController.mismatch}
	<Alert variant="destructive" class="rounded-none border-x-0 border-t-0">
		<TriangleAlert />
		<AlertTitle>Version mismatch</AlertTitle>
		<AlertDescription class="flex items-center gap-3">
			<span>
				This page was built against backend v{frontend} but is talking to v{backend}.
				{#if versionController.backendNewer}
					A newer version of the frontend may be available.
				{:else}
					Redeploy with matching image tags to resolve.
				{/if}
			</span>
			{#if versionController.backendNewer}
				<button
					type="button"
					aria-label="Refresh page to load latest version"
					onclick={() => location.reload()}
					class="hover:bg-destructive-foreground/10 shrink-0 rounded border border-current px-2 py-0.5 text-xs font-medium"
				>
					Refresh
				</button>
			{/if}
		</AlertDescription>
	</Alert>
{/if}
