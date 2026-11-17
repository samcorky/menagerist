<script lang="ts">
	import { Cat, ImageUp, Type } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { clearOwnAvatar, setOwnAvatar, setOwnAvatarFromCatService } from '$lib/api/client';
	import { uploadErrorMessage } from '$lib/api/errors';
	import type { Crop } from '$lib/avatars/crop-geometry';
	import { drawnCatPng } from '$lib/avatars/drawn-cat';
	import { auth } from '$lib/auth.svelte.js';
	import AvatarCropper from '$lib/components/avatar-cropper.svelte';
	import UserAvatar from '$lib/components/user-avatar.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	const MAX_BYTES = 5 * 1024 * 1024;
	const ACCEPT = 'image/jpeg,image/png,image/webp,image/gif';
	const UNUSABLE = "That file can't be used as a picture.";

	type Busy = 'upload' | 'cat' | 'clear' | null;

	let busy = $state<Busy>(null);
	let cropFile = $state<File | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);
	let uploadButton = $state<HTMLButtonElement | null>(null);

	const user = $derived(auth.user);
	// Busy buttons stay focusable (aria-disabled), so focus never drops to the page.
	const busyClass = $derived(
		busy === null ? 'pointer-coarse:h-11' : 'pointer-coarse:h-11 opacity-50'
	);

	type Result = {
		data?: unknown;
		error?: unknown;
		response?: Response | null;
	};

	/** Show the returned account, or explain what went wrong; true when it worked. */
	function settle(result: Result, failure: string): boolean {
		if (result.data && !result.error) {
			auth.adoptUser(result.data as NonNullable<typeof auth.user>);
			return true;
		}
		const message =
			result.response?.status === 400 && !hasDetail(result.error)
				? UNUSABLE
				: uploadErrorMessage(result);
		toast.error(failure, { description: message });
		return false;
	}

	function hasDetail(error: unknown): boolean {
		return (
			!!error &&
			typeof error === 'object' &&
			typeof (error as { detail?: unknown }).detail === 'string'
		);
	}

	function chooseFile(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0] ?? null;
		input.value = '';
		if (!file) return;
		if (file.size > MAX_BYTES) {
			toast.error("Couldn't use that picture", {
				description: 'A picture must be 5 MB or smaller.'
			});
			return;
		}
		cropFile = file;
	}

	async function upload(
		file: Blob,
		crop: Crop | null,
		source: 'upload' | 'drawn'
	): Promise<boolean> {
		const result = await setOwnAvatar({
			body: {
				file,
				source,
				...(crop ? { crop_x: crop.x, crop_y: crop.y, crop_size: crop.size } : {})
			}
		});
		return settle(result, "Couldn't change your picture");
	}

	async function saveCrop(crop: Crop | null) {
		const file = cropFile;
		if (!file || busy) return;
		busy = 'upload';
		try {
			if (await upload(file, crop, 'upload')) {
				cropFile = null;
				toast.success('Picture updated');
			} else if (crop === null) {
				// The cropper could not open the file, so there is nothing to adjust and retry.
				cropFile = null;
			}
		} finally {
			busy = null;
		}
	}

	async function randomCat() {
		if (busy) return;
		busy = 'cat';
		try {
			const result = await setOwnAvatarFromCatService();
			if (result.response?.status !== 503) {
				settle(result, "Couldn't fetch a cat");
				return;
			}
			// The service is off or unreachable: draw one here and upload it instead.
			let drawn: Blob;
			try {
				drawn = await drawnCatPng();
			} catch {
				toast.error("Couldn't draw a cat", { description: 'Try uploading a picture instead.' });
				return;
			}
			if (await upload(drawn, null, 'drawn')) {
				toast("The cat service isn't available, so here's a drawn cat.");
			}
		} finally {
			busy = null;
		}
	}

	async function useInitials() {
		if (busy) return;
		busy = 'clear';
		try {
			if (settle(await clearOwnAvatar(), "Couldn't remove your picture")) {
				toast.success('Showing your initials');
				// Use initials has just gone away; keep focus in the section.
				uploadButton?.focus();
			}
		} finally {
			busy = null;
		}
	}
</script>

{#if user}
	<section class="max-w-md space-y-4" aria-labelledby="account-picture-heading">
		<h2 id="account-picture-heading" class="font-heading text-lg font-semibold">Picture</h2>
		<div class="flex flex-col gap-4 sm:flex-row sm:items-center">
			<UserAvatar
				userId={user.id}
				displayName={user.display_name}
				avatarVersion={user.avatar_version}
				size="xl"
			/>
			<div class="flex min-w-0 flex-1 flex-wrap gap-2">
				<input
					bind:this={fileInput}
					type="file"
					accept={ACCEPT}
					class="sr-only"
					tabindex="-1"
					aria-hidden="true"
					onchange={chooseFile}
				/>
				<Button
					bind:ref={uploadButton}
					variant="outline"
					class={busyClass}
					aria-disabled={busy !== null}
					onclick={() => {
						if (!busy) fileInput?.click();
					}}
				>
					<ImageUp class="size-4" />
					Upload picture
				</Button>
				<Button
					variant="outline"
					class={busyClass}
					aria-disabled={busy !== null}
					aria-busy={busy === 'cat'}
					onclick={randomCat}
				>
					{#if busy === 'cat'}<Spinner class="size-4" />{:else}<Cat class="size-4" />{/if}
					Random cat
				</Button>
				{#if user.avatar_version}
					<Button
						variant="ghost"
						class={busyClass}
						aria-disabled={busy !== null}
						onclick={useInitials}
					>
						{#if busy === 'clear'}<Spinner class="size-4" />{:else}<Type class="size-4" />{/if}
						Use initials
					</Button>
				{/if}
			</div>
		</div>
		<p class="text-xs text-muted-foreground">
			JPEG, PNG, WebP or GIF, up to 5 MB. Everyone signed in to this server can see it.
		</p>
	</section>

	<ResponsiveDialog.Root
		open={cropFile !== null}
		onOpenChange={(open) => {
			if (!open && busy !== 'upload') cropFile = null;
		}}
	>
		<ResponsiveDialog.Content title="Crop your picture" size="sm">
			{#if cropFile}
				<div class="mt-4">
					<AvatarCropper
						file={cropFile}
						busy={busy === 'upload'}
						onsave={(crop) => void saveCrop(crop)}
						oncancel={() => (cropFile = null)}
					/>
				</div>
			{/if}
		</ResponsiveDialog.Content>
	</ResponsiveDialog.Root>
{/if}
