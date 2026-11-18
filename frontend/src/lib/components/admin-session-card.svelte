<script lang="ts">
	import type { AdminSessionResponse } from '$lib/api/client';
	import { describeDevice, formatRelativeTime, nameDevice } from '$lib/devices';
	import { formatIsoDate } from '$lib/format-date';
	import DeviceIcon from '$lib/components/device-icon.svelte';
	import DeviceTitle from '$lib/components/device-title.svelte';
	import UserAvatar from '$lib/components/user-avatar.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	/** One signed-in session as an administrator sees it: the device, its name and owner. */
	let {
		session,
		current = false,
		showOwner = true,
		ownerPicture = null,
		revoking = false,
		onrevoke,
		onrename
	}: {
		session: AdminSessionResponse;
		/** The administrator's own session, which is not offered for signing out. */
		current?: boolean;
		/** Off where every card is the same person's, such as one user's devices. */
		showOwner?: boolean;
		ownerPicture?: string | null;
		revoking?: boolean;
		/** Omit where the administrator may not sign sessions out. */
		onrevoke?: () => void;
		/** Save the device's name (`null` clears it); omit where it cannot be renamed. */
		onrename?: (name: string | null) => Promise<boolean>;
	} = $props();

	const described = $derived(
		describeDevice({
			userAgent: session.user_agent,
			platform: session.client_platform,
			mobile: session.client_mobile,
			displayMode: session.display_mode
		})
	);
</script>

<Card.Root>
	<Card.Content class="flex flex-col gap-3 p-4">
		<div class="flex items-start justify-between gap-3">
			<div class="flex min-w-0 items-start gap-3">
				<div
					class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"
				>
					<DeviceIcon kind={described.kind} class="size-5" />
				</div>
				<div class="min-w-0 space-y-0.5">
					<div class="flex flex-wrap items-center gap-2">
						<DeviceTitle
							{...nameDevice(session.device_name, described.label)}
							name={session.device_name ?? null}
							label={described.label}
							userAgent={session.user_agent}
							onsave={session.device_id ? onrename : undefined}
						/>
						{#if current}
							<Badge variant="secondary">This device</Badge>
						{/if}
					</div>
					{#if showOwner}
						<p class="flex items-center gap-1.5 text-xs text-muted-foreground">
							<UserAvatar
								userId={session.user_id}
								displayName={session.display_name ?? session.username ?? ''}
								avatarVersion={ownerPicture}
								size="sm"
								decorative
							/>
							{session.display_name} (@{session.username})
						</p>
					{/if}
				</div>
			</div>

			{#if !current && onrevoke}
				<Button
					type="button"
					variant="outline"
					class="shrink-0 pointer-coarse:h-11"
					disabled={revoking}
					onclick={onrevoke}
				>
					{#if revoking}
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
