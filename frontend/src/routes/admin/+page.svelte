<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import {
		Users,
		Laptop,
		Archive,
		SlidersHorizontal,
		CalendarClock,
		ChevronRight
	} from '@lucide/svelte';
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
	<BackButton fallback={resolve('/settings')} />
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
				<a href={resolve('/admin/backups')} class="group block">
					<div
						class="flex items-center justify-between rounded-xl border bg-card p-5 transition-colors group-hover:bg-muted/50"
					>
						<div class="flex items-start gap-4">
							<div
								class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground"
							>
								<Archive class="size-5" />
							</div>
							<div>
								<p class="font-heading font-semibold">Backups</p>
								<p class="mt-0.5 text-sm text-muted-foreground">
									Create, download and check complete instance backups.
								</p>
							</div>
						</div>
						<ChevronRight
							class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
						/>
					</div>
				</a>
			{/if}
			{#if canUsers}
				<a href={resolve('/admin/users')} class="group block">
					<div
						class="flex items-center justify-between rounded-xl border bg-card p-5 transition-colors group-hover:bg-muted/50"
					>
						<div class="flex items-start gap-4">
							<div
								class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground"
							>
								<Users class="size-5" />
							</div>
							<div>
								<p class="font-heading font-semibold">Users</p>
								<p class="mt-0.5 text-sm text-muted-foreground">
									Add people, change roles and reset passwords.
								</p>
							</div>
						</div>
						<ChevronRight
							class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
						/>
					</div>
				</a>
			{/if}

			{#if canDevices}
				<a href={resolve('/admin/devices')} class="group block">
					<div
						class="flex items-center justify-between rounded-xl border bg-card p-5 transition-colors group-hover:bg-muted/50"
					>
						<div class="flex items-start gap-4">
							<div
								class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground"
							>
								<Laptop class="size-5" />
							</div>
							<div>
								<p class="font-heading font-semibold">Devices</p>
								<p class="mt-0.5 text-sm text-muted-foreground">
									See everyone's active devices and sign them out.
								</p>
							</div>
						</div>
						<ChevronRight
							class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
						/>
					</div>
				</a>
			{/if}

			{#if canSettings}
				<a href={resolve('/admin/settings')} class="group block">
					<div
						class="flex items-center justify-between rounded-xl border bg-card p-5 transition-colors group-hover:bg-muted/50"
					>
						<div class="flex items-start gap-4">
							<div
								class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground"
							>
								<SlidersHorizontal class="size-5" />
							</div>
							<div>
								<p class="font-heading font-semibold">Settings</p>
								<p class="mt-0.5 text-sm text-muted-foreground">
									Change schedules and how long things are kept.
								</p>
							</div>
						</div>
						<ChevronRight
							class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
						/>
					</div>
				</a>
			{/if}

			{#if canTasks}
				<a href={resolve('/admin/scheduled-tasks')} class="group block">
					<div
						class="flex items-center justify-between rounded-xl border bg-card p-5 transition-colors group-hover:bg-muted/50"
					>
						<div class="flex items-start gap-4">
							<div
								class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground"
							>
								<CalendarClock class="size-5" />
							</div>
							<div>
								<p class="font-heading font-semibold">Scheduled tasks</p>
								<p class="mt-0.5 text-sm text-muted-foreground">
									See what runs in the background and start a task now.
								</p>
							</div>
						</div>
						<ChevronRight
							class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
						/>
					</div>
				</a>
			{/if}
		</div>
	{/if}
</Page>
