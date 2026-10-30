<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import { toast } from 'svelte-sonner';
	import {
		listOwnSessions,
		listSessions,
		listUsers,
		revokeSession,
		type AdminSessionResponse,
		type UserResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { describeDevice, formatRelativeTime } from '$lib/devices';
	import { formatIsoDate } from '$lib/format-date';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { wide } from '$lib/viewport.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import DataTable from '$lib/components/data-table.svelte';
	import DeviceIcon from '$lib/components/device-icon.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { NativeSelect } from '$lib/components/ui/native-select/index.js';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	let sessions = $state<AdminSessionResponse[]>([]);
	let users = $state<UserResponse[]>([]);
	let selectedUserId = $state<string>('');
	let loading = $state(true);
	let error = $state<string | null>(null);
	let revokingId = $state<string | null>(null);
	let currentSessionId = $state<string | null>(null);

	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading);
	});

	const canList = $derived(auth.can('identity:session:list'));
	const canRevoke = $derived(auth.can('identity:session:revoke'));
	const canListUsers = $derived(auth.can('identity:user:list'));

	async function loadUsers() {
		if (!canListUsers) return;
		try {
			const res = await listUsers();
			if (res.data) users = res.data;
		} catch {
			// User list is optional for filtering
		}
	}

	async function loadSessions() {
		loading = true;
		error = null;
		try {
			const [res, ownRes] = await Promise.all([
				listSessions({
					query: selectedUserId ? { user_id: selectedUserId } : undefined
				}),
				listOwnSessions()
			]);
			if (ownRes.data) {
				currentSessionId = ownRes.data.find((s) => s.current)?.id ?? null;
			}
			if (res.error || !res.data) {
				error = networkAwareError(res).title;
			} else {
				sessions = res.data;
			}
		} catch {
			error = 'Could not load active devices.';
		}
		loading = false;
	}

	$effect(() => {
		if (canList) {
			void loadUsers();
			void loadSessions();
		} else {
			loading = false;
		}
	});

	function handleFilterChange(e: Event & { currentTarget: HTMLSelectElement }) {
		selectedUserId = e.currentTarget.value;
		void loadSessions();
	}

	async function handleRevoke(sessionId: string) {
		if (revokingId !== null) return;
		revokingId = sessionId;
		try {
			const res = await revokeSession({ path: { session_id: sessionId } });
			if (res.error) {
				toast.error(errorMessage(res.error));
			} else {
				toast.success('Device signed out');
				await loadSessions();
			}
		} catch {
			toast.error('Could not sign out device.');
		} finally {
			revokingId = null;
		}
	}
</script>

<svelte:head>
	<title>Devices - Administration - Menagerist</title>
</svelte:head>

<Page width="fluid" class="gap-6">
	<BackButton fallback={resolve('/admin')} />
	<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Devices</h1>
			<p class="mt-1 text-muted-foreground">
				See active devices and sign them out across all accounts.
			</p>
		</div>

		{#if canList && canListUsers && users.length > 0}
			<div class="flex items-center gap-2 sm:self-end">
				<Label for="device-user-filter" class="shrink-0 text-sm">Filter by user</Label>
				<div class="w-48">
					<NativeSelect
						id="device-user-filter"
						value={selectedUserId}
						onchange={handleFilterChange}
					>
						<option value="">All users</option>
						{#each users as u (u.id)}
							<option value={u.id}>{u.display_name} ({u.username})</option>
						{/each}
					</NativeSelect>
				</div>
			</div>
		{/if}
	</div>

	{#if !canList}
		<Alert.Root>
			<Alert.Description>
				Only administrators with session management permissions can access this page.
			</Alert.Description>
		</Alert.Root>
	{:else if error}
		<Alert.Root variant="destructive">
			<Alert.Description>{error}</Alert.Description>
		</Alert.Root>
		<Button
			variant="outline"
			class="w-full sm:w-auto pointer-coarse:h-11"
			onclick={() => void loadSessions()}
		>
			Retry
		</Button>
	{:else if loading}
		<div class="space-y-3">
			<Skeleton class="h-16 w-full rounded-xl" />
			<Skeleton class="h-16 w-full rounded-xl" />
			<Skeleton class="h-16 w-full rounded-xl" />
		</div>
	{:else if sessions.length === 0}
		<p class="text-sm text-muted-foreground">No active devices.</p>
	{:else}
		{#if wide.current}
			<DataTable
				label="Active devices"
				columns={[
					{ label: 'Person' },
					{ label: 'Device' },
					{ label: 'Address' },
					{ label: 'Signed in' },
					{ label: 'Last active' },
					{ label: 'Action', end: true }
				]}
			>
				{#each sessions as session (session.id)}
					{@const described = describeDevice({
						userAgent: session.user_agent,
						platform: session.client_platform,
						mobile: session.client_mobile
					})}
					<Table.Row>
						<Table.Cell class="font-medium">
							<div>{session.display_name}</div>
							<div class="text-xs font-normal text-muted-foreground">@{session.username}</div>
						</Table.Cell>
						<Table.Cell>
							<div class="flex items-center gap-2">
								<DeviceIcon kind={described.kind} class="size-4 shrink-0 text-muted-foreground" />
								<span title={session.user_agent ?? undefined}>{described.label}</span>
							</div>
						</Table.Cell>
						<Table.Cell class="text-muted-foreground">{session.client_ip ?? '—'}</Table.Cell>
						<Table.Cell class="text-muted-foreground">
							{formatIsoDate(session.created_at.slice(0, 10), 'short')}
						</Table.Cell>
						<Table.Cell class="text-muted-foreground">
							{formatRelativeTime(session.last_seen_at)}
						</Table.Cell>
						<Table.Cell class="text-right">
							{#if session.id === currentSessionId}
								<Badge variant="secondary">This device</Badge>
							{:else if canRevoke}
								<Button
									type="button"
									variant="outline"
									class="h-9 px-3"
									disabled={revokingId === session.id}
									onclick={() => handleRevoke(session.id)}
								>
									{#if revokingId === session.id}
										<Spinner class="size-4" />
									{/if}
									Sign out
								</Button>
							{/if}
						</Table.Cell>
					</Table.Row>
				{/each}
			</DataTable>
		{:else}
			<ul class="space-y-3 md:hidden" aria-label="Active devices">
				{#each sessions as session (session.id)}
					{@const described = describeDevice({
						userAgent: session.user_agent,
						platform: session.client_platform,
						mobile: session.client_mobile
					})}
					<li>
						<Card.Root>
							<Card.Content class="flex flex-col gap-3 p-4">
								<div class="flex items-start justify-between gap-3">
									<div class="flex items-start gap-3">
										<div
											class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"
										>
											<DeviceIcon kind={described.kind} class="size-5" />
										</div>
										<div class="space-y-0.5">
											<div class="flex flex-wrap items-center gap-2">
												<p class="font-medium" title={session.user_agent ?? undefined}>
													{described.label}
												</p>
												{#if session.id === currentSessionId}
													<Badge variant="secondary">This device</Badge>
												{/if}
											</div>
											<p class="text-xs text-muted-foreground">
												{session.display_name} (@{session.username})
											</p>
										</div>
									</div>

									{#if session.id !== currentSessionId && canRevoke}
										<Button
											type="button"
											variant="outline"
											class="shrink-0 pointer-coarse:h-11"
											disabled={revokingId === session.id}
											onclick={() => handleRevoke(session.id)}
										>
											{#if revokingId === session.id}
												<Spinner class="size-4" />
											{/if}
											Sign out
										</Button>
									{/if}
								</div>

								<div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
									{#if session.client_ip}
										<span>{session.client_ip}</span>
										<span>&middot;</span>
									{/if}
									<span>Signed in {formatIsoDate(session.created_at.slice(0, 10), 'short')}</span>
									<span>&middot;</span>
									<span>Last active {formatRelativeTime(session.last_seen_at)}</span>
								</div>
							</Card.Content>
						</Card.Root>
					</li>
				{/each}
			</ul>
		{/if}
	{/if}
</Page>
