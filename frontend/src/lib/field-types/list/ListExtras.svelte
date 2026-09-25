<script lang="ts">
	import type { EditorField } from '$lib/schema-types';

	let {
		field,
		onChange
	}: {
		field: EditorField;
		onChange: (f: EditorField) => void;
	} = $props();

	function toggleMultiline(checked: boolean) {
		const meta = { ...field.meta };
		if (checked) meta.multiline = true;
		else delete meta.multiline;
		onChange({ ...field, meta });
	}
</script>

<label class="ml-2 flex items-center gap-1.5 text-xs text-muted-foreground">
	<input
		type="checkbox"
		checked={field.meta?.multiline === true}
		onchange={(e) => toggleMultiline((e.target as HTMLInputElement).checked)}
		class="h-4 w-4 rounded border-input accent-primary"
	/>
	Multi-line items
</label>
