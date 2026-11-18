/**
 * A barcode detector: the browser's own `BarcodeDetector` where it has one, otherwise the
 * `barcode-detector` ponyfill (ZXing compiled to WebAssembly). The ponyfill and its WebAssembly
 * file load only when first needed, from this server: the package would otherwise fetch the
 * file from a CDN, which the app's CSP blocks and which would tell a third party about the scan.
 */

/** Product codes (EAN/UPC, which carry ISBNs), common shelf and library codes, and QR codes. */
export const SCAN_FORMATS = [
	'ean_13',
	'ean_8',
	'upc_a',
	'upc_e',
	'code_128',
	'code_39',
	'itf',
	'qr_code'
] as const;

export type ScanFormat = (typeof SCAN_FORMATS)[number];

export type Detector = {
	detect(source: HTMLVideoElement): Promise<{ rawValue: string }[]>;
};

type DetectorClass = {
	new (options: { formats: ScanFormat[] }): Detector;
	getSupportedFormats(): Promise<readonly string[]>;
};

/** The formats a native detector should look for, or none when it cannot read any of ours. */
export function nativeFormats(supported: readonly string[]): ScanFormat[] {
	return SCAN_FORMATS.filter((format) => supported.includes(format));
}

async function nativeDetector(): Promise<Detector | null> {
	const Native = (globalThis as { BarcodeDetector?: DetectorClass }).BarcodeDetector;
	if (!Native) return null;
	try {
		const formats = nativeFormats(await Native.getSupportedFormats());
		return formats.length > 0 ? new Native({ formats }) : null;
	} catch {
		// Some browsers expose the class but fail on use (desktop Chrome without a platform reader).
		return null;
	}
}

async function wasmDetector(): Promise<Detector> {
	const [{ BarcodeDetector, prepareZXingModule }, { default: wasmUrl }] = await Promise.all([
		import('barcode-detector/ponyfill'),
		import('zxing-wasm/reader/zxing_reader.wasm?url')
	]);
	prepareZXingModule({
		overrides: {
			locateFile: (path: string, prefix: string) =>
				path.endsWith('.wasm') ? wasmUrl : prefix + path
		}
	});
	return new BarcodeDetector({ formats: [...SCAN_FORMATS] });
}

/** Resolve a detector; rejects only when the WebAssembly fallback cannot be loaded either. */
export async function createDetector(): Promise<Detector> {
	return (await nativeDetector()) ?? (await wasmDetector());
}

/** The first non-blank code in a detection result, trimmed. */
export function firstCode(results: { rawValue: string }[]): string | null {
	for (const { rawValue } of results) {
		const code = rawValue.trim();
		if (code) return code;
	}
	return null;
}
