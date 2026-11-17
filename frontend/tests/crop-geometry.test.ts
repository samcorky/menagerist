import { describe, expect, it } from 'vitest';
import {
	MAX_ZOOM,
	cropSquare,
	initialView,
	nudge,
	pan,
	zoomTo
} from '../src/lib/avatars/crop-geometry';

describe('crop geometry', () => {
	it('starts on the largest centred square', () => {
		expect(cropSquare(initialView(400, 200), 400, 200)).toEqual({ x: 100, y: 0, size: 200 });
		expect(cropSquare(initialView(200, 400), 200, 400)).toEqual({ x: 0, y: 100, size: 200 });
	});

	it('halves the square at zoom 2', () => {
		const view = zoomTo(initialView(400, 200), 2, 400, 200);
		expect(cropSquare(view, 400, 200)).toEqual({ x: 150, y: 50, size: 100 });
	});

	it('clamps a pan so the square stays inside the picture', () => {
		const right = pan(initialView(400, 200), 1000, 0, 400, 200);
		expect(cropSquare(right, 400, 200)).toEqual({ x: 200, y: 0, size: 200 });
		const left = pan(initialView(400, 200), -1000, -1000, 400, 200);
		expect(cropSquare(left, 400, 200)).toEqual({ x: 0, y: 0, size: 200 });
	});

	it('keeps zoom between 1 and the maximum', () => {
		expect(zoomTo(initialView(400, 200), 50, 400, 200).zoom).toBe(MAX_ZOOM);
		expect(zoomTo(initialView(400, 200), 0.2, 400, 200).zoom).toBe(1);
		expect(MAX_ZOOM).toBe(8);
	});

	it('re-clamps the centre when zooming out near an edge', () => {
		let view = zoomTo(initialView(400, 200), 4, 400, 200);
		view = pan(view, 1000, 1000, 400, 200);
		view = zoomTo(view, 1, 400, 200);
		expect(cropSquare(view, 400, 200)).toEqual({ x: 200, y: 0, size: 200 });
	});

	it('always gives whole pixels', () => {
		const view = zoomTo(initialView(333, 777), 3.3, 333, 777);
		const crop = cropSquare(pan(view, 12.7, 3.1, 333, 777), 333, 777);
		for (const value of Object.values(crop)) expect(Number.isInteger(value)).toBe(true);
		expect(crop.x + crop.size).toBeLessThanOrEqual(333);
		expect(crop.y + crop.size).toBeLessThanOrEqual(777);
	});

	it('nudges by 1% of the short side, or 10% with a large step', () => {
		const view = zoomTo(initialView(400, 200), 2, 400, 200);
		expect(cropSquare(nudge(view, 'right', false, 400, 200), 400, 200).x).toBe(152);
		expect(cropSquare(nudge(view, 'up', true, 400, 200), 400, 200).y).toBe(30);
	});
});
