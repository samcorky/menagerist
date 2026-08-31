<script lang="ts">
	import { Dialog } from 'bits-ui';
	import { X, ExternalLink, Check } from '@lucide/svelte';
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { captureController } from '$lib/capture.svelte.js';
	import {
		createNode,
		updateNode,
		listNodeTypes,
		createNodeType,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import AttributesEditor, {
		rowsToAttributes,
		type AttributeRow
	} from '$lib/components/attributes-editor.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';

	function slugify(s: string): string {
		return s
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-|-$/g, '');
	}

	// ── State ────────────────────────────────────────────────────────────────────
	let name = $state('');
	let selectedType = $state<string | null>(null);
	let saving = $state(false);
	let savedNodeId = $state<string | null>(null);

	// Layer 1 – type suggestions
	let allNodeTypes = $state<NodeTypeResponse[]>([]);
	let showNewTypeForm = $state(false);
	let newTypeLabel = $state('');
	let creatingType = $state(false);

	// Layer 2 – details (post-save)
	let description = $state('');
	let attrRows = $state<AttributeRow[]>([]);
	let autoSaving = $state(false);
	let saveTimer: ReturnType<typeof setTimeout> | undefined;

	// ── Derived ──────────────────────────────────────────────────────────────────
	let nameLower = $derived(name.toLowerCase());

	let matchingTypes = $derived(
		name.length === 0
			? []
			: allNodeTypes
					.filter((t) => t.slug.includes(nameLower) || t.label.toLowerCase().includes(nameLower))
					.slice(0, 6)
	);

	// ── Effects ──────────────────────────────────────────────────────────────────
	$effect(() => {
		if (captureController.open && allNodeTypes.length === 0) {
			listNodeTypes({ query: { limit: 200 } }).then((r) => {
				if (r.data) allNodeTypes = r.data;
			});
		}
	});

	// Auto-save Layer 2 fields after user stops typing
	$effect(() => {
		const desc = description;
		const rows = attrRows;
		if (!savedNodeId) return;
		clearTimeout(saveTimer);
		saveTimer = setTimeout(() => {
			void autoSave(desc, rows);
		}, 600);
		return () => clearTimeout(saveTimer);
	});

	// ── Actions ──────────────────────────────────────────────────────────────────
	async function save() {
		if (!name.trim() || saving) return;
		saving = true;
		const result = await createNode({
			body: { name: name.trim(), type: selectedType || null }
		});
		if (result.error || !result.data) {
			toast.error("Couldn't save", { description: errorMessage(result.error) });
			saving = false;
			return;
		}
		savedNodeId = result.data.id;
		captureController.notifyNodeCreated();
		saving = false;
	}

	async function autoSave(desc: string, rows: AttributeRow[]) {
		if (!savedNodeId) return;
		autoSaving = true;
		await updateNode({
			path: { node_id: savedNodeId },
			body: {
				description: desc || null,
				attributes: rowsToAttributes(rows)
			}
		});
		autoSaving = false;
	}

	async function selectType(slug: string) {
		if (selectedType === slug) {
			selectedType = null;
			return;
		}
		selectedType = slug;
		// If already saved with no type, patch it now
		if (savedNodeId) {
			await updateNode({ path: { node_id: savedNodeId }, body: { type: slug } });
		}
	}

	async function submitNewType() {
		if (!newTypeLabel.trim() || creatingType) return;
		creatingType = true;
		const slug = slugify(newTypeLabel.trim());
		const result = await createNodeType({ body: { slug, label: newTypeLabel.trim() } });
		if (result.error || !result.data) {
			toast.error("Couldn't create type", { description: errorMessage(result.error) });
			creatingType = false;
			return;
		}
		allNodeTypes = [...allNodeTypes, result.data];
		await selectType(slug);
		showNewTypeForm = false;
		newTypeLabel = '';
		creatingType = false;
	}

	async function openFullPage() {
		if (!savedNodeId) return;
		captureController.hide();
		await goto(resolve('/nodes/[id]', { id: savedNodeId }));
		resetState();
	}

	function close() {
		captureController.hide();
		resetState();
	}

	function resetState() {
		name = '';
		selectedType = null;
		savedNodeId = null;
		description = '';
		attrRows = [];
		showNewTypeForm = false;
		newTypeLabel = '';
		clearTimeout(saveTimer);
	}
</script>

<Dialog.Root
	open={captureController.open}
	onOpenChange={(v) => {
		if (!v) close();
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
		<Dialog.Content
			class="fixed right-0 bottom-0 left-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-2xl border-t bg-background p-6 shadow-xl sm:inset-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-full sm:max-w-lg sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border"
		>
			<!-- drag handle (mobile only) -->
			<div class="mx-auto mb-5 h-1.5 w-12 rounded-full bg-muted sm:hidden"></div>

			<div class="flex items-center justify-between">
				<Dialog.Title class="text-lg font-semibold">Quick capture</Dialog.Title>
				<button
					onclick={close}
					class="rounded-md p-1 text-muted-foreground hover:text-foreground"
					aria-label="Close"
				>
					<X class="size-4" />
				</button>
			</div>

			<!-- Layer 0: Name + Save -->
			<div class="mt-4 space-y-3">
				<div class="flex gap-2">
					<Input
						bind:value={name}
						placeholder="Name…"
						autofocus
						class="flex-1"
						onkeydown={(e) => {
							if (e.key === 'Enter' && !savedNodeId) void save();
						}}
						disabled={!!savedNodeId}
					/>
					{#if !savedNodeId}
						<Button onclick={save} disabled={!name.trim() || saving}>
							{saving ? 'Saving…' : 'Save'}
						</Button>
					{/if}
				</div>

				<!-- Layer 1: Type suggestions (shown when name is typed) -->
				{#if name.length > 0}
					<div class="space-y-2">
						{#if matchingTypes.length > 0 || selectedType}
							<div class="flex flex-wrap gap-1.5">
								{#each matchingTypes as nt (nt.slug)}
									<button
										onclick={() => selectType(nt.slug)}
										class="flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs transition-colors {selectedType ===
										nt.slug
											? 'border-primary bg-primary text-primary-foreground'
											: 'border-border bg-background hover:border-primary/50'}"
									>
										{#if selectedType === nt.slug}
											<Check class="size-3" />
										{/if}
										{nt.label}
									</button>
								{/each}
								{#if selectedType && !matchingTypes.find((t) => t.slug === selectedType)}
									<!-- Selected type not in matches (e.g. new type) — show it anyway -->
									<button
										onclick={() => (selectedType = null)}
										class="flex items-center gap-1 rounded-full border border-primary bg-primary px-2.5 py-0.5 text-xs text-primary-foreground"
									>
										<Check class="size-3" />
										{selectedType}
									</button>
								{/if}
							</div>
						{/if}

						{#if !showNewTypeForm}
							<button
								onclick={() => (showNewTypeForm = true)}
								class="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
							>
								+ New type
							</button>
						{:else}
							<form
								class="flex gap-2"
								onsubmit={(e) => {
									e.preventDefault();
									void submitNewType();
								}}
							>
								<Input
									bind:value={newTypeLabel}
									placeholder="Type label…"
									class="h-7 flex-1 text-xs"
									autofocus
								/>
								<Button type="submit" size="sm" disabled={!newTypeLabel.trim() || creatingType}>
									{creatingType ? '…' : 'Create'}
								</Button>
								<Button
									type="button"
									size="sm"
									variant="ghost"
									onclick={() => {
										showNewTypeForm = false;
										newTypeLabel = '';
									}}
								>
									Cancel
								</Button>
							</form>
						{/if}
					</div>
				{/if}

				<!-- Layer 2: Details (only after save) -->
				{#if savedNodeId}
					<details class="border-t pt-3">
						<summary
							class="cursor-pointer text-sm text-muted-foreground select-none hover:text-foreground"
						>
							More details
						</summary>
						<div class="mt-3 space-y-4">
							<div class="space-y-1.5">
								<Label>Description</Label>
								<Textarea
									bind:value={description}
									placeholder="Optional description…"
									class="min-h-[80px]"
								/>
							</div>
							<AttributesEditor bind:rows={attrRows} />
							{#if autoSaving}
								<p class="text-xs text-muted-foreground">Saving…</p>
							{/if}
						</div>
					</details>

					<!-- Footer: post-save actions -->
					<div class="flex items-center justify-between border-t pt-3">
						<button
							onclick={openFullPage}
							class="flex items-center gap-1 text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
						>
							<ExternalLink class="size-3.5" />
							Open full page
						</button>
						<Button onclick={close} variant="secondary" size="sm">Done</Button>
					</div>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
