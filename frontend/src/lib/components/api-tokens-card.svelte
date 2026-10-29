<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Check, ChevronDown, Clock, Copy, KeyRound, Plus } from '@lucide/svelte';
	import {
		createApiToken,
		listApiTokens,
		listGrantablePermissions,
		revokeApiToken,
		rotateApiToken,
		type ApiTokenResponse
	} from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import {
		AREAS,
		DEFAULT_EXPIRY_DAYS,
		EXPIRY_OPTIONS,
		TOKEN_PRESETS,
		describeExpiry,
		describeGrants,
		describeLastUsed,
		expiresSoon,
		grantsForPreset,
		grantsForSelection,
		sampleCurl,
		tokenErrorMessage,
		type AreaAccess,
		type TokenPreset
	} from '$lib/api-tokens';
	import { wide } from '$lib/viewport.svelte';
	import { auth } from '$lib/auth.svelte.js';
	import { copyText } from '$lib/clipboard';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import HiddenUsername from '$lib/components/hidden-username.svelte';
	import DataTable from '$lib/components/data-table.svelte';
	import PasswordInput from '$lib/components/password-input.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Collapsible from '$lib/components/ui/collapsible/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { NativeSelect, NativeSelectOption } from '$lib/components/ui/native-select/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	let tokens = $state<ApiTokenResponse[]>([]);
	let tokensLoading = $state(true);
	let tokensError = $state<string | null>(null);
	let now = $state(new Date());

	let grantable = $state<string[]>([]);
	let grantableError = $state<string | null>(null);

	// New token dialog
	let createOpen = $state(false);
	let name = $state('');
	let password = $state('');
	let preset = $state<TokenPreset | null>('read');
	let selection = $state<Record<string, AreaAccess>>({});
	let advancedOpen = $state(false);
	let expiryDays = $state(DEFAULT_EXPIRY_DAYS);
	let creating = $state(false);
	let createError = $state<string | null>(null);

	// Regenerate dialog
	let rotateTarget = $state<ApiTokenResponse | null>(null);
	let rotatePassword = $state('');
	let rotateExpiryDays = $state(DEFAULT_EXPIRY_DAYS);
	let rotating = $state(false);
	let rotateError = $state<string | null>(null);

	// Revoke confirmation
	let revokeTarget = $state<ApiTokenResponse | null>(null);
	let revoking = $state(false);

	// The one-time secret; cleared when its dialog closes.
	let secret = $state<{ name: string; token: string } | null>(null);
	let copied = $state(false);
	let copyFailed = $state(false);
	let tokenField = $state<HTMLInputElement | null>(null);

	const grants = $derived(grantsForSelection(selection, grantable));
	const visibleAreas = $derived(
		AREAS.filter((a) => [...a.read, ...a.write].some((p) => grantable.includes(p)))
	);
	const canSubmit = $derived(
		name.trim() !== '' && password !== '' && grants.length > 0 && grantable.length > 0
	);
	const curlSample = $derived(secret ? sampleCurl(window.location.origin, secret.token) : '');
	let nameEl = $state<HTMLInputElement | null>(null);
	let rotatePasswordEl = $state<HTMLInputElement | null>(null);

	function metaParts(token: ApiTokenResponse): string[] {
		return [
			describeExpiry(token.expires_at, now),
			describeLastUsed(token.last_used_at, now)
		].filter((part) => part !== '');
	}

	function selectionFor(wanted: string[]): Record<string, AreaAccess> {
		const next: Record<string, AreaAccess> = {};
		for (const area of AREAS) {
			if (area.write.some((p) => wanted.includes(p))) next[area.id] = 'write';
			else if (area.read.some((p) => wanted.includes(p))) next[area.id] = 'read';
			else next[area.id] = 'none';
		}
		return next;
	}

	function choosePreset(value: TokenPreset) {
		preset = value;
		selection = selectionFor(grantsForPreset(value, grantable));
	}

	function setAccess(areaId: string, access: AreaAccess) {
		selection = { ...selection, [areaId]: access };
		preset = null;
	}

	async function loadTokens() {
		tokensLoading = true;
		tokensError = null;
		try {
			const result = await listApiTokens();
			if (result.error || !result.data) {
				tokensError = networkAwareError(result).title;
			} else {
				tokens = result.data;
				now = new Date();
			}
		} catch {
			tokensError = 'Could not load tokens.';
		}
		tokensLoading = false;
	}

	async function loadGrantable() {
		grantableError = null;
		try {
			const result = await listGrantablePermissions();
			if (result.error || !result.data) {
				grantableError = 'Could not load what a token can be given access to.';
			} else {
				grantable = result.data.permissions;
				if (preset) selection = selectionFor(grantsForPreset(preset, grantable));
			}
		} catch {
			grantableError = 'Could not load what a token can be given access to.';
		}
	}

	$effect(() => {
		void loadTokens();
		void loadGrantable();
	});

	function openCreate() {
		name = '';
		password = '';
		expiryDays = DEFAULT_EXPIRY_DAYS;
		advancedOpen = false;
		createError = null;
		preset = 'read';
		selection = selectionFor(grantsForPreset('read', grantable));
		createOpen = true;
		if (grantable.length === 0) void loadGrantable();
	}

	function closeCreate() {
		createOpen = false;
		password = '';
	}

	function showSecret(tokenName: string, token: string) {
		copied = false;
		copyFailed = false;
		secret = { name: tokenName, token };
	}

	function closeSecret() {
		secret = null;
		copied = false;
		copyFailed = false;
	}

	async function handleCreate(event: SubmitEvent) {
		event.preventDefault();
		if (creating || !canSubmit) return;
		creating = true;
		createError = null;
		try {
			const result = await createApiToken({
				body: {
					name: name.trim(),
					password,
					grants,
					expires_in_days: expiryDays
				}
			});
			if (result.error || !result.data) {
				createError = tokenErrorMessage(result);
				return;
			}
			showSecret(result.data.name, result.data.token);
			closeCreate();
			void loadTokens();
		} catch {
			createError = tokenErrorMessage({});
		} finally {
			creating = false;
		}
	}

	function openRotate(token: ApiTokenResponse) {
		rotatePassword = '';
		rotateExpiryDays = DEFAULT_EXPIRY_DAYS;
		rotateError = null;
		rotateTarget = token;
	}

	function closeRotate() {
		rotateTarget = null;
		rotatePassword = '';
	}

	async function handleRotate(event: SubmitEvent) {
		event.preventDefault();
		if (rotating || !rotateTarget || rotatePassword === '') return;
		rotating = true;
		rotateError = null;
		try {
			const result = await rotateApiToken({
				path: { token_id: rotateTarget.id },
				body: { password: rotatePassword, expires_in_days: rotateExpiryDays }
			});
			if (result.error || !result.data) {
				rotateError = tokenErrorMessage(result);
				return;
			}
			showSecret(result.data.name, result.data.token);
			closeRotate();
			void loadTokens();
		} catch {
			rotateError = tokenErrorMessage({});
		} finally {
			rotating = false;
		}
	}

	async function handleRevoke() {
		if (revoking || !revokeTarget) return;
		revoking = true;
		try {
			const result = await revokeApiToken({ path: { token_id: revokeTarget.id } });
			if (result.error) {
				toast.error(tokenErrorMessage(result));
			} else {
				toast.success('Token revoked');
				revokeTarget = null;
				await loadTokens();
			}
		} catch {
			toast.error(tokenErrorMessage({}));
		} finally {
			revoking = false;
		}
	}

	async function copyToken() {
		if (!secret) return;
		copied = await copyText(secret.token, tokenField);
		copyFailed = !copied;
	}

	function accessLabel(areaId: string): string {
		const area = AREAS.find((a) => a.id === areaId);
		return `${area?.label ?? areaId} access`;
	}

	function canGrant(areaId: string, kind: 'read' | 'write'): boolean {
		const area = AREAS.find((a) => a.id === areaId);
		return (area?.[kind] ?? []).some((p) => grantable.includes(p));
	}
</script>

<section class="space-y-4" aria-labelledby="tokens-heading">
	<div class="flex flex-wrap items-center justify-between gap-2">
		<h2 id="tokens-heading" class="font-heading text-lg font-semibold">Personal access tokens</h2>
		<Button type="button" variant="outline" class="h-11" onclick={openCreate}>
			<Plus class="size-4" />
			New token
		</Button>
	</div>

	<!-- eslint-disable svelte/no-navigation-without-resolve -- /api/docs is served by the backend, not an app route -->
	<p class="text-sm text-muted-foreground">
		A token lets another app or script work with your collection as you, with only the access you
		give it. See the <a
			class="underline underline-offset-4"
			href="/api/docs"
			target="_blank"
			rel="noopener">API documentation</a
		>
		to find out how to use one.
	</p>

	{#if tokensError}
		<Alert.Root variant="destructive">
			<Alert.Description>{tokensError}</Alert.Description>
		</Alert.Root>
		<Button type="button" variant="outline" class="h-11" onclick={() => void loadTokens()}>
			Retry
		</Button>
	{:else if tokensLoading && tokens.length === 0}
		<div class="space-y-3">
			<Skeleton class="h-20 w-full rounded-xl" />
		</div>
	{:else if tokens.length === 0}
		<p class="text-sm text-muted-foreground">You have not created any tokens.</p>
	{:else}
		{#if wide.current}
			<DataTable
				label="Personal access tokens"
				columns={[
					{ label: 'Token' },
					{ label: 'Access' },
					{ label: 'Expires' },
					{ label: 'Last used' },
					{ label: 'Actions', end: true }
				]}
			>
				{#each tokens as token (token.id)}
					<Table.Row>
						<Table.Cell class="max-w-48 font-medium break-words">
							<div class="flex items-center gap-2">
								<KeyRound class="size-4 shrink-0 text-muted-foreground" />
								{token.name}
							</div>
						</Table.Cell>
						<Table.Cell class="text-muted-foreground">{describeGrants(token.grants)}</Table.Cell>
						<Table.Cell>
							{#if expiresSoon(token.expires_at, now)}
								<Badge variant="outline" class="gap-1 font-semibold">
									<Clock class="size-3" />
									{describeExpiry(token.expires_at, now)}
								</Badge>
							{:else}
								<span class="text-muted-foreground">{describeExpiry(token.expires_at, now)}</span>
							{/if}
						</Table.Cell>
						<Table.Cell class="text-muted-foreground">
							{describeLastUsed(token.last_used_at, now)}
						</Table.Cell>
						<Table.Cell>
							<div class="flex justify-end gap-2">
								<Button
									type="button"
									variant="outline"
									class="h-9"
									aria-label={`Regenerate ${token.name}`}
									onclick={() => openRotate(token)}
								>
									Regenerate
								</Button>
								<Button
									type="button"
									variant="outline"
									class="h-9"
									aria-label={`Revoke ${token.name}`}
									onclick={() => (revokeTarget = token)}
								>
									Revoke
								</Button>
							</div>
						</Table.Cell>
					</Table.Row>
				{/each}
			</DataTable>
		{:else}
			<ul class="space-y-3" aria-label="Personal access tokens">
				{#each tokens as token (token.id)}
					<li>
						<Card.Root>
							<Card.Content
								class="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between"
							>
								<div class="flex items-start gap-3">
									<div
										class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"
									>
										<KeyRound class="size-5" />
									</div>
									<div class="min-w-0 space-y-1">
										<p class="font-medium break-words">{token.name}</p>
										<p class="text-sm text-muted-foreground">{describeGrants(token.grants)}</p>
										<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
											{#if expiresSoon(token.expires_at, now)}
												<Badge variant="outline" class="gap-1 font-semibold">
													<Clock class="size-3" />
													{describeExpiry(token.expires_at, now)}
												</Badge>
												<span class="text-muted-foreground">
													{describeLastUsed(token.last_used_at, now)}
												</span>
											{:else}
												<span class="text-muted-foreground">{metaParts(token).join(' · ')}</span>
											{/if}
										</div>
									</div>
								</div>

								<div class="flex shrink-0 gap-2">
									<Button
										type="button"
										variant="outline"
										class="h-11"
										aria-label={`Regenerate ${token.name}`}
										onclick={() => openRotate(token)}
									>
										Regenerate
									</Button>
									<Button
										type="button"
										variant="outline"
										class="h-11"
										aria-label={`Revoke ${token.name}`}
										onclick={() => (revokeTarget = token)}
									>
										Revoke
									</Button>
								</div>
							</Card.Content>
						</Card.Root>
					</li>
				{/each}
			</ul>
		{/if}
	{/if}
</section>

<ResponsiveDialog.Root
	open={createOpen}
	onOpenChange={(open) => {
		if (!open) closeCreate();
	}}
>
	<ResponsiveDialog.Content
		title="New token"
		size="md"
		onOpenAutoFocus={(e) => {
			e.preventDefault();
			nameEl?.focus();
		}}
	>
		<form class="mt-4 space-y-4" onsubmit={handleCreate}>
			{#if createError}
				<Alert.Root variant="destructive" role="alert">
					<Alert.Description>{createError}</Alert.Description>
				</Alert.Root>
			{/if}
			{#if grantableError}
				<Alert.Root variant="destructive" role="alert">
					<Alert.Description>{grantableError}</Alert.Description>
				</Alert.Root>
			{/if}

			<div class="space-y-1.5">
				<Label for="token-name">Name</Label>
				<Input
					id="token-name"
					bind:ref={nameEl}
					name="token_name"
					class="h-11"
					autocomplete="off"
					required
					placeholder="For example, Home server"
					disabled={creating}
					bind:value={name}
				/>
			</div>

			<div class="space-y-1.5">
				<HiddenUsername username={auth.user?.username ?? ''} />
				<Label for="token-password">Your password</Label>
				<PasswordInput
					id="token-password"
					name="current_password"
					autocomplete="current-password"
					required
					disabled={creating}
					bind:value={password}
				/>
				<p class="text-xs text-muted-foreground">We ask for it to make sure it is you.</p>
			</div>

			<fieldset class="space-y-2" disabled={creating}>
				<legend class="text-sm font-medium">Access</legend>
				{#each Object.entries(TOKEN_PRESETS) as [key, label] (key)}
					<label
						class="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border px-3 has-[:checked]:border-primary"
					>
						<input
							type="radio"
							name="token_preset"
							class="size-4 accent-primary"
							value={key}
							checked={preset === key}
							onchange={() => choosePreset(key as TokenPreset)}
						/>
						<span class="text-sm">{label}</span>
					</label>
				{/each}
				{#if preset === null}
					<p class="text-xs text-muted-foreground">Custom access, set under Advanced.</p>
				{/if}
			</fieldset>

			<Collapsible.Root bind:open={advancedOpen}>
				<Collapsible.Trigger
					class="group flex min-h-11 items-center gap-1 text-sm font-medium underline-offset-4 hover:underline"
				>
					Advanced
					<ChevronDown
						class="size-4 transition-transform duration-150 group-data-[state=open]:rotate-180"
					/>
				</Collapsible.Trigger>
				<Collapsible.Content class="space-y-2 pt-1">
					{#each visibleAreas as area (area.id)}
						<div class="flex items-center justify-between gap-3">
							<Label for={`token-area-${area.id}`}>{area.label}</Label>
							<NativeSelect
								id={`token-area-${area.id}`}
								class="[&_select]:h-11"
								aria-label={accessLabel(area.id)}
								disabled={creating}
								value={selection[area.id] ?? 'none'}
								onchange={(e) =>
									setAccess(area.id, (e.target as HTMLSelectElement).value as AreaAccess)}
							>
								<NativeSelectOption value="none">No access</NativeSelectOption>
								{#if canGrant(area.id, 'read')}
									<NativeSelectOption value="read">Read</NativeSelectOption>
								{/if}
								{#if canGrant(area.id, 'write')}
									<NativeSelectOption value="write">Read and write</NativeSelectOption>
								{/if}
							</NativeSelect>
						</div>
					{/each}
				</Collapsible.Content>
			</Collapsible.Root>

			<div class="space-y-1.5">
				<Label for="token-expiry">Expires after</Label>
				<NativeSelect
					id="token-expiry"
					class="w-full [&_select]:h-11"
					disabled={creating}
					bind:value={expiryDays}
				>
					{#each EXPIRY_OPTIONS as option (option.days)}
						<NativeSelectOption value={option.days}>{option.label}</NativeSelectOption>
					{/each}
				</NativeSelect>
			</div>

			{#if grants.length === 0 && grantable.length > 0}
				<p class="text-xs text-muted-foreground">Give the token access to at least one area.</p>
			{/if}

			<div class="flex justify-end gap-2">
				<Button
					type="button"
					variant="outline"
					class="h-11"
					disabled={creating}
					onclick={closeCreate}
				>
					Cancel
				</Button>
				<Button type="submit" class="h-11" disabled={creating || !canSubmit}>
					{#if creating}
						<Spinner class="size-4" />
						Creating…
					{:else}
						Create token
					{/if}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

<ResponsiveDialog.Root
	open={rotateTarget !== null}
	onOpenChange={(open) => {
		if (!open) closeRotate();
	}}
>
	<ResponsiveDialog.Content
		title="Regenerate token"
		size="md"
		onOpenAutoFocus={(e) => {
			e.preventDefault();
			rotatePasswordEl?.focus();
		}}
	>
		<form class="mt-4 space-y-4" onsubmit={handleRotate}>
			<ResponsiveDialog.Description class="text-sm text-muted-foreground">
				{rotateTarget?.name ?? ''} will get a new value with the same access. The old one stops working
				straight away.
			</ResponsiveDialog.Description>

			{#if rotateError}
				<Alert.Root variant="destructive" role="alert">
					<Alert.Description>{rotateError}</Alert.Description>
				</Alert.Root>
			{/if}

			<div class="space-y-1.5">
				<HiddenUsername username={auth.user?.username ?? ''} />
				<Label for="rotate-password">Your password</Label>
				<PasswordInput
					id="rotate-password"
					bind:ref={rotatePasswordEl}
					name="current_password"
					autocomplete="current-password"
					required
					disabled={rotating}
					bind:value={rotatePassword}
				/>
			</div>

			<div class="space-y-1.5">
				<Label for="rotate-expiry">Expires after</Label>
				<NativeSelect
					id="rotate-expiry"
					class="w-full [&_select]:h-11"
					disabled={rotating}
					bind:value={rotateExpiryDays}
				>
					{#each EXPIRY_OPTIONS as option (option.days)}
						<NativeSelectOption value={option.days}>{option.label}</NativeSelectOption>
					{/each}
				</NativeSelect>
			</div>

			<div class="flex justify-end gap-2">
				<Button
					type="button"
					variant="outline"
					class="h-11"
					disabled={rotating}
					onclick={closeRotate}
				>
					Cancel
				</Button>
				<Button type="submit" class="h-11" disabled={rotating || rotatePassword === ''}>
					{#if rotating}
						<Spinner class="size-4" />
						Generating…
					{:else}
						Generate new token
					{/if}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

<ResponsiveDialog.Root
	open={secret !== null}
	onOpenChange={(open) => {
		if (!open) closeSecret();
	}}
>
	<ResponsiveDialog.Content title="Your new token" size="lg">
		{#if secret}
			<div class="mt-4 space-y-4">
				<Alert.Root>
					<Alert.Title>Copy it now</Alert.Title>
					<Alert.Description>
						This is the only time the token for {secret.name} will be shown. Store it somewhere safe.
						If you lose it, regenerate it.
					</Alert.Description>
				</Alert.Root>

				<div class="space-y-1.5">
					<Label for="token-value">Token</Label>
					<div class="flex gap-2">
						<Input
							id="token-value"
							bind:ref={tokenField}
							class="h-11 font-mono text-xs"
							readonly
							value={secret.token}
							onfocus={(e) => e.currentTarget.select()}
						/>
						<Button type="button" variant="outline" class="h-11 shrink-0" onclick={copyToken}>
							{#if copied}
								<Check class="size-4" />
								Copied
							{:else}
								<Copy class="size-4" />
								Copy token
							{/if}
						</Button>
					</div>
					{#if copyFailed}
						<p class="text-xs text-destructive" role="alert">
							Could not copy automatically. Select the token and copy it by hand.
						</p>
					{/if}
				</div>

				<div class="space-y-1.5">
					<p class="text-sm font-medium">Try it</p>
					<pre class="overflow-x-auto rounded-xl bg-muted p-3 font-mono text-xs"><code
							>{curlSample}</code
						></pre>
				</div>

				<div class="flex justify-end">
					<Button type="button" class="h-11" onclick={closeSecret}>Done</Button>
				</div>
			</div>
		{/if}
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

<ConfirmDialog
	open={revokeTarget !== null}
	title={`Revoke ${revokeTarget?.name ?? 'token'}?`}
	description="Anything using this token will stop working straight away. This cannot be undone."
	confirmLabel="Revoke token"
	busyLabel="Revoking…"
	busy={revoking}
	onOpenChange={(open) => {
		if (!open) revokeTarget = null;
	}}
	onConfirm={() => void handleRevoke()}
/>
