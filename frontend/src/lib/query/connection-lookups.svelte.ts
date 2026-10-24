import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import { getNode, listEdgeTypes, listNodes } from '$lib/api/client';
import { connectionReferences, type ItemChoice, type RelationshipChoice } from './builder';
import type { SummaryLookup } from './summary';
import type { Query } from './types';

const EDGE_TYPES_PAGE_SIZE = 100;
const MAX_EDGE_TYPE_PAGES = 20;
const ITEM_SEARCH_SIZE = 30;

/**
 * What connection rows and summaries need from the server: the relationship types and the
 * names of the linked items a query names. Reads are lazy, and a failed read leaves the
 * value unknown (never "gone"), so a flaky network does not mark rows as stale.
 */
export class ConnectionLookups {
	relationships = $state<RelationshipChoice[] | null>(null);
	relationshipsFailed = $state(false);
	#names = new SvelteMap<string, string | null>();
	#asked = new SvelteSet<string>();
	#loading = false;

	async loadRelationships(): Promise<void> {
		if (this.#loading || this.relationships !== null) return;
		this.#loading = true;
		this.relationshipsFailed = false;
		try {
			const all: RelationshipChoice[] = [];
			let after: string | undefined;
			for (let page = 0; page < MAX_EDGE_TYPE_PAGES; page++) {
				const result = await listEdgeTypes({ query: { after, limit: EDGE_TYPES_PAGE_SIZE } });
				if (result.error || !result.data) throw new Error('relationships');
				all.push(...result.data);
				const more = /rel="next"/.test(result.response?.headers.get('link') ?? '');
				if (!more || result.data.length === 0) break;
				after = result.data[result.data.length - 1].id;
			}
			this.relationships = all;
		} catch {
			this.relationshipsFailed = true;
		} finally {
			this.#loading = false;
		}
	}

	retryRelationships(): void {
		this.relationships = null;
		void this.loadRelationships();
	}

	/** Note an item the person just picked, so its name shows without a read. */
	rememberItem(item: ItemChoice): void {
		this.#names.set(item.id, item.name);
	}

	/** An item's name: null when it is gone, undefined until known. */
	itemName = (id: string): string | null | undefined => this.#names.get(id);

	async resolveItems(ids: readonly string[]): Promise<void> {
		const wanted = ids.filter((id) => !this.#names.has(id) && !this.#asked.has(id));
		for (const id of wanted) this.#asked.add(id);
		await Promise.all(
			wanted.map(async (id) => {
				try {
					const result = await getNode({ path: { node_id: id } });
					const status = result.response?.status;
					if (result.data) this.#names.set(id, result.data.name);
					else if (status === 404 || status === 422) this.#names.set(id, null);
					else this.#asked.delete(id);
				} catch {
					this.#asked.delete(id);
				}
			})
		);
	}

	/** Items whose name or details match the text; null when the read failed. */
	async searchItems(text: string): Promise<ItemChoice[] | null> {
		try {
			const result = await listNodes({
				query: { q: text.trim() || undefined, limit: ITEM_SEARCH_SIZE }
			});
			if (result.error || !result.data) return null;
			return result.data.map((n) => ({ id: n.id, name: n.name, type: n.type ?? null }));
		} catch {
			return null;
		}
	}

	/** Read what a query's connection conditions name. */
	ensureFor(query: Query | null): void {
		if (!query) return;
		const refs = connectionReferences(query);
		if (refs.any) void this.loadRelationships();
		if (refs.items.length > 0) void this.resolveItems(refs.items);
	}

	/** The parts of `SummaryLookup` this class answers. */
	get summary(): Pick<SummaryLookup, 'relationship' | 'itemName'> {
		return {
			relationship: (slug) =>
				this.relationships === null
					? undefined
					: (this.relationships.find((r) => r.slug === slug) ?? null),
			itemName: this.itemName
		};
	}
}
