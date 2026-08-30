<script lang="ts">
	import { Monitor, Sun, Moon } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { themeController } from '$lib/theme.svelte.js';
</script>

<Button
	variant="ghost"
	size="icon"
	onclick={() => themeController.cycle()}
	aria-label="Toggle theme"
>
	{#if themeController.theme === 'dark'}
		<Moon class="size-4" />
	{:else if themeController.theme === 'light'}
		<Sun class="size-4" />
	{:else}
		<Monitor class="size-4" />
	{/if}
</Button>
