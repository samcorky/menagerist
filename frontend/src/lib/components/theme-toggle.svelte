<script lang="ts">
	import { Monitor, Sun, Moon } from '@lucide/svelte';
	import IconButton from '$lib/components/icon-button.svelte';
	import { themeController } from '$lib/theme.svelte.js';
</script>

<IconButton label="Toggle theme" labelOnTouch={false} onclick={() => themeController.cycle()}>
	{#if themeController.theme === 'dark'}
		<Moon />
	{:else if themeController.theme === 'light'}
		<Sun />
	{:else}
		<Monitor />
	{/if}
</IconButton>
