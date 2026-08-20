<script lang="ts">
	import { BadgeCheck, RefreshCw, Server, TriangleAlert } from '@lucide/svelte';
	import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

	type VersionResponse = {
		current_version: string;
	};

	let version = $state<string | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(false);
	let checkedAt = $state<Date | null>(null);

	const apiBaseUrl = 'http://localhost:8000/api';

	async function loadStatus() {
		loading = true;
		error = null;

		try {
			const response = await fetch(`${apiBaseUrl}/version`);

			if (!response.ok) {
				throw new Error(`API returned ${response.status}`);
			}

			const data = (await response.json()) as VersionResponse;
			version = data.current_version;
			checkedAt = new Date();
		} catch (cause) {
			version = null;
			error = cause instanceof Error ? cause.message : 'Unable to reach the API';
			checkedAt = new Date();
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void loadStatus();
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

		{#if error}
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
							{#if loading}
								Checking…
							{:else if error}
								Unavailable
							{:else}
								Operational
							{/if}
						</Card.Title>
					</div>

					<div
						class={[
							'rounded-full border p-3',
							error
								? 'border-destructive/30 bg-destructive/10 text-destructive'
								: 'border-green-500/30 bg-green-500/10 text-green-600'
						]}
					>
						{#if error}
							<TriangleAlert class="size-5" />
						{:else}
							<BadgeCheck class="size-5" />
						{/if}
					</div>
				</Card.Header>

				<Card.Content>
					<div class="rounded-lg bg-muted p-4">
						<p class="text-sm text-muted-foreground">Endpoint</p>
						<p class="mt-1 font-mono text-sm">GET /api/version</p>
					</div>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Description>Application version</Card.Description>

					<Card.Title>
						{#if loading}
							<Skeleton class="h-8 w-32" />
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
