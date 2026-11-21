<script lang="ts">
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Flashlight, FlashlightOff } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import {
		CAMERA_PROBLEM_TEXT,
		hasTorch,
		openCamera,
		setTorch,
		stopCamera,
		type CameraProblem
	} from '$lib/barcode/camera';
	import { createDetector, firstCode, type Detector } from '$lib/barcode/detector';

	let {
		open = $bindable(false),
		onDetected
	}: {
		open?: boolean;
		/** Called once with the scanned or typed code; the scanner has closed by then. */
		onDetected: (code: string) => void;
	} = $props();

	/** How often a frame is read; detection is costly on the WebAssembly fallback. */
	const SCAN_INTERVAL_MS = 200;
	const typedId = 'barcode-typed-code';

	let problem = $state<CameraProblem | null>(null);
	let starting = $state(true);
	let typed = $state('');
	let canLight = $state(false);
	let lightOn = $state(false);
	/** The stream being filmed, for the light button. */
	let filming: MediaStream | null = null;

	/** Runs the camera for as long as the preview is on screen, which is while the dialog is open. */
	function scanWith(el: HTMLVideoElement) {
		let stopped = false;
		let stream: MediaStream | null = null;
		let timer: ReturnType<typeof setTimeout> | undefined;
		problem = null;
		starting = true;
		typed = '';
		canLight = false;
		lightOn = false;

		async function scan(detector: Detector) {
			if (stopped) return;
			try {
				const code = el.readyState >= 2 ? firstCode(await detector.detect(el)) : null;
				if (stopped) return;
				if (code) return finish(code);
			} catch {
				// A frame that cannot be read is retried with the next one.
			}
			timer = setTimeout(() => void scan(detector), SCAN_INTERVAL_MS);
		}

		async function start() {
			// The detector (possibly a WebAssembly download) loads while the person allows the camera.
			const detectorReady = createDetector().catch(() => null);
			const camera = await openCamera();
			if ('problem' in camera) {
				if (!stopped) fail(camera.problem);
				return;
			}
			if (stopped) return stopCamera(camera.stream);
			stream = camera.stream;
			filming = stream;
			canLight = hasTorch(stream);
			el.srcObject = stream;
			await el.play().catch(() => {});
			const detector = await detectorReady;
			if (stopped) return;
			if (!detector) return fail('scanner');
			starting = false;
			void scan(detector);
		}

		function fail(reason: CameraProblem) {
			stopCamera(stream);
			stream = null;
			filming = null;
			canLight = false;
			problem = reason;
			starting = false;
		}

		void start();
		return () => {
			stopped = true;
			clearTimeout(timer);
			stopCamera(stream);
			filming = null;
			canLight = false;
			lightOn = false;
			el.srcObject = null;
		};
	}

	async function toggleLight() {
		const next = !lightOn;
		if (await setTorch(filming, next)) lightOn = next;
	}

	function finish(code: string) {
		open = false;
		onDetected(code);
	}

	function useTyped() {
		const code = typed.trim();
		if (code) finish(code);
	}
</script>

<ResponsiveDialog.Root bind:open>
	<ResponsiveDialog.Content title="Scan barcode" size="md">
		<div class="mt-4 space-y-4">
			<div class="relative overflow-hidden rounded-lg bg-black {problem ? 'hidden' : ''}">
				<video
					{@attach scanWith}
					muted
					playsinline
					aria-label="Camera preview"
					class="aspect-[4/3] w-full object-cover"
				></video>
				<div
					aria-hidden="true"
					class="pointer-events-none absolute inset-x-[12%] top-1/2 h-1/3 -translate-y-1/2 rounded-md border-2 border-white/80"
				></div>
				{#if canLight}
					<button
						type="button"
						onclick={toggleLight}
						aria-pressed={lightOn}
						aria-label={lightOn ? 'Turn the light off' : 'Turn the light on'}
						class="absolute right-2 bottom-2 flex size-10 items-center justify-center rounded-full bg-black/60 text-white hover:bg-black/80 focus-visible:ring-2 focus-visible:ring-white focus-visible:outline-none pointer-coarse:size-11"
					>
						{#if lightOn}
							<Flashlight class="size-5" />
						{:else}
							<FlashlightOff class="size-5" />
						{/if}
					</button>
				{/if}
			</div>

			<p class="text-sm text-muted-foreground" role="status">
				{#if problem}
					{CAMERA_PROBLEM_TEXT[problem]}
				{:else if starting}
					Starting the camera…
				{:else}
					Hold the barcode inside the frame.
				{/if}
			</p>

			<form
				class="space-y-1.5"
				onsubmit={(e) => {
					e.preventDefault();
					useTyped();
				}}
			>
				<Label for={typedId} class="text-xs text-muted-foreground">Or type the code</Label>
				<div class="flex gap-2">
					<Input
						id={typedId}
						bind:value={typed}
						autocomplete="off"
						spellcheck={false}
						class="pointer-coarse:h-11"
					/>
					<Button type="submit" class="pointer-coarse:h-11" disabled={!typed.trim()}>
						Use code
					</Button>
				</div>
			</form>
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
