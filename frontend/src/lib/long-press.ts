export const LONG_PRESS_MS = 500;
/** A finger that moves further than this is scrolling, not holding. */
const SLOP_PX = 10;

interface PressEvent {
	pointerType: string;
	isPrimary: boolean;
	clientX: number;
	clientY: number;
}

/**
 * Pointer handlers that call `onlongpress` once when a finger is held still for `delayMs`,
 * and swallow the click that follows so the hold does not also open the item. Touch and
 * pen only: a mouse has the visible Select control.
 */
export function createLongPress(onlongpress: () => void, delayMs = LONG_PRESS_MS) {
	let timer: ReturnType<typeof setTimeout> | undefined;
	let origin: { x: number; y: number } | null = null;
	let fired = false;

	function cancel() {
		clearTimeout(timer);
		origin = null;
	}

	return {
		onpointerdown(e: PressEvent) {
			if (e.pointerType === 'mouse' || !e.isPrimary) return;
			fired = false;
			origin = { x: e.clientX, y: e.clientY };
			clearTimeout(timer);
			timer = setTimeout(() => {
				fired = true;
				origin = null;
				onlongpress();
			}, delayMs);
		},
		onpointermove(e: PressEvent) {
			if (!origin) return;
			if (Math.hypot(e.clientX - origin.x, e.clientY - origin.y) > SLOP_PX) cancel();
		},
		onpointerup: cancel,
		onpointercancel: cancel,
		/** Use in the capture phase: returns true when the click belongs to a long press. */
		swallowClick(): boolean {
			const swallow = fired;
			fired = false;
			return swallow;
		},
		/** The menu a held link opens on a phone; suppressed while a hold is possible. */
		suppressContextMenu(e: object): boolean {
			return fired || origin !== null || ('pointerType' in e && e.pointerType === 'touch');
		}
	};
}
