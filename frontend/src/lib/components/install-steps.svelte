<script lang="ts">
	import type { ManualInstall } from '$lib/install-prompt.svelte';

	let { platform }: { platform: ManualInstall } = $props();

	const STEPS: Record<ManualInstall, string[]> = {
		'ios-safari': [
			'Tap the Share button (a square with an arrow) in Safari’s toolbar.',
			'Scroll down and tap “Add to Home Screen”.',
			'Tap “Add”. Menagerist now opens from your home screen like any other app.'
		],
		'mac-safari': [
			'In Safari’s menu bar, choose File.',
			'Choose “Add to Dock…”.',
			'Click “Add”. Menagerist now opens from your Dock like any other app.'
		]
	};
</script>

<ol data-testid="install-steps" class="list-decimal space-y-2 pl-5 text-sm">
	{#each STEPS[platform] as step (step)}
		<li>{step}</li>
	{/each}
</ol>
