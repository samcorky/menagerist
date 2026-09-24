<script lang="ts">
	import { BookmarkPlus, Plus, X } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { getContext, untrack } from 'svelte';
	import {
		countEdgeTypeAttributeUsage,
		countNodeTypeAttributeUsage,
		getPreset
	} from '$lib/api/client';
	import { optionRemovalWarning } from '$lib/field-usage';
	import { SCHEMA_TYPE_CONTEXT, type SchemaTypeContext } from '$lib/schema-type-context';
	import type { EditorField } from '$lib/schema-types';
	import { listUpdateAvailable, optionsToDefinition, type Origin, type Preset } from '$lib/presets';
	import SavePresetDialog from '$lib/components/save-preset-dialog.svelte';
	import PresetPickerDialog from '$lib/components/preset-picker-dialog.svelte';

	let {
		field,
		onChange
	}: {
		field: EditorField;
		onChange: (f: EditorField) => void;
	} = $props();

	const ctx = getContext<SchemaTypeContext | undefined>(SCHEMA_TYPE_CONTEXT);

	let draft = $state('');
	let removalWarning = $state<string | null>(null);
	let removalRequest = 0;

	function addOption() {
		const trimmed = draft.trim();
		if (!trimmed || field.options.includes(trimmed)) {
			draft = '';
			return;
		}
		removalRequest++;
		removalWarning = null;
		onChange({ ...field, options: [...field.options, trimmed] });
		draft = '';
	}

	/** In-use warning for one option, or null. Advisory only; failures are ignored. */
	async function optionUsageWarning(opt: string): Promise<string | null> {
		const typeId = ctx?.typeId;
		if (!ctx || !typeId || field.keyPending) return null;
		const kind = ctx.kind;
		try {
			const result =
				kind === 'node'
					? await countNodeTypeAttributeUsage({
							path: { node_type_id: typeId, key: field.key },
							query: { value: opt }
						})
					: await countEdgeTypeAttributeUsage({
							path: { edge_type_id: typeId, key: field.key },
							query: { value: opt }
						});
			const count = result.data?.count ?? 0;
			return count > 0 ? optionRemovalWarning(opt, count, kind) : null;
		} catch {
			return null;
		}
	}

	async function removeOption(opt: string) {
		const request = ++removalRequest;
		removalWarning = null;
		onChange({ ...field, options: field.options.filter((o) => o !== opt) });
		const warning = await optionUsageWarning(opt);
		if (request === removalRequest && warning) removalWarning = warning;
	}

	// Saved-list linking: "save these options" and "use a saved list" / update flow.
	let savePresetOpen = $state(false);
	let pickerOpen = $state(false);
	let linkedPreset = $state<Preset | undefined>(undefined);
	let updating = $state(false);

	const origin = $derived(field.meta?.origin as Origin | undefined);
	const updateAvailable = $derived(listUpdateAvailable(field, linkedPreset));

	$effect(() => {
		const presetId = origin?.preset;
		if (!presetId) {
			untrack(() => (linkedPreset = undefined));
			return;
		}
		void getPreset({ path: { preset_id: presetId } }).then((result) => {
			if (result.data) linkedPreset = result.data as unknown as Preset;
		});
	});

	function useSavedList(preset: Preset) {
		const options = (preset.definition as { options: string[] }).options;
		onChange({
			...field,
			options,
			meta: { ...field.meta, origin: { preset: preset.id, version: preset.version } }
		});
	}

	async function updateFromPreset() {
		if (!linkedPreset) return;
		updating = true;
		const nextOptions = (linkedPreset.definition as { options: string[] }).options;
		const removed = field.options.filter((o) => !nextOptions.includes(o));
		const warnings = (await Promise.all(removed.map((o) => optionUsageWarning(o)))).filter(
			(w): w is string => w !== null
		);
		onChange({
			...field,
			options: nextOptions,
			meta: {
				...field.meta,
				origin: { preset: linkedPreset.id, version: linkedPreset.version }
			}
		});
		removalWarning = warnings.length > 0 ? warnings.join(' ') : null;
		updating = false;
	}
</script>

<div class="mt-1.5 ml-4 space-y-1.5 border-l border-input pl-3">
	<p class="text-xs text-muted-foreground">Options</p>
	{#if field.options.length > 0}
		<ul class="flex flex-wrap gap-1">
			{#each field.options as opt (opt)}
				<li>
					<Badge variant="secondary" class="pr-1">
						<span class="max-w-32 truncate" title={opt}>{opt}</span>
						<button
							type="button"
							onclick={() => removeOption(opt)}
							aria-label="Remove option {opt}"
							class="relative ml-1 rounded-full p-0.5 after:absolute after:-inset-2 after:content-[''] hover:bg-foreground/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
						>
							<X class="size-3" />
						</button>
					</Badge>
				</li>
			{/each}
		</ul>
	{/if}
	<div class="flex gap-1.5">
		<Input
			bind:value={draft}
			placeholder="Add option…"
			class="h-7 w-36 text-xs"
			onkeydown={(e) => {
				if (e.key === 'Enter') {
					e.preventDefault();
					addOption();
				}
			}}
		/>
		<Button type="button" variant="ghost" size="sm" class="h-7 px-2" onclick={addOption}>
			<Plus class="size-3" />
		</Button>
	</div>
	{#if removalWarning}
		<p class="text-xs text-muted-foreground" role="status">{removalWarning}</p>
	{/if}

	<div class="flex flex-wrap items-center gap-2">
		<Button
			type="button"
			variant="ghost"
			size="sm"
			class="h-7 text-xs"
			disabled={field.options.length === 0}
			onclick={() => (savePresetOpen = true)}
		>
			<BookmarkPlus class="size-3" />
			Save these options as a list
		</Button>
		{#if !origin}
			<Button
				type="button"
				variant="ghost"
				size="sm"
				class="h-7 text-xs"
				onclick={() => (pickerOpen = true)}
			>
				Use a saved list
			</Button>
		{/if}
	</div>

	{#if origin && updateAvailable}
		<div class="flex flex-wrap items-center gap-2">
			<p class="text-xs text-muted-foreground" role="status">Update available</p>
			<Button
				type="button"
				variant="ghost"
				size="sm"
				class="h-7 text-xs"
				disabled={updating}
				onclick={updateFromPreset}
			>
				{updating ? 'Updating…' : 'Update options'}
			</Button>
		</div>
	{/if}
</div>

<SavePresetDialog
	open={savePresetOpen}
	kind="choice_list"
	definition={optionsToDefinition(field.options)}
	onOpenChange={(v) => (savePresetOpen = v)}
	onSaved={() => {}}
/>

<PresetPickerDialog
	open={pickerOpen}
	kind="choice_list"
	title="Use a saved list"
	onOpenChange={(v) => (pickerOpen = v)}
	onPick={useSavedList}
/>
