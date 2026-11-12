<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import SettingsTile from '$lib/components/settings-tile.svelte';
	import { resolve } from '$app/paths';
	import { auth } from '$lib/auth.svelte.js';
	import { hubTiles } from '$lib/manage-nav';
	import BackButton from '$lib/components/back-button.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';

	// The same registry the sidebar reads; each entry carries its own permission.
	const tiles = $derived(hubTiles('admin', (permission) => auth.can(permission)));
</script>

<svelte:head>
	<title>Administration - Menagerist</title>
</svelte:head>

<Page width="fluid" class="gap-6">
	<BackButton peer fallback={resolve('/settings')} />
	<div>
		<h1 class="font-heading text-3xl font-semibold tracking-tight">Administration</h1>
		<p class="mt-1 text-muted-foreground">
			Manage users, active devices, backups, scheduled tasks and settings across this Menagerist.
		</p>
	</div>

	{#if tiles.length === 0}
		<Alert.Root>
			<Alert.Description>Only administrators can access this area.</Alert.Description>
		</Alert.Root>
	{:else}
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
	{/if}
</Page>
