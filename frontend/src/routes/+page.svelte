<script lang="ts">
	import { BadgeCheck, RefreshCw, Server, TriangleAlert } from '@lucide/svelte';
	import { getHealth, getVersion } from '$lib/api/client';
	import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

	let healthy = $state<boolean | null>(null);
	let version = $state<string | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(false);
	let checkedAt = $state<Date | null>(null);

	const refreshIntervalMs = 5_000;

	async function loadStatus() {
		loading = true;
		error = null;

		const [healthResult, versionResult] = await Promise.all([getHealth(), getVersion()]);

		if (healthResult.error || versionResult.error || !versionResult.data) {
			healthy = false;
			version = null;
			error = 'Unable to reach the API';
		} else {
			healthy = true;
			version = versionResult.data.current_version;
		}
		checkedAt = new Date();
		loading = false;
	}

	$effect(() => {
		void loadStatus();

		const interval = window.setInterval(() => {
			void loadStatus();
		}, refreshIntervalMs);

		return () => {
			window.clearInterval(interval);
		};
	});
</script>

<svelte:head>
	<title>System Status</title>
	<meta name="description" content="System status POC" />
</svelte:head>

<main class="min-h-screen bg-background px-6 py-10 text-foreground">
	<div class="mx-auto flex max-w-4xl flex-col gap-8">
		<section class="flex flex-col gap-3">
			<Badge variant="outline" class="w-fit gap-2 px-3 py-1">
				<Server class="size-4" />
				System status
			</Badge>

			<div class="space-y-2">
				<h1 class="text-4xl font-semibold tracking-tight">Service health</h1>
				<p class="max-w-2xl text-muted-foreground">
					POC dashboard for checking API reachability and the currently deployed backend version.
				</p>
			</div>
		</section>

		{#if error || healthy === false}
			<Alert variant="destructive">
				<TriangleAlert class="size-4" />
				<AlertTitle>API unavailable</AlertTitle>
				<AlertDescription>
					{error}
				</AlertDescription>
			</Alert>
		{/if}

		<section class="grid gap-4 md:grid-cols-2">
			<Card.Root>
				<Card.Header class="flex flex-row items-start justify-between gap-4 space-y-0">
					<div class="space-y-1">
						<Card.Description>API status</Card.Description>

						<Card.Title class={error ? 'text-destructive' : undefined}>
							{#if loading && healthy === null}
								Checking…
							{:else if error || healthy === false}
								Unavailable
							{:else}
								Operational
							{/if}
						</Card.Title>
					</div>

					<div
						class={[
							'rounded-full border p-3',
							error || healthy === false
								? 'border-destructive/30 bg-destructive/10 text-destructive'
								: 'border-green-500/30 bg-green-500/10 text-green-600'
						]}
					>
						{#if error || healthy === false}
							<TriangleAlert class="size-5" />
						{:else}
							<BadgeCheck class="size-5" />
						{/if}
					</div>
				</Card.Header>

				<Card.Content>
					<div class="rounded-lg bg-muted p-4">
						<p class="text-sm text-muted-foreground">Endpoints</p>
						<div class="mt-1 space-y-1 font-mono text-sm">
							<p>GET /api/health</p>
							<p>GET /api/version</p>
						</div>
					</div>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Description>Application version</Card.Description>

					<Card.Title class="flex h-8 items-center">
						{#if loading && !version}
							<Skeleton class="h-7 w-36" />
						{:else if version}
							{version}
						{:else}
							<span class="text-muted-foreground">Unknown</span>
						{/if}
					</Card.Title>
				</Card.Header>

				<Card.Content class="space-y-4">
					<Separator />

					<div class="space-y-2 text-sm text-muted-foreground">
						<p>
							Last checked:
							<span class="text-foreground">
								{checkedAt ? checkedAt.toLocaleString() : 'Not checked yet'}
							</span>
						</p>

						{#if error}
							<p class="text-destructive">Error: {error}</p>
						{/if}
					</div>
				</Card.Content>
			</Card.Root>
		</section>

		<div class="flex justify-end">
			<Button type="button" disabled={loading} onclick={loadStatus}>
				<RefreshCw class={['size-4', loading && 'animate-spin']} />
				Refresh
			</Button>
		</div>
	</div>
</main>
