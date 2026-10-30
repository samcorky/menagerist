<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import PasswordInput from '$lib/components/password-input.svelte';
	import { resolve } from '$app/paths';
	import { Copy, Check, KeyRound, Laptop, LockOpen, Plus, Dices, Pencil, X } from '@lucide/svelte';
	import { tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		createUser,
		listOwnSessions,
		listSessions,
		listUsers,
		resetUserPassword,
		revokeSession,
		unlockUser,
		updateUser,
		type AdminSessionResponse,
		type Role,
		type UserResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import {
		DISPLAY_NAME_MAX_LENGTH,
		DISPLAY_NAME_MESSAGE,
		generatePassword,
		PASSWORD_MIN_LENGTH
	} from '$lib/auth';
	import { isLocked, lastSignIn, lockedLabel, renameDecision } from '$lib/users';
	import { describeDevice, formatRelativeTime } from '$lib/devices';
	import { formatIsoDate } from '$lib/format-date';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { wide } from '$lib/viewport.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import DataTable from '$lib/components/data-table.svelte';
	import HiddenUsername from '$lib/components/hidden-username.svelte';
	import DeviceIcon from '$lib/components/device-icon.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { NativeSelect } from '$lib/components/ui/native-select/index.js';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import * as Table from '$lib/components/ui/table/index.js';

	let users = $state<UserResponse[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let rowBusy = $state<string | null>(null);
	let rowError = $state<{ id: string; message: string } | null>(null);

	let showCreate = $state(false);
	let newUsername = $state('');
	let newDisplayName = $state('');
	let newPassword = $state('');
	let newRole = $state<Role>('member');
	let creating = $state(false);
	let createError = $state<string | null>(null);

	let disableTarget = $state<UserResponse | null>(null);
	let confirmResetTarget = $state<UserResponse | null>(null);
	let resetTarget = $state<UserResponse | null>(null);
	let resetPassword = $state('');
	let resetting = $state(false);
	let resetError = $state<string | null>(null);

	let devicesTarget = $state<UserResponse | null>(null);
	let userDevices = $state<AdminSessionResponse[]>([]);
	let userDevicesLoading = $state(false);
	let userDevicesError = $state<string | null>(null);
	let revokingDeviceId = $state<string | null>(null);
	let currentSessionId = $state<string | null>(null);

	// Shown once, straight after an account is created or a password is reset.
	let issued = $state<{ name: string; username: string; password: string } | null>(null);
	let copied = $state(false);

	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading);
	});

	async function load() {
		loading = true;
		loadError = null;
		try {
			const result = await listUsers();
			if (result.error || !result.data) {
				loadError = networkAwareError(result).title;
			} else {
				users = result.data;
			}
		} catch {
			loadError = 'Could not load accounts.';
		}
		loading = false;
	}

	$effect(() => {
		if (canList) void load();
		else loading = false;
	});

	const canList = $derived(auth.can('identity:user:list'));
	const canCreate = $derived(auth.can('identity:user:create'));
	const canUpdate = $derived(auth.can('identity:user:update'));
	const canReset = $derived(auth.can('identity:user:reset_password'));
	const canUnlock = $derived(auth.can('identity:user:unlock'));
	const canListSessions = $derived(auth.can('identity:session:list'));
	const canRevokeSessions = $derived(auth.can('identity:session:revoke'));

	const newPasswordValid = $derived(newPassword.length >= PASSWORD_MIN_LENGTH);

	async function loadUserDevices(userId: string) {
		userDevicesLoading = true;
		userDevicesError = null;
		try {
			const [res, ownRes] = await Promise.all([
				listSessions({ query: { user_id: userId } }),
				listOwnSessions()
			]);
			if (ownRes.data) {
				currentSessionId = ownRes.data.find((s) => s.current)?.id ?? null;
			}
			if (res.error || !res.data) {
				userDevicesError = networkAwareError(res).title;
			} else {
				userDevices = res.data;
			}
		} catch {
			userDevicesError = 'Could not load devices.';
		}
		userDevicesLoading = false;
	}

	function openDevices(user: UserResponse) {
		devicesTarget = user;
		void loadUserDevices(user.id);
	}

	async function handleRevokeUserDevice(sessionId: string) {
		if (revokingDeviceId !== null) return;
		revokingDeviceId = sessionId;
		try {
			const res = await revokeSession({ path: { session_id: sessionId } });
			if (res.error) {
				toast.error(errorMessage(res.error));
			} else {
				toast.success('Device signed out');
				if (devicesTarget) await loadUserDevices(devicesTarget.id);
			}
		} catch {
			toast.error('Could not sign out device.');
		} finally {
			revokingDeviceId = null;
		}
	}

	async function handleCreate(event: SubmitEvent) {
		event.preventDefault();
		if (creating || !newPasswordValid) return;
		creating = true;
		createError = null;
		const result = await createUser({
			body: {
				username: newUsername.trim(),
				display_name: newDisplayName.trim(),
				password: newPassword,
				role: newRole
			}
		});
		creating = false;
		if (result.error || !result.data) {
			createError = errorMessage(result.error);
			return;
		}
		const created = result.data;
		issued = { name: created.display_name, username: created.username, password: newPassword };
		copied = false;
		users = [...users, created];
		showCreate = false;
		newUsername = '';
		newDisplayName = '';
		newPassword = '';
		newRole = 'member';
	}

	async function patch(
		user: UserResponse,
		changes: { display_name?: string; role?: Role; disabled?: boolean }
	) {
		rowBusy = user.id;
		rowError = null;
		const result = await updateUser({
			path: { user_id: user.id },
			body: changes
		});
		rowBusy = null;
		if (result.error || !result.data) {
			rowError = { id: user.id, message: errorMessage(result.error) };
			return;
		}
		const updated = result.data;
		users = users.map((u) => (u.id === updated.id ? updated : u));
		if (updated.id === auth.user?.id) await auth.refresh();
	}

	// Inline editing state: which user is being edited, the draft name, and field refs.
	let editing = $state<{
		id: string;
		draft: string;
		error: string | null;
		busy: boolean;
	} | null>(null);

	let editInput = $state<HTMLInputElement | null>(null);
	let editButton = $state<HTMLButtonElement | null>(null);

	async function startEdit(user: UserResponse) {
		rowError = null;
		editing = { id: user.id, draft: user.display_name, error: null, busy: false };
		await tick();
		editInput?.focus();
	}

	async function stopEdit(_userId?: string) {
		editing = null;
		await tick();
		editButton?.focus();
	}

	async function saveEdit(user: UserResponse) {
		if (!editing || editing.id !== user.id || editing.busy) return;
		const decision = renameDecision(user.display_name, editing.draft);
		if (decision.kind === 'unchanged') {
			await stopEdit(user.id);
			return;
		}
		if (decision.kind === 'problem') {
			editing.error = decision.message;
			return;
		}
		editing.busy = true;
		editing.error = null;
		const result = await updateUser({
			path: { user_id: user.id },
			body: { display_name: decision.name }
		});
		if (result.error || !result.data) {
			if (!editing) return;
			editing.busy = false;
			editing.error =
				result.response?.status === 422 ? DISPLAY_NAME_MESSAGE : errorMessage(result.error);
			return;
		}
		const updated = result.data;
		users = users.map((u) => (u.id === updated.id ? updated : u));
		if (updated.id === auth.user?.id) await auth.refresh();
		toast.success('Name updated');
		await stopEdit(user.id);
	}

	async function confirmDisable() {
		const target = disableTarget;
		if (!target) return;
		await patch(target, { disabled: true });
		disableTarget = null;
	}

	function confirmReset() {
		if (confirmResetTarget) openReset(confirmResetTarget);
		confirmResetTarget = null;
	}

	function openReset(user: UserResponse) {
		resetTarget = user;
		resetPassword = '';
		resetError = null;
	}

	async function handleReset(event: SubmitEvent) {
		event.preventDefault();
		if (!resetTarget || resetting || resetPassword.length < PASSWORD_MIN_LENGTH) return;
		resetting = true;
		resetError = null;
		const target = resetTarget;
		const result = await resetUserPassword({
			path: { user_id: target.id },
			body: { password: resetPassword }
		});
		resetting = false;
		if (result.error) {
			resetError = errorMessage(result.error);
			return;
		}
		issued = { name: target.display_name, username: target.username, password: resetPassword };
		copied = false;
		users = users.map((u) =>
			u.id === target.id ? { ...u, password_expired: true, locked_until: null } : u
		);
		resetTarget = null;
		resetPassword = '';
	}

	async function handleUnlock(user: UserResponse) {
		rowBusy = user.id;
		rowError = null;
		const result = await unlockUser({ path: { user_id: user.id } });
		rowBusy = null;
		if (result.error) {
			rowError = { id: user.id, message: errorMessage(result.error) };
			return;
		}
		users = users.map((u) => (u.id === user.id ? { ...u, locked_until: null } : u));
		toast.success('Account unlocked');
	}

	async function copyPassword() {
		if (!issued) return;
		try {
			await navigator.clipboard.writeText(issued.password);
			copied = true;
		} catch {
			toast.error('Could not copy', { description: 'Select the password and copy it by hand.' });
		}
	}
</script>

<svelte:head>
	<title>Users - Menagerist</title>
</svelte:head>

{#snippet nameEditor(user: UserResponse, compact: boolean)}
	{#if editing?.id === user.id}
		<form
			class="flex flex-col gap-1.5"
			onsubmit={(e) => {
				e.preventDefault();
				void saveEdit(user);
			}}
		>
			<div class="flex items-center gap-2">
				<Input
					type="text"
					class={compact ? 'h-9' : 'pointer-coarse:h-11'}
					bind:value={editing.draft}
					bind:ref={editInput}
					disabled={editing.busy}
					maxlength={DISPLAY_NAME_MAX_LENGTH}
					aria-label="Display name for {user.username}"
					onkeydown={(e) => {
						if (e.key === 'Escape') {
							e.preventDefault();
							void stopEdit(user.id);
						}
					}}
				/>
				<Button
					type="submit"
					class={compact ? 'h-9' : 'pointer-coarse:h-11'}
					disabled={editing.busy}
					aria-label="Save display name for {user.username}"
				>
					{#if editing.busy}
						<Spinner />
					{/if}
					Save
				</Button>
				<Button
					type="button"
					variant="ghost"
					size="icon"
					class="shrink-0 {compact ? 'size-9' : 'pointer-coarse:size-11'}"
					disabled={editing.busy}
					aria-label="Cancel editing name for {user.username}"
					onclick={() => stopEdit(user.id)}
				>
					<X class="size-4" />
				</Button>
			</div>
			{#if editing.error}
				<p class="text-sm text-destructive" role="alert">{editing.error}</p>
			{/if}
		</form>
	{:else}
		<div class="flex items-center gap-1.5">
			<p class="font-heading font-semibold tracking-tight">{user.display_name}</p>
			{#if canUpdate}
				<Button
					type="button"
					variant="ghost"
					size="icon"
					class="shrink-0 {compact ? 'size-9' : 'pointer-coarse:size-11'}"
					bind:ref={editButton}
					aria-label="Edit display name for {user.username}"
					onclick={() => startEdit(user)}
				>
					<Pencil class="size-4" />
				</Button>
			{/if}
		</div>
	{/if}
{/snippet}

<!-- The table has a Role column of its own, so it leaves the Admin badge out. -->
{#snippet statusBadges(user: UserResponse, isMe: boolean, locked: boolean, showRole: boolean)}
	{#if isMe}
		<Badge variant="outline">You</Badge>
	{/if}
	{#if showRole && user.role === 'admin'}
		<Badge variant="secondary">Admin</Badge>
	{/if}
	{#if user.disabled}
		<Badge variant="destructive">Disabled</Badge>
	{/if}
	{#if user.password_expired}
		<Badge variant="outline">Must change password</Badge>
	{/if}
	{#if locked && user.locked_until}
		<Badge variant="destructive">{lockedLabel(user.locked_until)}</Badge>
	{/if}
{/snippet}

<!-- Table rows keep the labelled Disable button and fold the rest into icon buttons. -->
{#snippet rowActions(user: UserResponse, isMe: boolean, locked: boolean, compact: boolean)}
	{@const size = compact ? 'size-9' : 'pointer-coarse:h-11'}
	{#if canUpdate}
		<Button
			variant="outline"
			class={compact ? 'h-9' : 'pointer-coarse:h-11'}
			disabled={rowBusy === user.id || isMe}
			onclick={() => (user.disabled ? patch(user, { disabled: false }) : (disableTarget = user))}
		>
			{user.disabled ? 'Enable' : 'Disable'}
		</Button>
	{/if}
	{#if canReset}
		<Button
			variant="outline"
			size={compact ? 'icon' : 'default'}
			class={size}
			title="Reset password"
			aria-label={compact ? 'Reset password' : undefined}
			disabled={rowBusy === user.id}
			onclick={() => (confirmResetTarget = user)}
		>
			<KeyRound class="size-4" />
			{#if !compact}Reset password{/if}
		</Button>
	{/if}
	{#if canUnlock && locked}
		<Button
			variant="outline"
			size={compact ? 'icon' : 'default'}
			class={size}
			title="Unlock"
			aria-label={compact ? 'Unlock' : undefined}
			disabled={rowBusy === user.id}
			onclick={() => handleUnlock(user)}
		>
			<LockOpen class="size-4" />
			{#if !compact}Unlock{/if}
		</Button>
	{/if}
	{#if canListSessions}
		<Button
			variant="outline"
			size={compact ? 'icon' : 'default'}
			class={size}
			title="Devices"
			aria-label={compact ? 'Devices' : undefined}
			disabled={rowBusy === user.id}
			onclick={() => openDevices(user)}
		>
			<Laptop class="size-4" />
			{#if !compact}Devices{/if}
		</Button>
	{/if}
{/snippet}

<Page width="fluid">
	<BackButton fallback={resolve('/admin')} />
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Users</h1>
			<p class="mt-1 text-muted-foreground">Everyone who can sign in to this Menagerist.</p>
		</div>
		{#if canCreate && !showCreate}
			<Button class="pointer-coarse:h-11" onclick={() => (showCreate = true)}>
				<Plus class="size-4" />
				Add user
			</Button>
		{/if}
	</div>

	{#if !canList}
		<Alert.Root>
			<Alert.Description>Only administrators can manage users.</Alert.Description>
		</Alert.Root>
	{:else}
		{#if issued}
			<Alert.Root>
				<Alert.Title>Password for {issued.name}</Alert.Title>
				<Alert.Description>
					<p>
						Give this to {issued.username} now. It is only shown once, and they must change it the first
						time they sign in.
					</p>
					<div class="mt-3 flex flex-wrap items-center gap-2">
						<code
							class="rounded-md border bg-muted px-2.5 py-1 font-mono text-sm font-semibold tracking-wider"
						>
							{issued.password}
						</code>
						<Button variant="outline" class="pointer-coarse:h-11" onclick={copyPassword}>
							{#if copied}
								<Check class="size-4" />
								Copied
							{:else}
								<Copy class="size-4" />
								Copy password
							{/if}
						</Button>
						<Button variant="ghost" class="pointer-coarse:h-11" onclick={() => (issued = null)}
							>Done</Button
						>
					</div>
				</Alert.Description>
			</Alert.Root>
		{/if}

		{#if showCreate}
			<Card.Root class="max-w-2xl">
				<Card.Header>
					<Card.Title>Add user</Card.Title>
					<Card.Description>
						Create a starting account. They'll choose a new password the first time they sign in.
					</Card.Description>
				</Card.Header>
				<Card.Content>
					<form class="space-y-4" onsubmit={handleCreate}>
						{#if createError}
							<Alert.Root variant="destructive">
								<Alert.Description>{createError}</Alert.Description>
							</Alert.Root>
						{/if}
						<div class="space-y-1.5">
							<Label for="new-name">Name</Label>
							<Input
								id="new-name"
								required
								maxlength={DISPLAY_NAME_MAX_LENGTH}
								disabled={creating}
								bind:value={newDisplayName}
							/>
						</div>
						<div class="space-y-1.5">
							<Label for="new-username">Username</Label>
							<Input
								id="new-username"
								autocomplete="off"
								autocapitalize="none"
								spellcheck={false}
								required
								disabled={creating}
								bind:value={newUsername}
							/>
						</div>
						<div class="space-y-1.5">
							<Label for="new-password">Starting password</Label>
							<div class="flex gap-2">
								<PasswordInput
									id="new-password"
									autocomplete="off"
									autocapitalize="none"
									spellcheck={false}
									required
									disabled={creating}
									bind:value={newPassword}
								/>
								<Button
									type="button"
									variant="outline"
									class="shrink-0 pointer-coarse:h-11"
									disabled={creating}
									onclick={() => (newPassword = generatePassword())}
								>
									<Dices class="size-4" />
									Randomise
								</Button>
							</div>
							<p class="text-xs text-muted-foreground">
								At least {PASSWORD_MIN_LENGTH} characters.
							</p>
						</div>
						<div class="space-y-1.5">
							<Label for="new-role">Role</Label>
							<NativeSelect
								id="new-role"
								disabled={creating}
								value={newRole}
								onchange={(e) => (newRole = e.currentTarget.value as Role)}
							>
								<option value="member">Member</option>
								<option value="admin">Administrator</option>
							</NativeSelect>
						</div>
						<div class="flex gap-2 pt-2">
							<Button
								type="submit"
								class="pointer-coarse:h-11"
								disabled={creating || !newPasswordValid}
							>
								{#if creating}
									<Spinner />
								{/if}
								Add user
							</Button>
							<Button
								type="button"
								variant="outline"
								class="pointer-coarse:h-11"
								disabled={creating}
								onclick={() => (showCreate = false)}
							>
								Cancel
							</Button>
						</div>
					</form>
				</Card.Content>
			</Card.Root>
		{/if}

		{#if loading}
			{#if loadingDisplay.show}
				<div class="space-y-3" role="status" aria-label="Loading accounts">
					<Skeleton class="h-28 w-full rounded-xl" />
					<Skeleton class="h-28 w-full rounded-xl" />
				</div>
			{/if}
		{:else if loadError}
			<Alert.Root variant="destructive">
				<Alert.Description>{loadError}</Alert.Description>
			</Alert.Root>
		{:else}
			{#if wide.current}
				<DataTable
					label="Users"
					columns={[
						{ label: 'Person' },
						{ label: 'Role' },
						{ label: 'Status' },
						{ label: 'Last sign-in' },
						{ label: 'Actions', end: true }
					]}
				>
					{#each users as user (user.id)}
						{@const isMe = user.id === auth.user?.id}
						{@const locked = isLocked(user.locked_until)}
						<Table.Row>
							<Table.Cell>
								{@render nameEditor(user, true)}
								<p class="text-sm text-muted-foreground">{user.username}</p>
								{#if rowError?.id === user.id}
									<p class="mt-1 text-sm text-destructive" role="alert">{rowError.message}</p>
								{/if}
							</Table.Cell>
							<Table.Cell>
								{#if canUpdate}
									<div class="w-36">
										<NativeSelect
											class="[&_select]:min-h-9"
											aria-label="Role for {user.username}"
											disabled={rowBusy === user.id || isMe}
											value={user.role}
											onchange={(e) => patch(user, { role: e.currentTarget.value as Role })}
										>
											<option value="member">Member</option>
											<option value="admin">Administrator</option>
										</NativeSelect>
									</div>
									{#if isMe}
										<p class="mt-1 text-xs text-muted-foreground">
											You can't change your own role or disable yourself.
										</p>
									{/if}
								{:else}
									{user.role === 'admin' ? 'Administrator' : 'Member'}
								{/if}
							</Table.Cell>
							<Table.Cell>
								<div class="flex flex-wrap items-center gap-1.5">
									{@render statusBadges(user, isMe, locked, false)}
								</div>
							</Table.Cell>
							<Table.Cell class="text-muted-foreground">
								<span title={lastSignIn(user.last_login_at).title}
									>{lastSignIn(user.last_login_at).text}</span
								>
							</Table.Cell>
							<Table.Cell>
								<div class="flex flex-wrap items-center justify-end gap-1.5">
									{@render rowActions(user, isMe, locked, true)}
								</div>
							</Table.Cell>
						</Table.Row>
					{/each}
				</DataTable>
			{:else}
				<ul class="flex flex-col gap-3" aria-label="Users">
					{#each users as user (user.id)}
						{@const isMe = user.id === auth.user?.id}
						{@const locked = isLocked(user.locked_until)}
						<li>
							<Card.Root>
								<Card.Content class="flex flex-col gap-3 p-4 sm:p-5">
									<div class="flex flex-wrap items-start justify-between gap-2">
										<div class="min-w-0 flex-1">
											{@render nameEditor(user, false)}
											<p class="text-sm text-muted-foreground">{user.username}</p>
										</div>
										<div class="flex flex-wrap items-center gap-1.5">
											{@render statusBadges(user, isMe, locked, true)}
										</div>
									</div>

									<p class="text-xs text-muted-foreground">
										Last sign-in: <span title={lastSignIn(user.last_login_at).title}
											>{lastSignIn(user.last_login_at).text}</span
										>
									</p>

									{#if canUpdate || canReset || canUnlock || canListSessions}
										<div class="flex flex-wrap items-center gap-2 pt-1">
											{#if canUpdate}
												<div class="w-36">
													<NativeSelect
														class="pointer-coarse:[&_select]:min-h-11"
														aria-label="Role for {user.username}"
														disabled={rowBusy === user.id || isMe}
														value={user.role}
														onchange={(e) => patch(user, { role: e.currentTarget.value as Role })}
													>
														<option value="member">Member</option>
														<option value="admin">Administrator</option>
													</NativeSelect>
												</div>
											{/if}
											{@render rowActions(user, isMe, locked, false)}
										</div>
									{/if}

									{#if isMe && canUpdate}
										<p class="text-xs text-muted-foreground">
											You can't change your own role or disable yourself.
										</p>
									{/if}

									{#if rowError?.id === user.id}
										<p class="text-sm text-destructive" role="alert">{rowError.message}</p>
									{/if}
								</Card.Content>
							</Card.Root>
						</li>
					{/each}
				</ul>
			{/if}
		{/if}
	{/if}
</Page>

<ConfirmDialog
	open={disableTarget !== null}
	title="Disable {disableTarget?.display_name}?"
	description="They will be signed out everywhere and cannot sign in until re-enabled."
	confirmLabel="Disable"
	busyLabel="Disabling…"
	busy={rowBusy !== null && rowBusy === disableTarget?.id}
	onOpenChange={(open) => {
		if (!open) disableTarget = null;
	}}
	onConfirm={() => void confirmDisable()}
/>

<ConfirmDialog
	open={confirmResetTarget !== null}
	title="Reset password for {confirmResetTarget?.display_name}?"
	description="They will be signed out everywhere and must choose a new password at next sign-in."
	confirmLabel="Continue"
	destructive={false}
	onOpenChange={(open) => {
		if (!open) confirmResetTarget = null;
	}}
	onConfirm={confirmReset}
/>

<ResponsiveDialog.Root
	open={devicesTarget !== null}
	onOpenChange={(open) => {
		if (!open) devicesTarget = null;
	}}
>
	<ResponsiveDialog.Content title="Devices for {devicesTarget?.display_name}" size="md">
		<ResponsiveDialog.Description>
			Active devices currently signed in to this account.
		</ResponsiveDialog.Description>
		<div class="mt-4 space-y-4">
			{#if userDevicesError}
				<Alert.Root variant="destructive">
					<Alert.Description>{userDevicesError}</Alert.Description>
				</Alert.Root>
				<Button
					variant="outline"
					class="pointer-coarse:h-11"
					onclick={() => devicesTarget && void loadUserDevices(devicesTarget.id)}
				>
					Retry
				</Button>
			{:else if userDevicesLoading}
				<div class="space-y-3">
					<Skeleton class="h-16 w-full rounded-xl" />
					<Skeleton class="h-16 w-full rounded-xl" />
				</div>
			{:else if userDevices.length === 0}
				<p class="text-sm text-muted-foreground">No active devices.</p>
			{:else}
				<ul class="space-y-3" aria-label="User devices">
					{#each userDevices as dev (dev.id)}
						{@const described = describeDevice({
							userAgent: dev.user_agent,
							platform: dev.client_platform,
							mobile: dev.client_mobile
						})}
						<li>
							<Card.Root>
								<Card.Content
									class="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
								>
									<div class="flex items-start gap-3">
										<div
											class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"
										>
											<DeviceIcon kind={described.kind} class="size-5" />
										</div>
										<div class="space-y-1">
											<div class="flex flex-wrap items-center gap-2">
												<p class="font-medium" title={dev.user_agent ?? undefined}>
													{described.label}
												</p>
												{#if dev.id === currentSessionId}
													<Badge variant="secondary">This device</Badge>
												{/if}
											</div>
											<p class="text-xs text-muted-foreground">
												{#if dev.client_ip}
													{dev.client_ip} &middot;
												{/if}
												Signed in {formatIsoDate(dev.created_at.slice(0, 10), 'short')} &middot; Last
												active {formatRelativeTime(dev.last_seen_at)}
											</p>
										</div>
									</div>

									{#if dev.id !== currentSessionId && canRevokeSessions}
										<Button
											type="button"
											variant="outline"
											class="shrink-0 pointer-coarse:h-11"
											disabled={revokingDeviceId === dev.id}
											onclick={() => handleRevokeUserDevice(dev.id)}
										>
											{#if revokingDeviceId === dev.id}
												<Spinner class="size-4" />
											{/if}
											Sign out
										</Button>
									{/if}
								</Card.Content>
							</Card.Root>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

<ResponsiveDialog.Root
	open={resetTarget !== null}
	onOpenChange={(open) => {
		if (!open) resetTarget = null;
	}}
>
	<ResponsiveDialog.Content title="Reset password" size="sm">
		<ResponsiveDialog.Description>
			Choose a new starting password for {resetTarget?.display_name}. They will be signed out
			everywhere and must change it at their next sign-in.
		</ResponsiveDialog.Description>
		<form class="mt-4 space-y-4" onsubmit={handleReset}>
			<HiddenUsername username={resetTarget?.username ?? ''} autocomplete="off" />
			{#if resetError}
				<Alert.Root variant="destructive">
					<Alert.Description>{resetError}</Alert.Description>
				</Alert.Root>
			{/if}
			<div class="space-y-1.5">
				<Label for="reset-password">New starting password</Label>
				<div class="flex gap-2">
					<PasswordInput
						id="reset-password"
						autocomplete="off"
						autocapitalize="none"
						spellcheck={false}
						required
						disabled={resetting}
						bind:value={resetPassword}
					/>
					<Button
						type="button"
						variant="outline"
						class="shrink-0 pointer-coarse:h-11"
						disabled={resetting}
						onclick={() => (resetPassword = generatePassword())}
					>
						<Dices class="size-4" />
						Randomise
					</Button>
				</div>
				<p class="text-xs text-muted-foreground">At least {PASSWORD_MIN_LENGTH} characters.</p>
			</div>
			<div class="flex gap-2 pt-2">
				<Button
					type="submit"
					class="pointer-coarse:h-11"
					disabled={resetting || resetPassword.length < PASSWORD_MIN_LENGTH}
				>
					{#if resetting}
						<Spinner />
					{/if}
					Save password
				</Button>
				<Button
					type="button"
					variant="outline"
					class="pointer-coarse:h-11"
					disabled={resetting}
					onclick={() => (resetTarget = null)}
				>
					Cancel
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
