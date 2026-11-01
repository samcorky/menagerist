<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import PasswordInput from '$lib/components/password-input.svelte';
	import { tick } from 'svelte';
	import { auth } from '$lib/auth.svelte.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	let username = $state('');
	let password = $state('');
	let passwordInput = $state<HTMLInputElement | null>(null);
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		busy = true;
		error = null;
		const result = await auth.signIn(username.trim(), password);
		// On success the route guard moves on to the page asked for.
		if (!result.ok) {
			error = result.message;
			password = '';
		}
		busy = false;
		if (!result.ok) {
			await tick();
			passwordInput?.focus();
		}
	}
</script>

<svelte:head>
	<title>Sign in - Menagerist</title>
</svelte:head>

<Page width="narrow" class="pt-8">
	<div>
		<h1 class="font-heading text-3xl font-semibold tracking-tight">Sign in</h1>
		<p class="mt-1 text-muted-foreground">Welcome back to your collection.</p>
	</div>

	<form class="space-y-4" onsubmit={handleSubmit}>
		{#if error}
			<Alert.Root variant="destructive">
				<Alert.Description>{error}</Alert.Description>
			</Alert.Root>
		{/if}

		<div class="space-y-1.5">
			<Label for="login-username">Username</Label>
			<Input
				id="login-username"
				name="username"
				class="pointer-coarse:h-11"
				autocomplete="username"
				autocapitalize="none"
				spellcheck={false}
				required
				disabled={busy}
				bind:value={username}
			/>
		</div>

		<div class="space-y-1.5">
			<Label for="login-password">Password</Label>
			<PasswordInput
				id="login-password"
				bind:ref={passwordInput}
				name="password"
				autocomplete="current-password"
				required
				disabled={busy}
				bind:value={password}
			/>
		</div>

		<Button
			type="submit"
			class="w-full pointer-coarse:h-11"
			disabled={busy || !username.trim() || !password}
		>
			{#if busy}
				<Spinner class="size-4" />
				Signing in…
			{:else}
				Sign in
			{/if}
		</Button>
	</form>
</Page>
