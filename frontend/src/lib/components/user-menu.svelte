<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { LogOut, UserRound, Shield } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { auth } from '$lib/auth.svelte.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import * as Tooltip from '$lib/components/ui/tooltip/index.js';
	import UserAvatar from '$lib/components/user-avatar.svelte';
	import { cn } from '$lib/utils.js';

	type Props = {
		/** `sidebar` is the row at the foot of the sidebar; `top-bar` the icon in the header. */
		placement?: 'top-bar' | 'sidebar';
		/** The sidebar is the narrow rail: show the picture only, the name in a tooltip. */
		rail?: boolean;
	};

	let { placement = 'top-bar', rail = false }: Props = $props();

	const name = $derived(auth.user?.display_name ?? '');
	const userId = $derived(auth.user?.id ?? '');
	const avatarVersion = $derived(auth.user?.avatar_version ?? null);
	const inSidebar = $derived(placement === 'sidebar');
	// The tooltip names a trigger that shows no name: the top-bar icon and the rail.
	const tooltip = $derived(!inSidebar || rail);

	async function handleSignOut() {
		const result = await auth.signOut();
		if (!result.ok) toast.error("Couldn't sign out", { description: result.message });
	}
</script>

{#if auth.user}
	<DropdownMenu.Root>
		<!-- The tooltip sits on a wrapper so its trigger and the menu's do not fight over one element. -->
		<Tooltip.Root disabled={!tooltip}>
			<Tooltip.Trigger>
				{#snippet child({ props: tooltipProps })}
					<span {...tooltipProps} class={inSidebar ? 'flex' : 'inline-flex'}>
						<DropdownMenu.Trigger>
							{#snippet child({ props })}
								{#if inSidebar}
									<!-- The picture sits where the other rows' icons do, so the rail never moves it. -->
									<button
										{...props}
										type="button"
										class="flex h-9 w-full min-w-0 items-center gap-2 rounded-xl px-1 text-sm text-foreground transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/30 data-[state=open]:bg-muted pointer-coarse:h-11"
										aria-label="Account menu for {name}"
									>
										<UserAvatar {userId} displayName={name} {avatarVersion} size="sm" decorative />
										<span
											class={cn(
												'truncate whitespace-nowrap transition-opacity duration-150 motion-reduce:transition-none',
												rail && 'opacity-0'
											)}
											data-testid="sidebar-account-name">{name}</span
										>
									</button>
								{:else}
									<Button
										{...props}
										variant="ghost"
										size="icon"
										class="pointer-coarse:size-11"
										aria-label="Account menu for {name}"
									>
										<UserAvatar {userId} displayName={name} {avatarVersion} size="sm" decorative />
									</Button>
								{/if}
							{/snippet}
						</DropdownMenu.Trigger>
					</span>
				{/snippet}
			</Tooltip.Trigger>
			<Tooltip.Content side={inSidebar ? 'right' : undefined}
				>Account menu for {name}</Tooltip.Content
			>
		</Tooltip.Root>
		<DropdownMenu.Content
			side={inSidebar ? (rail ? 'right' : 'top') : 'bottom'}
			align={inSidebar ? 'start' : 'end'}
			class="max-w-72 min-w-52"
		>
			<!-- The full name, however long: the sidebar row may have cut it short. -->
			<DropdownMenu.Label class="flex items-center gap-2">
				<UserAvatar {userId} displayName={name} {avatarVersion} size="md" decorative />
				<span class="min-w-0 break-words">{name}</span>
			</DropdownMenu.Label>
			<DropdownMenu.Separator />
			<DropdownMenu.Item
				class="pointer-coarse:min-h-11"
				onSelect={() => goto(resolve('/settings/account'))}
			>
				<UserRound class="size-4" />
				Account
			</DropdownMenu.Item>
			{#if auth.isAdmin && !auth.passwordExpired}
				<DropdownMenu.Item class="pointer-coarse:min-h-11" onSelect={() => goto(resolve('/admin'))}>
					<Shield class="size-4" />
					Administration
				</DropdownMenu.Item>
			{/if}
			<DropdownMenu.Item class="pointer-coarse:min-h-11" onSelect={handleSignOut}>
				<LogOut class="size-4" />
				Sign out
			</DropdownMenu.Item>
		</DropdownMenu.Content>
	</DropdownMenu.Root>
{/if}
