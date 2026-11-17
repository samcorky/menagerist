/**
 * The square a person keeps when cropping a picture, in natural pixels of the
 * upright image. Zoom 1 is the largest square that fits; every change is clamped
 * so the square never leaves the picture.
 */

export const MAX_ZOOM = 8;

export type CropView = { zoom: number; centreX: number; centreY: number };
export type Crop = { x: number; y: number; size: number };
export type Direction = 'up' | 'down' | 'left' | 'right';

function side(zoom: number, width: number, height: number): number {
	return Math.max(1, Math.round(Math.min(width, height) / zoom));
}

function clamp(value: number, low: number, high: number): number {
	return Math.min(high, Math.max(low, value));
}

function clamped(view: CropView, width: number, height: number): CropView {
	const zoom = clamp(view.zoom, 1, MAX_ZOOM);
	const half = side(zoom, width, height) / 2;
	return {
		zoom,
		centreX: clamp(view.centreX, half, width - half),
		centreY: clamp(view.centreY, half, height - half)
	};
}

export function initialView(width: number, height: number): CropView {
	return { zoom: 1, centreX: width / 2, centreY: height / 2 };
}

export function cropSquare(view: CropView, width: number, height: number): Crop {
	const size = side(view.zoom, width, height);
	return {
		x: clamp(Math.round(view.centreX - size / 2), 0, width - size),
		y: clamp(Math.round(view.centreY - size / 2), 0, height - size),
		size
	};
}

/** Move the square by a distance in natural pixels. */
export function pan(
	view: CropView,
	dx: number,
	dy: number,
	width: number,
	height: number
): CropView {
	return clamped(
		{ ...view, centreX: view.centreX + dx, centreY: view.centreY + dy },
		width,
		height
	);
}

export function zoomTo(view: CropView, zoom: number, width: number, height: number): CropView {
	return clamped({ ...view, zoom }, width, height);
}

/** An arrow-key step: 1% of the picture's short side, or 10% for a large step. */
export function nudge(
	view: CropView,
	direction: Direction,
	large: boolean,
	width: number,
	height: number
): CropView {
	const step = (Math.min(width, height) * (large ? 10 : 1)) / 100;
	const [dx, dy] = {
		up: [0, -step],
		down: [0, step],
		left: [-step, 0],
		right: [step, 0]
	}[direction];
	return pan(view, dx, dy, width, height);
}
