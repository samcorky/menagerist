import { toast } from 'svelte-sonner';
import { SvelteSet } from 'svelte/reactivity';
import { deleteNodes } from '$lib/api/client';
import { errorMessage, networkAwareError } from '$lib/api/errors';
import { itemCount, unknownItemIds } from '$lib/bulk-actions';
import { deferDelete, UNDO_WINDOW_MS, type DeferredDelete } from '$lib/deferred-delete';

/**
 * Bulk deletes waiting out their Undo window (design §14). The items are hidden from the page
 * at once, but nothing is sent until the window ends, so Undo is just "do not send".
 */
export class PendingDeletes {
	/** Items to leave out of the list while their delete is pending. */
	readonly hidden = new SvelteSet<string>();
	readonly #pending = new SvelteSet<DeferredDelete>();

	start(
		ids: string[],
		hooks: {
			/** The server deleted them; reload the list. Hidden items stay hidden until this settles. */
			onsent: () => Promise<void> | void;
			/** The server named items that no longer exist. */
			onmissing: (ids: string[]) => void;
		}
	): void {
		for (const id of ids) this.hidden.add(id);
		const show = () => {
			for (const id of ids) this.hidden.delete(id);
		};

		const pending = deferDelete(async () => {
			const result = await deleteNodes({ body: { ids } });
			if (result.error) {
				show();
				if (!result.response) {
					const { title, description } = networkAwareError(result);
					toast.error(title, { description });
				} else {
					const detail = errorMessage(result.error);
					toast.error("Couldn't delete those items", { description: detail });
					const missing = unknownItemIds(detail);
					if (missing.length > 0) hooks.onmissing(missing);
				}
				return;
			}
			await hooks.onsent();
			show();
		});
		this.#pending.add(pending);
		void pending.settled.finally(() => this.#pending.delete(pending));

		toast.success(`${itemCount(ids.length)} deleted`, {
			duration: UNDO_WINDOW_MS,
			action: {
				label: 'Undo',
				onClick: () => {
					pending.undo();
					show();
				}
			}
		});
	}

	/** Send every pending delete now, as leaving the page does (§14: navigation commits at once). */
	async flushAll(): Promise<void> {
		await Promise.all([...this.#pending].map((p) => p.flush().catch(() => {})));
	}
}
