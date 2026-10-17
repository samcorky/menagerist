<script lang="ts">
	import PasswordInput from '$lib/components/password-input.svelte';
	import { resolve } from '$app/paths';
	import { Copy, Check, KeyRound, LockOpen, Plus, Dices, Pencil, X } from '@lucide/svelte';
	import { tick } from 'svelte';
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
	import {
		DISPLAY_NAME_MAX_LENGTH,
		DISPLAY_NAME_MESSAGE,
		generatePassword,
		PASSWORD_MIN_LENGTH
	} from '$lib/auth';
	import { isLocked, lastSignIn, lockedLabel, renameDecision } from '$lib/users';
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

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-2xl flex-col gap-6">
		<BackButton fallback={resolve('/admin')} />
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
								class="rounded-md border bg-muted px-2.5 py-1 font-mono text-sm font-semibold tracking-wider"
							>
								{issued.password}
							</code>
							<Button variant="outline" class="h-11" onclick={copyPassword}>
								{#if copied}
									<Check class="size-4" />
									Copied
								{:else}
									<Copy class="size-4" />
									Copy password
								{/if}
							</Button>
							<Button variant="ghost" class="h-11" onclick={() => (issued = null)}>Done</Button>
						</div>
					</Alert.Description>
				</Alert.Root>
			{/if}

			{#if showCreate}
				<Card.Root>
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
										class="h-11 shrink-0"
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
								<Button type="submit" class="h-11" disabled={creating || !newPasswordValid}>
									{#if creating}
										<Spinner />
									{/if}
									Add user
								</Button>
								<Button
									type="button"
									variant="outline"
									class="h-11"
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
				<ul class="flex flex-col gap-3" aria-label="Users">
					{#each users as user (user.id)}
						{@const isMe = user.id === auth.user?.id}
						{@const locked = isLocked(user.locked_until)}
						<li>
							<Card.Root>
								<Card.Content class="flex flex-col gap-3 p-4 sm:p-5">
									<div class="flex flex-wrap items-start justify-between gap-2">
										<div class="min-w-0 flex-1">
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
															class="h-11"
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
															class="h-11"
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
															class="size-11 shrink-0"
															disabled={editing.busy}
															aria-label="Cancel editing name for {user.username}"
															onclick={() => stopEdit(user.id)}
														>
															<X class="size-4" />
														</Button>
													</div>
													{#if editing.error}
														<p class="text-sm text-destructive" role="alert">
															{editing.error}
														</p>
													{/if}
												</form>
											{:else}
												<div class="flex items-center gap-1.5">
													<p class="font-heading font-semibold tracking-tight">
														{user.display_name}
													</p>
													{#if canUpdate}
														<Button
															type="button"
															variant="ghost"
															size="icon"
															class="size-11 shrink-0"
															bind:ref={editButton}
															aria-label="Edit display name for {user.username}"
															onclick={() => startEdit(user)}
														>
															<Pencil class="size-4" />
														</Button>
													{/if}
												</div>
											{/if}
											<p class="text-sm text-muted-foreground">{user.username}</p>
										</div>
										<div class="flex flex-wrap items-center gap-1.5">
											{#if isMe}
												<Badge variant="outline">You</Badge>
											{/if}
											{#if user.role === 'admin'}
												<Badge variant="secondary">Admin</Badge>
											{/if}
											{#if user.disabled}
												<Badge variant="destructive">Disabled</Badge>
											{/if}
											{#if user.password_expired}
												<Badge variant="outline">Must change password</Badge>
											{/if}
											{#if locked && user.locked_until}
												<Badge variant="destructive">
													{lockedLabel(user.locked_until)}
												</Badge>
											{/if}
										</div>
									</div>

									<p class="text-xs text-muted-foreground">
										Last sign-in: <span title={lastSignIn(user.last_login_at).title}
											>{lastSignIn(user.last_login_at).text}</span
										>
									</p>

									{#if canUpdate || canReset || canUnlock}
										<div class="flex flex-wrap items-center gap-2 pt-1">
											{#if canUpdate}
												<div class="w-36">
													<NativeSelect
														aria-label="Role for {user.username}"
														disabled={rowBusy === user.id || isMe}
														value={user.role}
														onchange={(e) => patch(user, { role: e.currentTarget.value as Role })}
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
						Randomise
					</Button>
				</div>
				<p class="text-xs text-muted-foreground">At least {PASSWORD_MIN_LENGTH} characters.</p>
			</div>
			<div class="flex gap-2 pt-2">
				<Button
					type="submit"
					class="h-11"
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
					class="h-11"
					disabled={resetting}
					onclick={() => (resetTarget = null)}
				>
					Cancel
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
