import { describe, expect, it } from 'vitest';
import { drawnCatSvg, seededRandom } from '../src/lib/avatars/drawn-cat';

const ALLOWED = new Set(['svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'polygon']);

/** Element names in document order, and whether every open tag is closed. */
function structure(svg: string): { names: string[]; balanced: boolean } {
	const stack: string[] = [];
	const names: string[] = [];
	for (const [, closing, name, selfClosing] of svg.matchAll(/<(\/?)([a-zA-Z]+)[^>]*?(\/?)>/g)) {
		if (closing) {
			if (stack.pop() !== name) return { names, balanced: false };
		} else {
			names.push(name);
			if (!selfClosing) stack.push(name);
		}
	}
	return { names, balanced: stack.length === 0 };
}

describe('drawnCatSvg', () => {
	it('draws the same cat for the same seed', () => {
		expect(drawnCatSvg(seededRandom(42))).toBe(drawnCatSvg(seededRandom(42)));
	});

	it('draws different cats for different seeds', () => {
		const cats = new Set(Array.from({ length: 20 }, (_, i) => drawnCatSvg(seededRandom(i))));
		expect(cats.size).toBeGreaterThan(15);
	});

	it('is a self-contained 256 px square with only simple shapes', () => {
		for (let seed = 0; seed < 50; seed++) {
			const svg = drawnCatSvg(seededRandom(seed));
			expect(svg).toMatch(/^<svg [^>]*viewBox="0 0 256 256"/);
			expect(svg).toContain('width="256" height="256"');
			expect(svg).toContain('xmlns="http://www.w3.org/2000/svg"');
			const { names, balanced } = structure(svg);
			expect(balanced).toBe(true);
			expect(names.every((name) => ALLOWED.has(name))).toBe(true);
		}
	});

	it('never references anything outside itself', () => {
		for (let seed = 0; seed < 50; seed++) {
			const svg = drawnCatSvg(seededRandom(seed));
			expect(svg).not.toMatch(/<script|href|foreignObject|url\(|on\w+=/i);
		}
	});

	it('uses only plain hex colours', () => {
		const svg = drawnCatSvg(seededRandom(7));
		for (const [, colour] of svg.matchAll(/(?:fill|stroke)="([^"]+)"/g)) {
			expect(colour).toMatch(/^(#[0-9a-f]{6}|none)$/);
		}
	});

	it('works with Math.random by default', () => {
		expect(drawnCatSvg()).toMatch(/^<svg /);
	});
});

describe('seededRandom', () => {
	it('gives numbers in [0, 1) and repeats for the same seed', () => {
		const a = seededRandom(1);
		const b = seededRandom(1);
		for (let i = 0; i < 100; i++) {
			const value = a();
			expect(value).toBe(b());
			expect(value).toBeGreaterThanOrEqual(0);
			expect(value).toBeLessThan(1);
		}
	});
});
