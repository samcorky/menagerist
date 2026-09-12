<script lang="ts">
	import { Upload } from '@lucide/svelte';

	let {
		onFiles,
		ref = $bindable(null)
	}: {
		onFiles: (files: FileList | File[]) => void;
		ref?: HTMLDivElement | null;
	} = $props();

	let dragOver = $state(false);
	let fileInputEl = $state<HTMLInputElement | null>(null);

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		if (e.dataTransfer?.files) onFiles(e.dataTransfer.files);
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		if (input.files) onFiles(input.files);
		input.value = '';
	}
</script>

<div
	bind:this={ref}
	role="button"
	tabindex="0"
	class="relative flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed py-6 text-sm transition-colors {dragOver
		? 'border-primary bg-primary/5'
		: 'border-border hover:border-primary/50 hover:bg-muted/40'}"
	ondragover={(e) => {
		e.preventDefault();
		dragOver = true;
	}}
	ondragleave={() => (dragOver = false)}
	ondrop={handleDrop}
	onclick={() => fileInputEl?.click()}
	onkeydown={(e) => e.key === 'Enter' && fileInputEl?.click()}
>
	<Upload class="size-5 text-muted-foreground" />
	<span class="text-muted-foreground">
		Drop files here or <span class="text-foreground underline underline-offset-2">browse</span>
	</span>
	<input bind:this={fileInputEl} type="file" multiple class="sr-only" onchange={handleFileInput} />
</div>
