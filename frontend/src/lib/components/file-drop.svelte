<script lang="ts">
	import { Camera, Images, Upload } from '@lucide/svelte';
	import { coarsePointer } from '$lib/viewport.svelte';
	import { Button } from '$lib/components/ui/button/index.js';

	let {
		onFiles,
		multiple = true,
		accept,
		disabled = false,
		id,
		label,
		camera = false,
		ref = $bindable(null)
	}: {
		onFiles: (files: FileList | File[]) => void;
		multiple?: boolean;
		accept?: string;
		disabled?: boolean;
		id?: string;
		/** Replaces the default "Drop files here or browse" wording. */
		label?: string;
		/**
		 * For photos: on a touch screen, offer "Take a photo" (the camera) beside "Choose a photo"
		 * (the gallery or files). Elsewhere `capture` does nothing, so the drop zone stays.
		 */
		camera?: boolean;
		ref?: HTMLDivElement | null;
	} = $props();

	let dragOver = $state(false);
	let fileInputEl = $state<HTMLInputElement | null>(null);
	let cameraInputEl = $state<HTMLInputElement | null>(null);
	let galleryInputEl = $state<HTMLInputElement | null>(null);

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		if (disabled) return;
		if (e.dataTransfer?.files) {
			onFiles(multiple ? e.dataTransfer.files : Array.from(e.dataTransfer.files).slice(0, 1));
		}
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		if (input.files) onFiles(input.files);
		input.value = '';
	}
</script>

{#if camera && coarsePointer.current}
	<div bind:this={ref} role="group" aria-label={label ?? 'Add a photo'} class="flex gap-2">
		<Button
			type="button"
			variant="outline"
			class="flex-1 pointer-coarse:h-11"
			{disabled}
			onclick={() => cameraInputEl?.click()}
		>
			<Camera data-icon="inline-start" />
			Take a photo
		</Button>
		<Button
			type="button"
			variant="outline"
			class="flex-1 pointer-coarse:h-11"
			{disabled}
			onclick={() => galleryInputEl?.click()}
		>
			<Images data-icon="inline-start" />
			Choose a photo
		</Button>
		<!-- `capture` opens the camera at once; many phones then cannot pick an existing photo. -->
		<input
			bind:this={cameraInputEl}
			type="file"
			accept="image/*"
			capture="environment"
			tabindex="-1"
			aria-hidden="true"
			class="hidden"
			onchange={handleFileInput}
		/>
		<input
			bind:this={galleryInputEl}
			type="file"
			accept="image/*"
			tabindex="-1"
			aria-hidden="true"
			class="hidden"
			onchange={handleFileInput}
		/>
	</div>
{:else}
	<div
		bind:this={ref}
		role="button"
		aria-disabled={disabled}
		tabindex={disabled ? -1 : 0}
		class="relative flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed py-6 text-sm transition-colors {dragOver
			? 'border-primary bg-primary/5'
			: 'border-border hover:border-primary/50 hover:bg-muted/40'}"
		ondragover={(e) => {
			e.preventDefault();
			dragOver = !disabled;
		}}
		ondragleave={() => (dragOver = false)}
		ondrop={handleDrop}
		onkeydown={(e) => !disabled && e.key === 'Enter' && fileInputEl?.click()}
	>
		<Upload class="size-5 text-muted-foreground" />
		<span class="text-muted-foreground">
			{#if label}
				<span class="text-foreground underline underline-offset-2">{label}</span>
			{:else}
				Drop {multiple ? 'files' : 'a file'} here or
				<span class="text-foreground underline underline-offset-2">browse</span>
			{/if}
		</span>
		<input
			bind:this={fileInputEl}
			{id}
			type="file"
			{multiple}
			{accept}
			{disabled}
			tabindex="-1"
			class="absolute inset-0 h-full w-full cursor-pointer opacity-0"
			onchange={handleFileInput}
		/>
	</div>
{/if}
