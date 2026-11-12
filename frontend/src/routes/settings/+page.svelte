<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import SettingsTile from '$lib/components/settings-tile.svelte';
	import { resolve } from '$app/paths';
	import { auth } from '$lib/auth.svelte.js';
	import { hubTiles } from '$lib/manage-nav';

	// The same registry the sidebar reads, so a new entry reaches both from one edit.
	const tiles = $derived(hubTiles('settings', (permission) => auth.can(permission)));
</script>

<svelte:head>
	<title>Settings - Menagerist</title>
</svelte:head>

<Page width="fluid" class="gap-6">
	<div>
		<h1 class="font-heading text-3xl font-semibold tracking-tight">Settings</h1>
		<p class="mt-1 text-muted-foreground">Manage your item structure.</p>
	</div>

	<div class="grid gap-3 sm:grid-cols-[repeat(auto-fill,minmax(20rem,1fr))]">
		{#each tiles as tile (tile.href)}
			<SettingsTile
				href={resolve(tile.href as '/')}
				icon={tile.icon}
				title={tile.label}
				description={tile.description ?? ''}
			/>
		{/each}
	</div>
</Page>
