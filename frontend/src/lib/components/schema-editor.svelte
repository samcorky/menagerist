<script lang="ts" module>
	export type SchemaField = {
		key: string;
		label: string;
		type: 'text' | 'number' | 'boolean' | 'date' | 'select' | 'richtext' | 'group';
		required: boolean;
		options?: string[];
		groupFields?: SubField[];
	};

	export type SubField = Omit<SchemaField, 'type'> & {
		type: Exclude<SchemaField['type'], 'group'>;
	};

	export type Schema = { fields: SchemaField[] };
</script>

<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { slugify } from '$lib/utils.js';

	let { schema = $bindable<Schema | null>(null) }: { schema?: Schema | null } = $props();

	let fields = $state<SchemaField[]>(schema?.fields ?? []);

	$effect(() => {
		schema = { fields };
	});

	function addField() {
		fields = [...fields, { key: '', label: '', type: 'text', required: false }];
	}

	function removeField(index: number) {
		fields = fields.filter((_, i) => i !== index);
	}

	function handleLabelChange(index: number, value: string) {
		fields = fields.map((f, i) => {
			if (i !== index) return f;
			// Lock the key once set — only derive on first non-empty label
			return { ...f, label: value, key: f.key || slugify(value) };
		});
	}

	function addSubField(field: SchemaField) {
		field.groupFields = [
			...(field.groupFields ?? []),
			{ key: '', label: '', type: 'text', required: false }
		];
	}

	function removeSubField(field: SchemaField, index: number) {
		field.groupFields = (field.groupFields ?? []).filter((_, i) => i !== index);
	}

	function handleSubFieldLabelChange(field: SchemaField, index: number, value: string) {
		field.groupFields = (field.groupFields ?? []).map((f, i) => {
			if (i !== index) return f;
			return { ...f, label: value, key: f.key || slugify(value) };
		});
	}
</script>

{#snippet fieldRow(
	field: SchemaField,
	allowGroup: boolean,
	onLabelChange: (value: string) => void,
	onRemove: () => void
)}
	<div class="flex flex-wrap items-center gap-2">
		<Input
			value={field.label}
			placeholder="Label"
			class="w-40"
			aria-label="Field label"
			oninput={(e) => onLabelChange((e.target as HTMLInputElement).value)}
		/>
		<select
			bind:value={field.type}
			class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
			aria-label="Field kind"
		>
			<option value="text">Text</option>
			<option value="number">Number</option>
			<option value="boolean">Yes/No</option>
			<option value="date">Date</option>
			<option value="select">Choice</option>
			<option value="richtext">Long text</option>
			{#if allowGroup}
				<option value="group">Group</option>
			{/if}
		</select>
		<label class="flex items-center gap-1.5 text-sm">
			<input
				type="checkbox"
				bind:checked={field.required}
				class="h-4 w-4 rounded border-input accent-primary"
			/>
			Required
		</label>
		<Button type="button" variant="ghost" size="icon" onclick={onRemove} aria-label="Remove field">
			<X class="size-4" />
		</Button>
	</div>

	{#if allowGroup && field.type === 'group'}
		<div class="ml-6 space-y-2 border-l border-input pl-4">
			{#each field.groupFields ?? [] as subField, si (si)}
				{@render fieldRow(
					subField,
					false,
					(value) => handleSubFieldLabelChange(field, si, value),
					() => removeSubField(field, si)
				)}
			{/each}
			<Button type="button" variant="outline" size="sm" onclick={() => addSubField(field)}>
				<Plus class="size-4" />
				Add sub-field
			</Button>
		</div>
	{/if}
{/snippet}

<div class="space-y-3">
	<Label>Fields</Label>

	{#each fields as field, i (i)}
		{@render fieldRow(
			field,
			true,
			(value) => handleLabelChange(i, value),
			() => removeField(i)
		)}
	{/each}

	<Button type="button" variant="outline" size="sm" onclick={addField}>
		<Plus class="size-4" />
		Add field
	</Button>
</div>
