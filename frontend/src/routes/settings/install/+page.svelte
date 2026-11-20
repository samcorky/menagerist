<script lang="ts">
	import { Download } from '@lucide/svelte';
	import Page from '$lib/components/page.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import InstallSteps from '$lib/components/install-steps.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { resolve } from '$app/paths';
	import { displayMode } from '$lib/display-mode.svelte';
	import { installPrompt } from '$lib/install-prompt.svelte';
</script>

<svelte:head>
	<title>Install the app - Menagerist</title>
</svelte:head>

<Page width="reading">
	<BackButton peer fallback={resolve('/settings')} />

	<div>
		<h1 class="font-heading text-3xl font-semibold tracking-tight">Install the app</h1>
		<p class="mt-1 text-muted-foreground">
			Open Menagerist from your home screen or dock, in its own window.
		</p>
	</div>

	<div
		data-testid="install-panel"
		class="flex flex-col gap-3 rounded-xl border bg-muted/30 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
	>
		<div class="min-w-0 space-y-2">
			<p class="font-medium">Install the app on this device</p>
			{#if displayMode.standalone}
				<p>Menagerist is installed on this device.</p>
			{:else if installPrompt.canPrompt}
				<p class="text-muted-foreground">
					Opens in its own window, without the browser's tabs and address bar.
				</p>
			{:else if installPrompt.choice === 'waiting'}
				<p>Choose Install in your browser's dialog to add Menagerist.</p>
			{:else if installPrompt.choice === 'accepted'}
				<p>Menagerist is installed. Open it from your apps, home screen or dock.</p>
			{:else if installPrompt.choice === 'dismissed'}
				<p>
					You closed the install prompt. You can still install from your browser's menu, or the
					install icon in its address bar.
				</p>
			{:else if installPrompt.manual}
				<InstallSteps platform={installPrompt.manual} />
			{:else}
				<p>
					This browser can't install the app. Try Chrome or Edge, or Safari on an iPhone, iPad or
					Mac.
				</p>
			{/if}
		</div>

		{#if installPrompt.canPrompt && !displayMode.standalone}
			<Button
				size="sm"
				class="shrink-0 self-start sm:self-auto pointer-coarse:h-11"
				onclick={() => void installPrompt.prompt()}
			>
				<Download data-icon="inline-start" />
				Install
			</Button>
		{/if}
	</div>
</Page>
