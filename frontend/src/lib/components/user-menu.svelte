<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { LogOut, UserRound, Shield } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { auth } from '$lib/auth.svelte.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';

	const name = $derived(auth.user?.display_name ?? '');

	async function handleSignOut() {
		const result = await auth.signOut();
		if (!result.ok) toast.error("Couldn't sign out", { description: result.message });
	}
</script>

{#if auth.user}
	<DropdownMenu.Root>
		<DropdownMenu.Trigger>
			{#snippet child({ props })}
				<Button
					{...props}
					variant="ghost"
					size="icon"
					class="size-11"
					aria-label="Account menu for {name}"
				>
					<UserRound class="size-4" />
				</Button>
			{/snippet}
		</DropdownMenu.Trigger>
		<DropdownMenu.Content align="end" class="min-w-52">
			<DropdownMenu.Label class="truncate">{name}</DropdownMenu.Label>
			<DropdownMenu.Separator />
			<DropdownMenu.Item class="min-h-11" onSelect={() => goto(resolve('/settings/account'))}>
				<UserRound class="size-4" />
				Account
			</DropdownMenu.Item>
			{#if auth.isAdmin && !auth.passwordExpired}
				<DropdownMenu.Item class="min-h-11" onSelect={() => goto(resolve('/admin'))}>
					<Shield class="size-4" />
					Administration
				</DropdownMenu.Item>
			{/if}
			<DropdownMenu.Item class="min-h-11" onSelect={handleSignOut}>
				<LogOut class="size-4" />
				Sign out
			</DropdownMenu.Item>
		</DropdownMenu.Content>
	</DropdownMenu.Root>
{/if}
