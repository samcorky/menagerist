<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { errorMessage } from '$lib/api/errors';
	import FileDrop from '$lib/components/file-drop.svelte';
	import TypeIcon from '$lib/components/type-icon.svelte';
	import { uploadCover } from '$lib/node-cover-upload';

	// Stands in for a missing cover: the item's type icon and colour, and a way to add a photo.
	let {
		nodeId,
		icon,
		colour,
		onuploaded
	}: {
		nodeId: string;
		icon?: string | null;
		colour?: string | null;
		onuploaded?: () => void;
	} = $props();

	let busy = $state(false);

	async function add(files: FileList | File[]) {
		const file = Array.from(files).find((f) => f.type.startsWith('image/'));
		if (!file) {
			toast.error('Choose an image to use as the cover');
			return;
		}
		busy = true;
		const result = await uploadCover(nodeId, file);
		busy = false;
		if (result.error || !result.data) {
			toast.error("Couldn't add the photo", { description: errorMessage(result.error) });
			return;
		}
		onuploaded?.();
	}
</script>

<div data-testid="cover-placeholder" class="space-y-2">
	<div
		class="flex aspect-[4/3] items-center justify-center rounded-xl border bg-muted/30 lg:aspect-[3/4]"
	>
		<TypeIcon {icon} {colour} boxed class="size-24 rounded-3xl text-6xl" />
	</div>
	<FileDrop onFiles={add} multiple={false} accept="image/*" label="Add a photo" disabled={busy} />
</div>
