<script lang="ts">
	import PasswordInput from '$lib/components/password-input.svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { toast } from 'svelte-sonner';
	import { auth } from '$lib/auth.svelte.js';
	import { DISPLAY_NAME_MAX_LENGTH, displayNameProblem, PASSWORD_MIN_LENGTH } from '$lib/auth';
	import { describeDevice, formatRelativeTime } from '$lib/devices';
	import { formatIsoDate } from '$lib/format-date';
	import {
		listOwnSessions,
		revokeOwnSession,
		revokeOtherSessions,
		type SessionResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import ApiTokensCard from '$lib/components/api-tokens-card.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import DeviceIcon from '$lib/components/device-icon.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	let current = $state('');
	let next = $state('');
	let confirm = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);
	let newError = $state<string | null>(null);

	let displayName = $state(auth.user?.display_name ?? '');
	let nameBusy = $state(false);
	let nameError = $state<string | null>(null);
	let nameTouched = $state(false);

	let sessions = $state<SessionResponse[]>([]);
	let sessionsLoading = $state(true);
	let sessionsError = $state<string | null>(null);
	let sessionBusy = $state<string | null>(null);
	let revokingOthers = $state(false);
	let confirmRevokeOthers = $state(false);

	const nameProblem = $derived(nameTouched ? displayNameProblem(displayName) : null);
	const nameUnchanged = $derived(displayName.trim() === (auth.user?.display_name ?? ''));

	async function handleRename(event: SubmitEvent) {
		event.preventDefault();
		nameTouched = true;
		if (nameBusy || displayNameProblem(displayName)) return;
		nameBusy = true;
		nameError = null;
		const result = await auth.updateDisplayName(displayName);
		nameBusy = false;
		if (!result.ok) {
			nameError = result.message;
			return;
		}
		displayName = auth.user?.display_name ?? displayName;
		nameTouched = false;
		toast.success('Display name updated');
	}

	const forced = $derived(auth.passwordExpired);
	const mismatch = $derived(confirm !== '' && confirm !== next);
	const tooShort = $derived(next !== '' && next.length < PASSWORD_MIN_LENGTH);
	const canSubmit = $derived(
		current !== '' && next.length >= PASSWORD_MIN_LENGTH && confirm === next && next !== current
	);

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (busy || !canSubmit) return;
		const wasForced = forced;
		busy = true;
		error = null;
		newError = null;
		const result = await auth.changePassword(current, next);
		busy = false;
		if (!result.ok) {
			if ('field' in result) newError = result.message;
			else error = result.message;
			return;
		}
		current = '';
		next = '';
		confirm = '';
		toast.success('Password changed');
		if (wasForced) await goto(resolve('/'));
		else void loadSessions();
	}

	async function loadSessions() {
		sessionsLoading = true;
		sessionsError = null;
		try {
			const result = await listOwnSessions();
			if (result.error || !result.data) {
				sessionsError = networkAwareError(result).title;
			} else {
				sessions = result.data;
			}
		} catch {
			sessionsError = 'Could not load devices.';
		}
		sessionsLoading = false;
	}

	$effect(() => {
		if (!forced) void loadSessions();
		else sessionsLoading = false;
	});

	const hasOtherDevices = $derived(sessions.some((s) => !s.current));

	async function handleRevokeSession(sessionId: string) {
		if (sessionBusy !== null) return;
		sessionBusy = sessionId;
		try {
			const result = await revokeOwnSession({ path: { session_id: sessionId } });
			if (result.error) {
				toast.error(errorMessage(result.error));
			} else {
				toast.success('Device signed out');
				await loadSessions();
			}
		} catch {
			toast.error('Could not sign out device.');
		} finally {
			sessionBusy = null;
		}
	}

	async function handleRevokeOtherSessions() {
		if (revokingOthers) return;
		revokingOthers = true;
		try {
			const result = await revokeOtherSessions();
			if (result.error) {
				toast.error(errorMessage(result.error));
			} else {
				toast.success('Other devices signed out');
				confirmRevokeOthers = false;
				await loadSessions();
			}
		} catch {
			toast.error('Could not sign out other devices.');
		} finally {
			revokingOthers = false;
		}
	}
</script>

<svelte:head>
	<title>Account - Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-md flex-col gap-6">
		{#if !forced}
			<BackButton fallback={resolve('/settings')} />
		{/if}
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Account</h1>
			{#if auth.user}
				<p class="mt-1 text-muted-foreground">
					{auth.user.display_name} ({auth.user.username}) &middot;
					{auth.user.role === 'admin' ? 'Administrator' : 'Member'}
				</p>
			{/if}
		</div>

		{#if forced}
			<Alert.Root>
				<Alert.Title>Choose a new password</Alert.Title>
				<Alert.Description>
					Your password was set by an administrator, so you need to replace it before you carry on.
				</Alert.Description>
			</Alert.Root>
		{/if}

		{#if !forced}
			<form class="space-y-4" onsubmit={handleRename}>
				<h2 class="font-heading text-lg font-semibold">Display name</h2>

				<div class="space-y-1.5">
					<Label for="account-display-name">Name</Label>
					<Input
						id="account-display-name"
						name="display_name"
						class="h-11"
						autocomplete="name"
						required
						aria-invalid={nameProblem !== null || nameError !== null}
						aria-describedby="account-display-name-error"
						disabled={nameBusy}
						bind:value={displayName}
						oninput={() => {
							nameTouched = true;
							nameError = null;
						}}
					/>
					<p
						id="account-display-name-error"
						class="text-xs text-destructive"
						role={nameProblem || nameError ? 'alert' : undefined}
					>
						{nameProblem ?? nameError ?? ''}
					</p>
					<p class="text-xs text-muted-foreground">
						Up to {DISPLAY_NAME_MAX_LENGTH} characters. This is the name shown in the menu.
					</p>
				</div>

				<Button type="submit" class="h-11 w-full sm:w-auto" disabled={nameBusy || nameUnchanged}>
					{#if nameBusy}
						<Spinner class="size-4" />
						Saving…
					{:else}
						Save name
					{/if}
				</Button>
			</form>
		{/if}

		<form class="space-y-4" onsubmit={handleSubmit}>
			<h2 class="font-heading text-lg font-semibold">Change password</h2>

			{#if error}
				<Alert.Root variant="destructive">
					<Alert.Description>{error}</Alert.Description>
				</Alert.Root>
			{/if}

			<div class="space-y-1.5">
				<Label for="account-current">Current password</Label>
				<PasswordInput
					id="account-current"
					name="current_password"
					autocomplete="current-password"
					required
					disabled={busy}
					bind:value={current}
				/>
			</div>

			<div class="space-y-1.5">
				<Label for="account-new">New password</Label>
				<PasswordInput
					id="account-new"
					name="new_password"
					autocomplete="new-password"
					required
					aria-invalid={tooShort || newError !== null}
					aria-describedby="account-new-hint account-new-error"
					disabled={busy}
					bind:value={next}
				/>
				<p id="account-new-hint" class="text-xs text-muted-foreground">
					At least {PASSWORD_MIN_LENGTH} characters. Other devices will be signed out.
				</p>
				{#if newError}
					<p id="account-new-error" class="text-xs text-destructive" role="alert">{newError}</p>
				{/if}
			</div>

			<div class="space-y-1.5">
				<Label for="account-confirm">Confirm new password</Label>
				<PasswordInput
					id="account-confirm"
					name="confirm_password"
					autocomplete="new-password"
					required
					aria-invalid={mismatch}
					disabled={busy}
					bind:value={confirm}
				/>
				{#if mismatch}
					<p class="text-xs text-destructive">The passwords do not match.</p>
				{/if}
			</div>

			<Button type="submit" class="h-11 w-full sm:w-auto" disabled={busy || !canSubmit}>
				{#if busy}
					<Spinner class="size-4" />
					Saving…
				{:else}
					Change password
				{/if}
			</Button>
		</form>

		{#if !forced}
			<section class="space-y-4" aria-labelledby="devices-heading">
				<div class="flex items-center justify-between">
					<h2 id="devices-heading" class="font-heading text-lg font-semibold">Devices</h2>
					{#if hasOtherDevices}
						<Button
							type="button"
							variant="outline"
							class="h-11"
							disabled={revokingOthers}
							onclick={() => (confirmRevokeOthers = true)}
						>
							{#if revokingOthers}
								<Spinner class="size-4" />
							{/if}
							Sign out all other devices
						</Button>
					{/if}
				</div>

				{#if sessionsError}
					<Alert.Root variant="destructive">
						<Alert.Description>{sessionsError}</Alert.Description>
					</Alert.Root>
					<Button type="button" variant="outline" class="h-11" onclick={() => void loadSessions()}>
						Retry
					</Button>
				{:else if sessionsLoading}
					<div class="space-y-3">
						<Skeleton class="h-20 w-full rounded-xl" />
						<Skeleton class="h-20 w-full rounded-xl" />
					</div>
				{:else if sessions.length === 0}
					<p class="text-sm text-muted-foreground">No active devices.</p>
				{:else}
					<ul class="space-y-3" aria-label="Active devices">
						{#each sessions as session (session.id)}
							{@const described = describeDevice({
								userAgent: session.user_agent,
								platform: session.client_platform,
								mobile: session.client_mobile
							})}
							<li>
								<Card.Root>
									<Card.Content
										class="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between"
									>
										<div class="flex items-start gap-3">
											<div
												class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"
											>
												<DeviceIcon kind={described.kind} class="size-5" />
											</div>
											<div class="space-y-1">
												<div class="flex flex-wrap items-center gap-2">
													<p class="font-medium" title={session.user_agent ?? undefined}>
														{described.label}
													</p>
													{#if session.current}
														<Badge variant="secondary">This device</Badge>
													{/if}
												</div>
												<p class="text-xs text-muted-foreground">
													{#if session.client_ip}
														{session.client_ip} &middot;
													{/if}
													Signed in {formatIsoDate(session.created_at.slice(0, 10), 'short')} &middot;
													Last active {formatRelativeTime(session.last_seen_at)}
												</p>
											</div>
										</div>

										{#if !session.current}
											<Button
												type="button"
												variant="outline"
												class="h-11 shrink-0"
												disabled={sessionBusy === session.id}
												onclick={() => handleRevokeSession(session.id)}
											>
												{#if sessionBusy === session.id}
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
			</section>

			<ApiTokensCard />

			<ConfirmDialog
				open={confirmRevokeOthers}
				title="Sign out all other devices?"
				description="You will stay signed in on this device, but any other sessions will end."
				confirmLabel="Sign out other devices"
				busyLabel="Signing out…"
				busy={revokingOthers}
				onOpenChange={(open) => {
					if (!open) confirmRevokeOthers = false;
				}}
				onConfirm={() => void handleRevokeOtherSessions()}
			/>
		{/if}
	</div>
</main>
