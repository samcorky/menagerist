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

	<div data-testid="install-panel" class="space-y-3 rounded-xl border bg-card p-4">
		{#if displayMode.standalone}
			<p>Menagerist is installed on this device.</p>
		{:else if installPrompt.canPrompt}
			<Button class="pointer-coarse:h-11" onclick={() => void installPrompt.prompt()}>
				<Download data-icon="inline-start" />
				Install
			</Button>
		{:else if installPrompt.manual}
			<InstallSteps platform={installPrompt.manual} />
		{:else}
			<p>
				This browser can't install the app. Try Chrome or Edge, or Safari on an iPhone, iPad or Mac.
			</p>
		{/if}
	</div>
</Page>
