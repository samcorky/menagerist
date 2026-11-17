/**
 * A cat drawn in the browser, for Random cat when the server's cat service is off
 * or unreachable. Each call assembles a face from random parts; the result is
 * rendered to a PNG and uploaded like any picture, so the server checks it too.
 */

type Random = () => number;

const SIZE = 256;
const CX = 128;
const CY = 150;
const OUTLINE = '#3a2f2a';

const BACKGROUNDS = ['#fde8e4', '#e3f0fb', '#e6f4ea', '#fdf3d7', '#efe7fb', '#e0f4f3'];
const COATS = ['#e8893c', '#2b2b2e', '#8a8f98', '#f1d9b5', '#7a5236', '#f7f5f2', '#c9c2b8'];
const EYES = ['#5fa84f', '#e0a526', '#4a8fd6', '#c46a2b'];
const INNER_EAR = '#f2a7b5';
const NOSE = '#e58ca0';

type Head = { rx: number; ry: number };
const HEADS: Head[] = [
	{ rx: 78, ry: 70 },
	{ rx: 88, ry: 64 },
	{ rx: 72, ry: 76 }
];

function pick<T>(random: Random, options: readonly T[]): T {
	return options[Math.min(options.length - 1, Math.floor(random() * options.length))];
}

function ears(style: number, head: Head, coat: string): string {
	const top = CY - head.ry;
	const left = CX - head.rx * 0.62;
	const right = CX + head.rx * 0.62;
	const shape = (x: number, side: -1 | 1, fill: string, inset: number): string => {
		const w = 34 - inset;
		const h = (style === 2 ? 34 : 58) - inset * 1.6;
		const base = top + 22;
		const tipX = x + side * (style === 2 ? 22 : 6);
		const tipY = base - h;
		if (style === 1) {
			return `<path d="M${x - w} ${base} Q${tipX} ${tipY - 14} ${x + w} ${base} Z" fill="${fill}"/>`;
		}
		return `<polygon points="${x - w},${base} ${tipX},${tipY} ${x + w},${base}" fill="${fill}"/>`;
	};
	return [
		`<g stroke="${OUTLINE}" stroke-width="4" stroke-linejoin="round">`,
		shape(left, -1, coat, 0),
		shape(right, 1, coat, 0),
		'</g>',
		shape(left, -1, INNER_EAR, 14),
		shape(right, 1, INNER_EAR, 14)
	].join('');
}

function markings(style: number, head: Head, second: string): string {
	switch (style) {
		case 1: {
			const top = CY - head.ry + 8;
			return [-18, 0, 18]
				.map(
					(dx) =>
						`<path d="M${CX + dx} ${top} L${CX + dx * 0.6} ${top + 26}" stroke="${second}" stroke-width="7" stroke-linecap="round" fill="none"/>`
				)
				.join('');
		}
		case 2:
			return `<ellipse cx="${CX + 30}" cy="${CY - 12}" rx="32" ry="28" fill="${second}"/>`;
		case 3:
			return `<ellipse cx="${CX}" cy="${CY + 34}" rx="${head.rx * 0.55}" ry="30" fill="#f7f5f2"/>`;
		default:
			return '';
	}
}

function face(eye: string): string {
	const eyeY = CY - 10;
	const eyeShape = (x: number): string =>
		`<ellipse cx="${x}" cy="${eyeY}" rx="13" ry="15" fill="${eye}" stroke="${OUTLINE}" stroke-width="3"/>` +
		`<ellipse cx="${x}" cy="${eyeY}" rx="4" ry="11" fill="#1d1a18"/>` +
		`<circle cx="${x + 4}" cy="${eyeY - 6}" r="3" fill="#ffffff"/>`;
	const whiskers = [-1, 1]
		.flatMap((side) =>
			[-6, 4].map(
				(dy) =>
					`<path d="M${CX + side * 26} ${CY + 22 + dy} L${CX + side * 84} ${CY + 16 + dy * 2}" stroke="${OUTLINE}" stroke-width="2.5" stroke-linecap="round" fill="none"/>`
			)
		)
		.join('');
	return [
		eyeShape(CX - 30),
		eyeShape(CX + 30),
		`<polygon points="${CX - 9},${CY + 14} ${CX + 9},${CY + 14} ${CX},${CY + 24}" fill="${NOSE}" stroke="${OUTLINE}" stroke-width="2" stroke-linejoin="round"/>`,
		`<path d="M${CX} ${CY + 24} Q${CX - 8} ${CY + 36} ${CX - 18} ${CY + 30} M${CX} ${CY + 24} Q${CX + 8} ${CY + 36} ${CX + 18} ${CY + 30}" stroke="${OUTLINE}" stroke-width="3" stroke-linecap="round" fill="none"/>`,
		whiskers
	].join('');
}

/** A self-contained 256×256 SVG of a random cat's face. */
export function drawnCatSvg(random: Random = Math.random): string {
	const background = pick(random, BACKGROUNDS);
	const coat = pick(random, COATS);
	const second = pick(
		random,
		COATS.filter((colour) => colour !== coat)
	);
	const head = pick(random, HEADS);
	const earStyle = Math.floor(random() * 3);
	const markingStyle = Math.floor(random() * 4);
	const eye = pick(random, EYES);
	return [
		`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${SIZE} ${SIZE}" width="${SIZE}" height="${SIZE}">`,
		`<rect width="${SIZE}" height="${SIZE}" fill="${background}"/>`,
		ears(earStyle, head, coat),
		`<ellipse cx="${CX}" cy="${CY}" rx="${head.rx}" ry="${head.ry}" fill="${coat}" stroke="${OUTLINE}" stroke-width="4"/>`,
		markings(markingStyle, head, second),
		face(eye),
		'</svg>'
	].join('');
}

/** A small seeded generator (mulberry32), so a cat can be drawn again from its seed. */
export function seededRandom(seed: number): Random {
	let state = seed >>> 0;
	return () => {
		state = (state + 0x6d2b79f5) >>> 0;
		let t = state;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

/** Draw a random cat onto a 256 px canvas and return it as a PNG. */
export async function drawnCatPng(random: Random = Math.random): Promise<Blob> {
	const svg = new Blob([drawnCatSvg(random)], { type: 'image/svg+xml' });
	const address = URL.createObjectURL(svg);
	try {
		const image = new Image(SIZE, SIZE);
		image.src = address;
		await image.decode();
		const canvas = document.createElement('canvas');
		canvas.width = SIZE;
		canvas.height = SIZE;
		const context = canvas.getContext('2d');
		if (!context) throw new Error('This browser cannot draw a cat.');
		context.drawImage(image, 0, 0, SIZE, SIZE);
		return await new Promise<Blob>((resolve, reject) =>
			canvas.toBlob(
				(blob) => (blob ? resolve(blob) : reject(new Error('This browser cannot draw a cat.'))),
				'image/png'
			)
		);
	} finally {
		URL.revokeObjectURL(address);
	}
}
