<script lang="ts">
	import { tick } from 'svelte';
	import { Pencil } from '@lucide/svelte';
	import IconButton from '$lib/components/icon-button.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	/** The longest device name the server accepts. */
	const MAX_LENGTH = 60;

	let {
		title,
		subtitle = null,
		name = null,
		label,
		userAgent = null,
		onsave
	}: {
		title: string;
		/** The generated label, shown muted under a name. */
		subtitle?: string | null;
		name?: string | null;
		/** The generated label, offered as the starting text when naming. */
		label: string;
		userAgent?: string | null;
		/** Save a new name (`null` clears it). Omit where the device cannot be renamed. Resolves true on success. */
		onsave?: (name: string | null) => Promise<boolean>;
	} = $props();

	let editing = $state(false);
	let draft = $state('');
	let saving = $state(false);
	let input = $state<HTMLInputElement | null>(null);

	async function start() {
		draft = name ?? '';
		editing = true;
		await tick();
		input?.focus();
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!onsave || saving) return;
		saving = true;
		const saved = await onsave(draft.trim() === '' ? null : draft.trim());
		saving = false;
		if (saved) editing = false;
	}
</script>

{#if editing}
	<form class="flex flex-wrap items-center gap-2" onsubmit={save}>
		<Input
			bind:ref={input}
			bind:value={draft}
			class="h-9 w-56 max-w-full"
			maxlength={MAX_LENGTH}
			placeholder={label}
			aria-label="Device name"
			onkeydown={(e) => {
				if (e.key === 'Escape') editing = false;
			}}
		/>
		<Button type="submit" size="sm" disabled={saving}>
			{#if saving}<Spinner class="size-4" />{/if}
			Save
		</Button>
		<Button type="button" size="sm" variant="ghost" onclick={() => (editing = false)}>
			Cancel
		</Button>
	</form>
{:else}
	<div class="flex min-w-0 items-center gap-1">
		<div class="min-w-0">
			<p class="truncate font-medium" title={userAgent ?? undefined} data-testid="device-title">
				{title}
			</p>
			{#if subtitle}
				<p class="truncate text-xs text-muted-foreground" data-testid="device-subtitle">
					{subtitle}
				</p>
			{/if}
		</div>
		{#if onsave}
			<IconButton
				label={name ? 'Rename device' : 'Name device'}
				labelOnTouch={false}
				class="size-8 shrink-0"
				onclick={start}
			>
				<Pencil class="size-4" />
			</IconButton>
		{/if}
	</div>
{/if}
