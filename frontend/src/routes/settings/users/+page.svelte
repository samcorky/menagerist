<script lang="ts">
	import PasswordInput from '$lib/components/password-input.svelte';
	import { resolve } from '$app/paths';
	import { Copy, Check, KeyRound, LockOpen, Plus, Dices } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import {
		createUser,
		listUsers,
		resetUserPassword,
		unlockUser,
		updateUser,
		type Role,
		type UserResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { generatePassword, PASSWORD_MIN_LENGTH } from '$lib/auth';
	import { isLocked, lastSignIn, lockedLabel } from '$lib/users';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import BackButton from '$lib/components/back-button.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
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

	const newPasswordValid = $derived(newPassword.length >= PASSWORD_MIN_LENGTH);

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
		issued = {
			name: result.data.display_name,
			username: result.data.username,
			password: newPassword
		};
		copied = false;
		users = [...users, result.data];
		newUsername = '';
		newDisplayName = '';
		newPassword = '';
		newRole = 'member';
		showCreate = false;
	}

	async function patch(
		user: UserResponse,
		body: { role?: Role; disabled?: boolean },
		revert?: () => void
	) {
		rowBusy = user.id;
		rowError = null;
		const result = await updateUser({ path: { user_id: user.id }, body });
		rowBusy = null;
		if (result.error || !result.data) {
			rowError = { id: user.id, message: errorMessage(result.error) };
			revert?.();
			return;
		}
		const updated = result.data;
		users = users.map((u) => (u.id === updated.id ? updated : u));
		if (updated.id === auth.user?.id) await auth.refresh();
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

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-2xl flex-col gap-6">
		<BackButton fallback={resolve('/settings')} />
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div>
				<h1 class="font-heading text-3xl font-semibold tracking-tight">Users</h1>
				<p class="mt-1 text-muted-foreground">Everyone who can sign in to this Menagerist.</p>
			</div>
			{#if canCreate && !showCreate}
				<Button class="h-11" onclick={() => (showCreate = true)}>
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
								class="min-h-11 flex-1 rounded-xl bg-muted px-3 py-2.5 font-mono text-sm break-all select-all"
								data-testid="issued-password">{issued.password}</code
							>
							<Button variant="outline" class="h-11" onclick={copyPassword}>
								{#if copied}
									<Check class="size-4" />
									Copied
								{:else}
									<Copy class="size-4" />
									Copy
								{/if}
							</Button>
						</div>
						<div class="mt-3">
							<Button variant="ghost" class="h-11" onclick={() => (issued = null)}>Done</Button>
						</div>
					</Alert.Description>
				</Alert.Root>
			{/if}

			{#if showCreate && canCreate}
				<Card.Root>
					<Card.Header>
						<Card.Title>Add a user</Card.Title>
						<Card.Description>
							Choose a starting password. They will be asked to replace it when they first sign in.
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
								<Label for="new-display-name">Name</Label>
								<Input
									id="new-display-name"
									class="h-11"
									autocomplete="off"
									required
									disabled={creating}
									bind:value={newDisplayName}
								/>
							</div>
							<div class="space-y-1.5">
								<Label for="new-username">Username</Label>
								<Input
									id="new-username"
									class="h-11"
									autocomplete="off"
									autocapitalize="none"
									spellcheck={false}
									required
									disabled={creating}
									bind:value={newUsername}
								/>
							</div>
							<div class="space-y-1.5">
								<Label for="new-user-password">Starting password</Label>
								<div class="flex gap-2">
									<PasswordInput
										id="new-user-password"
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
										class="h-11 shrink-0"
										disabled={creating}
										onclick={() => (newPassword = generatePassword())}
									>
										<Dices class="size-4" />
										Generate
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
									class="w-full [&_select]:h-11"
									disabled={creating}
									bind:value={newRole}
								>
									<option value="member">Member</option>
									<option value="admin">Administrator</option>
								</NativeSelect>
							</div>
							<div class="flex flex-wrap justify-end gap-2">
								<Button
									type="button"
									variant="outline"
									class="h-11"
									disabled={creating}
									onclick={() => {
										showCreate = false;
										createError = null;
									}}
								>
									Cancel
								</Button>
								<Button type="submit" class="h-11" disabled={creating || !newPasswordValid}>
									{#if creating}
										<Spinner class="size-4" />
										Adding…
									{:else}
										Add user
									{/if}
								</Button>
							</div>
						</form>
					</Card.Content>
				</Card.Root>
			{/if}

			{#if loadError}
				<Alert.Root variant="destructive">
					<Alert.Description>
						{loadError}
						<Button variant="link" class="h-11 px-1" onclick={load}>Try again</Button>
					</Alert.Description>
				</Alert.Root>
			{:else if loading}
				<div class="space-y-3" aria-busy="true">
					<Skeleton class="h-24 w-full rounded-2xl" />
					<Skeleton class="h-24 w-full rounded-2xl" />
				</div>
			{:else}
				<ul class="space-y-3" aria-label="Users">
					{#each users as user (user.id)}
						{@const isMe = user.id === auth.user?.id}
						{@const locked = isLocked(user.locked_until)}
						{@const signedInAt = lastSignIn(user.last_login_at)}
						<li>
							<Card.Root>
								<Card.Content class="space-y-3">
									<div class="flex flex-wrap items-center gap-2">
										<p class="font-heading font-semibold">{user.display_name}</p>
										{#if isMe}<Badge variant="secondary">You</Badge>{/if}
										{#if user.disabled}<Badge variant="outline">Disabled</Badge>{/if}
										{#if locked && user.locked_until}
											<Badge variant="destructive">{lockedLabel(user.locked_until)}</Badge>
										{/if}
										{#if user.password_expired}<Badge variant="outline">Must change password</Badge
											>{/if}
									</div>
									<p class="text-sm break-all text-muted-foreground">{user.username}</p>
									<p class="text-sm text-muted-foreground" title={signedInAt.title}>
										Last sign-in: {signedInAt.text}
									</p>

									{#if canUpdate || canReset || (canUnlock && locked)}
										<div class="flex flex-wrap items-end gap-2">
											{#if canUpdate}
												<div class="space-y-1">
													<Label for="role-{user.id}" class="text-xs">Role</Label>
													<NativeSelect
														id="role-{user.id}"
														class="[&_select]:h-11"
														disabled={rowBusy === user.id || isMe}
														value={user.role}
														onchange={(e) => {
															const select = e.currentTarget;
															void patch(user, { role: select.value as Role }, () => {
																select.value = user.role;
															});
														}}
													>
														<option value="member">Member</option>
														<option value="admin">Administrator</option>
													</NativeSelect>
												</div>
												<Button
													variant="outline"
													class="h-11"
													disabled={rowBusy === user.id || isMe}
													onclick={() =>
														user.disabled
															? patch(user, { disabled: false })
															: (disableTarget = user)}
												>
													{user.disabled ? 'Enable' : 'Disable'}
												</Button>
											{/if}
											{#if canReset}
												<Button
													variant="outline"
													class="h-11"
													disabled={rowBusy === user.id}
													onclick={() => (confirmResetTarget = user)}
												>
													<KeyRound class="size-4" />
													Reset password
												</Button>
											{/if}
											{#if canUnlock && locked}
												<Button
													variant="outline"
													class="h-11"
													disabled={rowBusy === user.id}
													onclick={() => handleUnlock(user)}
												>
													<LockOpen class="size-4" />
													Unlock
												</Button>
											{/if}
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
	</div>
</main>

<ConfirmDialog
	open={disableTarget !== null}
	title="Disable {disableTarget?.display_name}?"
	description="They are signed out and cannot sign in until re-enabled."
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
	description="Their sessions end and they must choose a new password at next sign-in."
	confirmLabel="Continue"
	destructive={false}
	onOpenChange={(open) => {
		if (!open) confirmResetTarget = null;
	}}
	onConfirm={confirmReset}
/>

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
						class="h-11 shrink-0"
						disabled={resetting}
						onclick={() => (resetPassword = generatePassword())}
					>
						<Dices class="size-4" />
						Generate
					</Button>
				</div>
				<p class="text-xs text-muted-foreground">At least {PASSWORD_MIN_LENGTH} characters.</p>
			</div>
			<div class="flex justify-end gap-2">
				<Button
					type="button"
					variant="outline"
					class="h-11"
					disabled={resetting}
					onclick={() => (resetTarget = null)}
				>
					Cancel
				</Button>
				<Button
					type="submit"
					class="h-11"
					disabled={resetting || resetPassword.length < PASSWORD_MIN_LENGTH}
				>
					{resetting ? 'Resetting…' : 'Reset password'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
