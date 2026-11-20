<script lang="ts">
	import { Download, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import InstallSteps from '$lib/components/install-steps.svelte';
	import { installPrompt } from '$lib/install-prompt.svelte';
	import { readFlag, writeFlag } from '$lib/remembered';

	const DISMISSED_KEY = 'install-card-dismissed';

	// Installing is a per-device choice, so the dismissal is too.
	let dismissed = $state(readFlag(DISMISSED_KEY, false));
	let stepsOpen = $state(false);

	function dismiss() {
		writeFlag(DISMISSED_KEY, true);
		dismissed = true;
	}
</script>

{#if installPrompt.available && !dismissed}
	<div
		data-testid="install-card"
		class="flex flex-col gap-3 rounded-xl border bg-muted/30 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
	>
		<div class="min-w-0">
			<p class="font-medium">Install the app on this device</p>
			<p class="text-muted-foreground">Open it from your home screen or dock, in its own window.</p>
		</div>
		<div class="flex shrink-0 items-center gap-1">
			{#if installPrompt.canPrompt}
				<Button size="sm" class="pointer-coarse:h-11" onclick={() => void installPrompt.prompt()}>
					<Download data-icon="inline-start" />
					Install
				</Button>
			{:else}
				<Button size="sm" class="pointer-coarse:h-11" onclick={() => (stepsOpen = true)}>
					How to install
				</Button>
			{/if}
			<Button
				variant="ghost"
				size="icon-sm"
				class="pointer-coarse:size-11"
				aria-label="Dismiss"
				onclick={dismiss}
			>
				<X class="size-4" />
			</Button>
		</div>
	</div>

	{#if installPrompt.manual}
		<ResponsiveDialog.Root open={stepsOpen} onOpenChange={(open) => (stepsOpen = open)}>
			<ResponsiveDialog.Content title="Install the app" size="md">
				<InstallSteps platform={installPrompt.manual} />
			</ResponsiveDialog.Content>
		</ResponsiveDialog.Root>
	{/if}
{/if}
