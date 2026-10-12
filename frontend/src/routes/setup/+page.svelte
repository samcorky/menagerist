<script lang="ts">
	import PasswordInput from '$lib/components/password-input.svelte';
	import { tick } from 'svelte';
	import { auth } from '$lib/auth.svelte.js';
	import { describeClaimed, PASSWORD_MIN_LENGTH } from '$lib/auth';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	let displayName = $state('');
	let username = $state('');
	let password = $state('');
	let confirm = $state('');
	let nameInput = $state<HTMLInputElement | null>(null);
	let busy = $state(false);
	let error = $state<string | null>(null);
	let claimedSummary = $state<string[] | null>(null);

	const mismatch = $derived(confirm !== '' && confirm !== password);
	const tooShort = $derived(password !== '' && password.length < PASSWORD_MIN_LENGTH);
	const canSubmit = $derived(
		displayName.trim() !== '' &&
			username.trim() !== '' &&
			password.length >= PASSWORD_MIN_LENGTH &&
			confirm === password
	);

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (busy || !canSubmit) return;
		busy = true;
		error = null;
		const result = await auth.setup(username.trim(), displayName.trim(), password);
		if (!result.ok) {
			error = result.message;
			busy = false;
			await tick();
			nameInput?.focus();
			return;
		}
		password = '';
		confirm = '';
		const parts = 'claimed' in result ? describeClaimed(result.claimed) : [];
		if (parts.length === 0) {
			await auth.finishSetup();
		} else {
			claimedSummary = parts;
		}
		busy = false;
	}

	async function handleContinue() {
		busy = true;
		await auth.finishSetup();
		busy = false;
	}
</script>

<svelte:head>
	<title>Set up - Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-10 sm:px-6">
	<div class="mx-auto flex max-w-sm flex-col gap-6">
		{#if claimedSummary}
			<div>
				<h1 class="font-heading text-3xl font-semibold tracking-tight">You're all set</h1>
				<p class="mt-1 text-muted-foreground">Your account is ready and you are signed in.</p>
			</div>
			<Alert.Root>
				<Alert.Description>
					Everything that was already here is now yours: {claimedSummary.join(', ')}.
				</Alert.Description>
			</Alert.Root>
			<Button class="h-11 w-full" disabled={busy} onclick={handleContinue}>
				{#if busy}
					<Spinner class="size-4" />
				{/if}
				Continue
			</Button>
		{:else}
			<div>
				<h1 class="font-heading text-3xl font-semibold tracking-tight">Welcome to Menagerist</h1>
				<p class="mt-1 text-muted-foreground">
					Create the administrator account. Anything already in this collection will become yours.
				</p>
			</div>

			<form class="space-y-4" onsubmit={handleSubmit}>
				{#if error}
					<Alert.Root variant="destructive">
						<Alert.Description>{error}</Alert.Description>
					</Alert.Root>
				{/if}

				<div class="space-y-1.5">
					<Label for="setup-display-name">Your name</Label>
					<Input
						id="setup-display-name"
						bind:ref={nameInput}
						name="display_name"
						class="h-11"
						autocomplete="name"
						required
						disabled={busy}
						bind:value={displayName}
					/>
				</div>

				<div class="space-y-1.5">
					<Label for="setup-username">Username</Label>
					<Input
						id="setup-username"
						name="username"
						class="h-11"
						autocomplete="username"
						autocapitalize="none"
						spellcheck={false}
						required
						disabled={busy}
						bind:value={username}
					/>
					<p class="text-xs text-muted-foreground">
						Letters, numbers, dots, dashes and underscores.
					</p>
				</div>

				<div class="space-y-1.5">
					<Label for="setup-password">Password</Label>
					<PasswordInput
						id="setup-password"
						name="password"
						autocomplete="new-password"
						required
						aria-invalid={tooShort}
						aria-describedby="setup-password-hint"
						disabled={busy}
						bind:value={password}
					/>
					<p id="setup-password-hint" class="text-xs text-muted-foreground">
						At least {PASSWORD_MIN_LENGTH} characters.
					</p>
				</div>

				<div class="space-y-1.5">
					<Label for="setup-confirm">Confirm password</Label>
					<PasswordInput
						id="setup-confirm"
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

				<Button type="submit" class="h-11 w-full" disabled={busy || !canSubmit}>
					{#if busy}
						<Spinner class="size-4" />
						Creating account…
					{:else}
						Create account
					{/if}
				</Button>
			</form>
		{/if}
	</div>
</main>
