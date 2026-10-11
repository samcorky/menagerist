<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { toast } from 'svelte-sonner';
	import { auth } from '$lib/auth.svelte.js';
	import { DISPLAY_NAME_MAX_LENGTH, displayNameProblem, PASSWORD_MIN_LENGTH } from '$lib/auth';
	import BackButton from '$lib/components/back-button.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as Alert from '$lib/components/ui/alert/index.js';
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
				<Input
					id="account-current"
					name="current_password"
					type="password"
					class="h-11"
					autocomplete="current-password"
					required
					disabled={busy}
					bind:value={current}
				/>
			</div>

			<div class="space-y-1.5">
				<Label for="account-new">New password</Label>
				<Input
					id="account-new"
					name="new_password"
					type="password"
					class="h-11"
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
				<Input
					id="account-confirm"
					name="confirm_password"
					type="password"
					class="h-11"
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
	</div>
</main>
