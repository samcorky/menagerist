<script lang="ts">
	import { onDestroy } from 'svelte';
	import { Minus, Plus } from '@lucide/svelte';
	import {
		MAX_ZOOM,
		cropSquare,
		initialView,
		nudge,
		pan,
		zoomTo,
		type Crop,
		type CropView,
		type Direction
	} from '$lib/avatars/crop-geometry';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	type Props = {
		file: File;
		busy?: boolean;
		/** The square to keep, or `null` when this browser cannot open the file. */
		onsave: (crop: Crop | null) => void;
		oncancel: () => void;
	};

	let { file, busy = false, onsave, oncancel }: Props = $props();

	let bitmap = $state.raw<ImageBitmap | null>(null);
	let view = $state<CropView>({ zoom: 1, centreX: 0, centreY: 0 });
	let canvas = $state<HTMLCanvasElement | null>(null);
	let drag: { pointerId: number; x: number; y: number } | null = null;

	const width = $derived(bitmap?.width ?? 1);
	const height = $derived(bitmap?.height ?? 1);
	const crop = $derived(cropSquare(view, width, height));

	$effect(() => {
		let cancelled = false;
		// The same upright image the server crops: EXIF orientation applied.
		createImageBitmap(file, { imageOrientation: 'from-image' })
			.then((loaded) => {
				if (cancelled) return loaded.close();
				bitmap = loaded;
				view = initialView(loaded.width, loaded.height);
			})
			.catch(() => {
				// Undecodable here; the server centres the crop or explains why it can't.
				if (!cancelled) onsave(null);
			});
		return () => {
			cancelled = true;
		};
	});

	$effect(() => {
		if (!canvas || !bitmap) return;
		const shown = canvas.clientWidth || 288;
		const scale = Math.max(1, Math.round(window.devicePixelRatio || 1));
		canvas.width = shown * scale;
		canvas.height = shown * scale;
		const context = canvas.getContext('2d');
		if (!context) return;
		context.imageSmoothingQuality = 'high';
		context.drawImage(
			bitmap,
			crop.x,
			crop.y,
			crop.size,
			crop.size,
			0,
			0,
			canvas.width,
			canvas.height
		);
	});

	onDestroy(() => bitmap?.close());

	/** Natural pixels per CSS pixel of the stage. */
	function ratio(): number {
		return crop.size / (canvas?.clientWidth || 288);
	}

	function onpointerdown(event: PointerEvent) {
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		drag = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
	}

	function onpointermove(event: PointerEvent) {
		if (!drag || drag.pointerId !== event.pointerId) return;
		const factor = ratio();
		// Dragging the picture right shows more of its left side.
		view = pan(
			view,
			-(event.clientX - drag.x) * factor,
			-(event.clientY - drag.y) * factor,
			width,
			height
		);
		drag = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
	}

	function onpointerup(event: PointerEvent) {
		if (drag?.pointerId === event.pointerId) drag = null;
	}

	function onwheel(event: WheelEvent) {
		event.preventDefault();
		view = zoomTo(view, view.zoom * Math.pow(1.1, -event.deltaY / 100), width, height);
	}

	// Svelte attaches `onwheel` as passive, which cannot stop the page scrolling.
	function wheelZoom(node: HTMLElement) {
		node.addEventListener('wheel', onwheel, { passive: false });
		return () => node.removeEventListener('wheel', onwheel);
	}

	const ARROWS: Record<string, Direction> = {
		ArrowUp: 'up',
		ArrowDown: 'down',
		ArrowLeft: 'left',
		ArrowRight: 'right'
	};

	function onkeydown(event: KeyboardEvent) {
		const direction = ARROWS[event.key];
		if (direction) {
			event.preventDefault();
			// Arrows move the picture under the frame, the way dragging does.
			const opposite: Record<Direction, Direction> = {
				up: 'down',
				down: 'up',
				left: 'right',
				right: 'left'
			};
			view = nudge(view, opposite[direction], event.shiftKey, width, height);
		} else if (event.key === '+' || event.key === '=') {
			event.preventDefault();
			view = zoomTo(view, view.zoom * 1.25, width, height);
		} else if (event.key === '-') {
			event.preventDefault();
			view = zoomTo(view, view.zoom / 1.25, width, height);
		}
	}
</script>

<div class="space-y-4">
	<div class="relative mx-auto aspect-square w-full max-w-72 overflow-hidden rounded-md bg-muted">
		{#if bitmap}
			<button
				type="button"
				class="peer block size-full cursor-grab touch-none rounded-md outline-none active:cursor-grabbing"
				aria-label="Picture crop area. Drag or use the arrow keys to move the picture; plus and minus zoom."
				{onpointerdown}
				{onpointermove}
				{onpointerup}
				onpointercancel={onpointerup}
				{@attach wheelZoom}
				{onkeydown}
			>
				<canvas bind:this={canvas} class="size-full" aria-hidden="true"></canvas>
			</button>
			<!-- Dims everything outside the circle people will see; also draws the crop area's focus ring, above the dimming. -->
			<div
				class="pointer-events-none absolute inset-0 rounded-full shadow-[0_0_0_9999px_rgb(0_0_0/0.45)] peer-focus-visible:ring-3 peer-focus-visible:ring-ring"
				aria-hidden="true"
			></div>
		{:else}
			<div class="flex size-full items-center justify-center">
				<Spinner class="size-6" />
			</div>
		{/if}
	</div>

	<div class="flex items-center gap-2">
		<Minus class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
		<input
			type="range"
			min="1"
			max={MAX_ZOOM}
			step="0.01"
			value={view.zoom}
			disabled={!bitmap}
			aria-label="Zoom"
			class="h-7 w-full accent-primary pointer-coarse:h-11"
			oninput={(event) => (view = zoomTo(view, Number(event.currentTarget.value), width, height))}
		/>
		<Plus class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
	</div>

	<div class="flex justify-end gap-2">
		<Button variant="outline" class="pointer-coarse:h-11" onclick={oncancel} disabled={busy}>
			Cancel
		</Button>
		<Button class="pointer-coarse:h-11" onclick={() => onsave(crop)} disabled={!bitmap || busy}>
			{#if busy}<Spinner class="size-4" />Saving…{:else}Save{/if}
		</Button>
	</div>
</div>
