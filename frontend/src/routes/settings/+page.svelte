<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import SettingsTile from '$lib/components/settings-tile.svelte';
	import { resolve } from '$app/paths';
	import {
		Tag,
		ArrowLeftRight,
		Bookmark,
		Activity,
		Sparkles,
		Shield,
		UserRound,
		Trash2
	} from '@lucide/svelte';
	import { auth } from '$lib/auth.svelte.js';
</script>

<svelte:head>
	<title>Settings - Menagerist</title>
</svelte:head>

<Page width="fluid" class="gap-6">
	<div>
		<h1 class="font-heading text-3xl font-semibold tracking-tight">Settings</h1>
		<p class="mt-1 text-muted-foreground">Manage your item structure.</p>
	</div>

	<div class="grid gap-3 sm:grid-cols-[repeat(auto-fill,minmax(20rem,1fr))]">
		<SettingsTile
			href={resolve('/settings/item-types')}
			icon={Tag}
			title="Item types"
			description="Organise your items with types like &quot;Film&quot;, &quot;Person&quot;, or &quot;Event&quot;."
		/>
		<SettingsTile
			href={resolve('/settings/relationships')}
			icon={ArrowLeftRight}
			title="Relationship types"
			description="Define how items connect - &quot;Directed by&quot;, &quot;Signed by&quot;, &quot;Part of&quot;."
		/>
		<SettingsTile
			href={resolve('/settings/saved-fields')}
			icon={Bookmark}
			title="Saved fields"
			description="Reuse a field or a list of choices across item types."
		/>
		<SettingsTile
			href={resolve('/settings/examples')}
			icon={Sparkles}
			title="Examples"
			description="Explore Menagerist with ready-made example items."
		/>
		<SettingsTile
			href={resolve('/recently-deleted')}
			icon={Trash2}
			title="Recently deleted"
			description="Restore items and collections you deleted, or delete them for good."
		/>

		{#if auth.isAdmin}
			<SettingsTile
				href={resolve('/admin')}
				icon={Shield}
				title="Administration"
				description="Manage users and active devices."
			/>
		{/if}

		<SettingsTile
			href={resolve('/settings/account')}
			icon={UserRound}
			title="Account"
			description="Change your password."
		/>

		<SettingsTile
			href={resolve('/status')}
			icon={Activity}
			title="System status"
			description="Health checks, database connectivity, and build info."
		/>
	</div>
</Page>
