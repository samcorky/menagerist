import {
	getRestoreProgress,
	restoreInstance,
	type ProgressSnapshotResponse
} from '$lib/api/client';

type RestoreResult = { ok: true } | { ok: false; message: string };

/** How the restore is getting on, or null when nothing has reported (or it cannot be read). */
export async function readRestoreProgress(): Promise<ProgressSnapshotResponse | null> {
	try {
		const result = await getRestoreProgress();
		return result.data ?? null;
	} catch {
		return null;
	}
}

export async function restoreFirstRunArchive(file: File): Promise<RestoreResult> {
	try {
		const result = await restoreInstance({ body: file });
		if (result.response?.ok) return { ok: true };
		switch (result.response?.status) {
			case 400:
				return {
					ok: false,
					message: 'This backup could not be verified. Choose another backup and try again.'
				};
			case 409:
				return {
					ok: false,
					message:
						'This backup cannot be restored here. It may be from a different version, or setup is already complete.'
				};
			case 413:
				return {
					ok: false,
					message:
						'This backup is larger than this server allows. Ask the person running this server to increase the backup upload limit.'
				};
			case 429:
				return {
					ok: false,
					message: 'Too many restore attempts. Wait a few minutes and try again.'
				};
			default:
				return {
					ok: false,
					message: 'We could not restore this backup. Check your connection and try again.'
				};
		}
	} catch {
		return {
			ok: false,
			message: 'We could not reach the server. Check your connection and try again.'
		};
	}
}
