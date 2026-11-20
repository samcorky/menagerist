<script lang="ts">
	import { Share, SquarePlus } from '@lucide/svelte';
	import type { Component } from 'svelte';
	import type { ManualInstall } from '$lib/install-prompt.svelte';

	let { platform }: { platform: ManualInstall } = $props();

	// An icon shows the button as the browser draws it, so it is easy to find.
	type Step = { text: string; icon?: Component };

	const STEPS: Record<ManualInstall, Step[]> = {
		'ios-safari': [
			{ text: 'Tap the Share button in Safari’s toolbar.', icon: Share },
			{ text: 'Scroll down and tap “Add to Home Screen”.', icon: SquarePlus },
			{ text: 'Tap “Add”. Menagerist now opens from your home screen like any other app.' }
		],
		'mac-safari': [
			{ text: 'In Safari’s menu bar, choose File.' },
			{ text: 'Choose “Add to Dock…”.' },
			{ text: 'Click “Add”. Menagerist now opens from your Dock like any other app.' }
		]
	};
</script>

<ol data-testid="install-steps" class="list-decimal space-y-2 pl-5 text-sm">
	{#each STEPS[platform] as step (step.text)}
		<li>
			{#if step.icon}
				{@const StepIcon = step.icon}
				<StepIcon class="mr-1 inline size-5 align-text-bottom" aria-hidden="true" />
			{/if}
			{step.text}
		</li>
	{/each}
</ol>
