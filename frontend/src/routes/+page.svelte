<script lang="ts">
	import { RefreshCw, Server, BadgeCheck, TriangleAlert } from '@lucide/svelte';

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
			<div
				class="inline-flex w-fit items-center gap-2 rounded-full border bg-card px-3 py-1 text-sm text-muted-foreground"
			>
				<Server class="size-4" />
				System status
			</div>

			<div class="space-y-2">
				<h1 class="text-4xl font-semibold tracking-tight">Service health</h1>
				<p class="max-w-2xl text-muted-foreground">
					POC dashboard for checking API reachability and the currently deployed backend version.
				</p>
			</div>
		</section>

		<section class="grid gap-4 md:grid-cols-2">
			<div class="rounded-xl border bg-card p-6 text-card-foreground shadow-sm">
				<div class="flex items-start justify-between gap-4">
					<div class="space-y-1">
						<p class="text-sm font-medium text-muted-foreground">API status</p>

						{#if loading}
							<h2 class="text-2xl font-semibold">Checking…</h2>
						{:else if error}
							<h2 class="text-2xl font-semibold text-destructive">Unavailable</h2>
						{:else}
							<h2 class="text-2xl font-semibold">Operational</h2>
						{/if}
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
				</div>

				<div class="mt-6 rounded-lg bg-muted p-4">
					<p class="text-sm text-muted-foreground">Endpoint</p>
					<p class="mt-1 font-mono text-sm">GET /version</p>
				</div>
			</div>

			<div class="rounded-xl border bg-card p-6 text-card-foreground shadow-sm">
				<div class="space-y-1">
					<p class="text-sm font-medium text-muted-foreground">Application version</p>

					{#if loading}
						<div class="mt-3 h-8 w-32 animate-pulse rounded-md bg-muted"></div>
					{:else if version}
						<h2 class="text-2xl font-semibold">{version}</h2>
					{:else}
						<h2 class="text-2xl font-semibold text-muted-foreground">Unknown</h2>
					{/if}
				</div>

				<div class="mt-6 space-y-2 text-sm text-muted-foreground">
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
			</div>
		</section>

		<div class="flex justify-end">
			<button
				type="button"
				class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
				disabled={loading}
				onclick={loadStatus}
			>
				<RefreshCw class={['size-4', loading && 'animate-spin']} />
				Refresh
			</button>
		</div>
	</div>
</main>
