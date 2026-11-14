// Unsaved form input kept across a session the server ended (it timed out or was revoked).
// Forms register a snapshot while mounted; only when the session ends are the snapshots written,
// to this tab's sessionStorage, under the account they belong to. After signing in again the form
// offers its draft back. Drafts never leave the device and must never hold a password.
const PREFIX = 'menagerist:draft:';

type Snapshot = () => unknown;

const sources = new Map<string, Snapshot>();

function storageKey(owner: string, key: string): string {
	return `${PREFIX}${owner}:${key}`;
}

/** The storage keys of every saved draft, or only those not owned by `keep`. */
function savedKeys(keep?: string): string[] {
	const found: string[] = [];
	for (let i = 0; i < sessionStorage.length; i++) {
		const name = sessionStorage.key(i);
		if (name?.startsWith(PREFIX) && !(keep && name.startsWith(`${PREFIX}${keep}:`))) {
			found.push(name);
		}
	}
	return found;
}

/**
 * Offer a form's input to be kept if the session ends. `snapshot` returns what to keep, or
 * `null` when there is nothing worth keeping. Call from a component `$effect` and return the
 * cleanup, so the form is only asked while it is on screen.
 */
export function registerDraft(key: string, snapshot: Snapshot): () => void {
	sources.set(key, snapshot);
	return () => {
		if (sources.get(key) === snapshot) sources.delete(key);
	};
}

/** Keep every open form's input for `owner`; called as the server ends their session. */
export function saveDrafts(owner: string): void {
	for (const [key, snapshot] of sources) {
		try {
			const data = snapshot();
			if (data === null || data === undefined) continue;
			sessionStorage.setItem(storageKey(owner, key), JSON.stringify(data));
		} catch {
			// Storage blocked or full: the input is lost, as it was before drafts existed.
		}
	}
}

/** The draft `owner` left in the form `key`, if any. */
export function readDraft<T>(owner: string, key: string): T | null {
	try {
		const stored = sessionStorage.getItem(storageKey(owner, key));
		return stored === null ? null : (JSON.parse(stored) as T);
	} catch {
		return null;
	}
}

/** Forget the draft for one form, once it was restored, discarded, saved or cancelled. */
export function clearDraft(owner: string, key: string): void {
	try {
		sessionStorage.removeItem(storageKey(owner, key));
	} catch {
		// Nothing could have been stored either.
	}
}

/**
 * Forget saved drafts: all of them (signing out on purpose), or all but `owner`'s (someone
 * signed in, so nobody else's draft is kept on this tab).
 */
export function clearDrafts(owner?: string): void {
	try {
		for (const name of savedKeys(owner)) sessionStorage.removeItem(name);
	} catch {
		// Nothing could have been stored either.
	}
}
