import { fetchExactCount } from '$lib/smart-collections';

/**
 * The exact item count of one collection, fetched in the background. A request is made
 * at most once automatically per scope (a collection and its conditions); `retry` repeats it.
 */
export class ExactCount {
	count = $state<number | null>(null);
	loading = $state(false);
	failed = $state(false);

	#scope: string | null = null;
	#attempted = false;
	#seq = 0;
	#controller: AbortController | null = null;

	/** Switch to a scope; a different one discards the figure and cancels any request. */
	track(scope: string): void {
		if (scope === this.#scope) return;
		this.cancel();
		this.#scope = scope;
		this.#attempted = false;
		this.count = null;
		this.failed = false;
	}

	/** Request the count unless this scope has already tried. */
	auto(collectionId: string): void {
		if (this.#attempted) return;
		void this.retry(collectionId);
	}

	async retry(collectionId: string): Promise<void> {
		this.cancel();
		this.#attempted = true;
		const seq = this.#seq;
		const controller = new AbortController();
		this.#controller = controller;
		this.loading = true;
		this.failed = false;
		try {
			const count = await fetchExactCount(collectionId, controller.signal);
			if (seq !== this.#seq) return;
			this.count = count;
		} catch {
			if (seq !== this.#seq) return;
			this.failed = true;
		}
		this.loading = false;
	}

	/** Abort any request and ignore its reply. */
	cancel(): void {
		this.#seq++;
		this.#controller?.abort();
		this.#controller = null;
		this.loading = false;
	}
}
