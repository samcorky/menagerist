<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import SettingsTile from '$lib/components/settings-tile.svelte';
	import { resolve } from '$app/paths';
	import { Users, Laptop, Archive, SlidersHorizontal, CalendarClock } from '@lucide/svelte';
	import { auth } from '$lib/auth.svelte.js';
	import BackButton from '$lib/components/back-button.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';

	const canUsers = $derived(auth.can('identity:user:list'));
	const canDevices = $derived(auth.can('identity:session:list'));
	const canBackups = $derived(auth.can('backup:archive:read'));
	const canSettings = $derived(auth.can('settings:instance:read'));
	const canTasks = $derived(auth.can('scheduling:job:read'));
	const canAny = $derived(canUsers || canDevices || canBackups || canSettings || canTasks);
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

	{#if !canAny}
		<Alert.Root>
			<Alert.Description>Only administrators can access this area.</Alert.Description>
		</Alert.Root>
	{:else}
		<div class="grid gap-3 sm:grid-cols-[repeat(auto-fill,minmax(20rem,1fr))]">
			{#if canBackups}
				<SettingsTile
					href={resolve('/admin/backups')}
					icon={Archive}
					title="Backups"
					description="Create, download and check complete instance backups."
				/>
			{/if}

			{#if canUsers}
				<SettingsTile
					href={resolve('/admin/users')}
					icon={Users}
					title="Users"
					description="Add people, change roles and reset passwords."
				/>
			{/if}

			{#if canDevices}
				<SettingsTile
					href={resolve('/admin/devices')}
					icon={Laptop}
					title="Devices"
					description="See everyone's active devices and sign them out."
				/>
			{/if}

			{#if canSettings}
				<SettingsTile
					href={resolve('/admin/settings')}
					icon={SlidersHorizontal}
					title="Settings"
					description="Change schedules and how long things are kept."
				/>
			{/if}

			{#if canTasks}
				<SettingsTile
					href={resolve('/admin/scheduled-tasks')}
					icon={CalendarClock}
					title="Scheduled tasks"
					description="See what runs in the background and start a task now."
				/>
			{/if}
		</div>
	{/if}
</Page>
