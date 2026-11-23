export const UNDO_WINDOW_MS = 5000;

export interface DeferredDelete {
	/** Cancel the delete if it has not been sent yet. */
	undo(): void;
	/** Send now, such as when the person navigates away; a no-op once sent or undone. */
	flush(): Promise<void>;
	/** Settles when the request has been sent or the delete was undone. */
	readonly settled: Promise<void>;
}

/**
 * Hold a destructive request for the Undo window (design §14): nothing is sent until the
 * window ends, so Undo needs no restore endpoint. `send` runs at most once.
 */
export function deferDelete(
	send: () => Promise<void>,
	{ windowMs = UNDO_WINDOW_MS }: { windowMs?: number } = {}
): DeferredDelete {
	let state: 'pending' | 'sent' | 'undone' = 'pending';
	let finish: () => void = () => {};
	// `run` is hoisted and only reads `timer` once called, which is after this line.
	const timer = setTimeout(() => void run().catch(() => {}), windowMs);
	const settled = new Promise<void>((resolve) => (finish = resolve));

	async function run(): Promise<void> {
		if (state !== 'pending') return;
		state = 'sent';
		clearTimeout(timer);
		try {
			await send();
		} finally {
			finish();
		}
	}

	// A failure surfaces through `send` itself (the caller reports it); the timer has no one to throw to.
	return {
		undo() {
			if (state !== 'pending') return;
			state = 'undone';
			clearTimeout(timer);
			finish();
		},
		flush: run,
		settled
	};
}
