/** Naming another person's device from the admin pages (Devices, and a user's devices). */
import { toast } from 'svelte-sonner';
import { renameDevice, type AdminSessionResponse } from '$lib/api/client';
import { errorMessage } from '$lib/api/errors';

/**
 * Save a device's name (`null` clears it) and say so. Resolves to the saved name, or
 * `undefined` when it failed and the person has been told why.
 */
export async function renameUserDevice(
	deviceId: string,
	name: string | null
): Promise<string | null | undefined> {
	try {
		const res = await renameDevice({ path: { device_id: deviceId }, body: { name } });
		if (res.error || !res.data) {
			toast.error(errorMessage(res.error));
			return undefined;
		}
		const saved = res.data.name ?? null;
		toast.success(saved ? 'Device named' : 'Device name cleared');
		return saved;
	} catch {
		toast.error('Could not save the name.');
		return undefined;
	}
}

/** The sessions with a device's new name on every session started in it. */
export function withDeviceName(
	sessions: AdminSessionResponse[],
	deviceId: string,
	name: string | null
): AdminSessionResponse[] {
	return sessions.map((s) => (s.device_id === deviceId ? { ...s, device_name: name } : s));
}
