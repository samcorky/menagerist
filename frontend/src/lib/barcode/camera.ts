/** Opening the rear camera for scanning, and why it could not be opened, in plain words. */

export type CameraProblem = 'denied' | 'unavailable' | 'insecure' | 'scanner';

export const CAMERA_PROBLEM_TEXT: Record<CameraProblem, string> = {
	denied: 'Camera access is turned off for this site. Allow it in your browser, or type the code.',
	unavailable: 'No camera is available. Type the code instead.',
	insecure: 'The camera only works over a secure (https) connection. Type the code instead.',
	scanner: "The scanner couldn't start. Type the code instead."
};

/** Classify a `getUserMedia` failure. */
export function cameraProblem(error: unknown): CameraProblem {
	const name = error instanceof Error || error instanceof DOMException ? error.name : '';
	return name === 'NotAllowedError' || name === 'SecurityError' ? 'denied' : 'unavailable';
}

/** Ask for the rear camera, or say why it cannot be used. */
export async function openCamera(): Promise<{ stream: MediaStream } | { problem: CameraProblem }> {
	if (!window.isSecureContext) return { problem: 'insecure' };
	if (!navigator.mediaDevices?.getUserMedia) return { problem: 'unavailable' };
	try {
		const stream = await navigator.mediaDevices.getUserMedia({
			video: { facingMode: { ideal: 'environment' } },
			audio: false
		});
		return { stream };
	} catch (error) {
		return { problem: cameraProblem(error) };
	}
}

export function stopCamera(stream: MediaStream | null): void {
	stream?.getTracks().forEach((track) => track.stop());
}

/** `torch` is not in TypeScript's capability and constraint types yet. */
type TorchTrack = { getCapabilities?: () => { torch?: boolean } };

/** Whether the camera in this stream has a light to switch on (not offered on iOS Safari). */
export function hasTorch(stream: MediaStream | null): boolean {
	const track = stream?.getVideoTracks()[0] as unknown as TorchTrack | undefined;
	return Boolean(track?.getCapabilities?.().torch);
}

/** Switch the camera's light on or off; false when the browser refuses. */
export async function setTorch(stream: MediaStream | null, on: boolean): Promise<boolean> {
	const track = stream?.getVideoTracks()[0];
	if (!track) return false;
	try {
		await track.applyConstraints({ advanced: [{ torch: on } as MediaTrackConstraintSet] });
		return true;
	} catch {
		return false;
	}
}
