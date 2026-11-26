import { nextCursor, type PageResult } from '$lib/paging';

/** What the list asks its fetcher for: the page after `after` (the first when absent). */
export interface PageRequest<P> {
	after: string | undefined;
	params: P;
}

/**
 * How a list shows its pages. `append` is the infinite list (design §19): each page is added
 * to the rows, and `ListFoot` asks for the next. `page` is for a table, or one of several
 * lists on a screen: the rows are the current page alone, and `PageNav` steps through them.
 */
export type PagedListMode = 'append' | 'page';

/** What a foot reads and does, whatever the rows are: `PageNav` takes any list that has it. */
export interface PagedFoot {
	readonly rows: readonly unknown[];
	readonly loading: boolean;
	readonly nextFailed: boolean;
	readonly hasMore: boolean;
	readonly total: number | null;
	readonly pageIndex: number;
	readonly from: number | null;
	readonly to: number | null;
	next(): Promise<void>;
	previous(): Promise<void>;
	retry(): Promise<void>;
}

/** The server's row count from a `Total-Count` header, or null when it sent none. */
function totalOf(response: Response | undefined): number | null {
	const total = Number.parseInt(response?.headers.get('total-count') ?? '', 10);
	return Number.isNaN(total) || total < 0 ? null : total;
}

/**
 * A list read a page at a time, through the server's cursor.
 *
 * It owns the rows, the cursor the server's `Link` header gave for the next page, whether
 * there is more, and the loading and failed states, so a page only says how to read one page
 * of its route and what it is filtered by (`params`). The cursor is the server's, never the
 * last row's id, so the list keeps working under any sort. A response that arrives after a
 * newer request is dropped.
 *
 * It has no effects of its own: a page calls `load` from an `$effect` that reads what it
 * filters by, and wires the foot (`ListFoot` for `append`, `PageNav` for `page`) to it.
 */
export class PagedList<T, P> {
	/** Every row read so far (`append`), or the rows of the current page (`page`). */
	rows = $state<T[]>([]);
	/** A page is being read. True until the first page has come back. */
	loading = $state(true);
	/** The first page would not load: the whole list is the page-level failure. */
	failed = $state(false);
	/** Another page would not load: the rows shown stay, and `retry` tries it again. */
	nextFailed = $state(false);
	/** What the failed read returned, for wording the error; null when nothing failed. */
	failure = $state<PageResult<T> | null>(null);
	hasMore = $state(false);
	/** The server's count of every row, where it sends one. */
	total = $state<number | null>(null);
	/** Which page is shown, from 0. Always 0 for an `append` list. */
	pageIndex = $state(0);

	readonly mode: PagedListMode;
	readonly #fetchPage: (request: PageRequest<P>) => Promise<PageResult<T>>;
	#params: P | undefined;
	// The cursor of the page after the one shown; null when there is none.
	#cursor: string | null = null;
	// `page` mode: the cursor each page was read with, and how many rows came before it.
	#cursors: (string | undefined)[] = [undefined];
	#starts: number[] = [0];
	#seq = 0;
	// The read that failed while rows were shown, for `retry` to repeat.
	#failedRead: { index: number; after: string | undefined; start: number } | null = null;

	constructor(
		fetchPage: (request: PageRequest<P>) => Promise<PageResult<T>>,
		{ mode = 'append' }: { mode?: PagedListMode } = {}
	) {
		this.#fetchPage = fetchPage;
		this.mode = mode;
	}

	/** Start again from the first page for `params`, dropping the rows read so far. */
	load(params: P): Promise<void> {
		this.#params = params;
		this.rows = [];
		this.hasMore = false;
		this.total = null;
		this.pageIndex = 0;
		this.#cursor = null;
		this.#cursors = [undefined];
		this.#starts = [0];
		return this.#read(0, undefined, 0);
	}

	/** `append`: read the next page onto the rows, if there is one and nothing is loading. */
	loadMore(): Promise<void> {
		if (this.mode !== 'append') return Promise.resolve();
		if (!this.hasMore || this.loading || this.#cursor === null) return Promise.resolve();
		return this.#read(0, this.#cursor, this.rows.length);
	}

	/** `page`: show the next page, if there is one. */
	next(): Promise<void> {
		if (this.mode !== 'page' || !this.hasMore || this.loading || this.#cursor === null) {
			return Promise.resolve();
		}
		return this.#read(
			this.pageIndex + 1,
			this.#cursor,
			this.#starts[this.pageIndex] + this.rows.length
		);
	}

	/** `page`: show the page before, which the list read before and reads again. */
	previous(): Promise<void> {
		if (this.mode !== 'page' || this.pageIndex === 0 || this.loading) return Promise.resolve();
		const index = this.pageIndex - 1;
		return this.#read(index, this.#cursors[index], this.#starts[index]);
	}

	/**
	 * `page`: read the page shown again, keeping its rows meanwhile, after a row on it was
	 * added, changed or removed. If it has emptied, the page before it is shown instead.
	 */
	refresh(): Promise<void> {
		if (this.mode !== 'page' || this.#params === undefined) return Promise.resolve();
		const index = this.pageIndex;
		return this.#read(index, this.#cursors[index], this.#starts[index]);
	}

	/** Try again what failed: the first page, or the page that was being read. */
	retry(): Promise<void> {
		if (this.failed) return this.#read(0, undefined, 0);
		const read = this.nextFailed ? this.#failedRead : null;
		return read === null ? Promise.resolve() : this.#read(read.index, read.after, read.start);
	}

	/** `page`: the first row's place in the whole list, from 1; null with no rows. */
	get from(): number | null {
		return this.rows.length === 0 ? null : this.#starts[this.pageIndex] + 1;
	}

	/** `page`: the last row's place in the whole list; null with no rows. */
	get to(): number | null {
		return this.rows.length === 0 ? null : this.#starts[this.pageIndex] + this.rows.length;
	}

	async #read(index: number, after: string | undefined, start: number): Promise<void> {
		if (this.#params === undefined) return;
		const seq = ++this.#seq;
		this.loading = true;
		if (after === undefined) this.failed = false;
		this.nextFailed = false;
		this.failure = null;
		let result: PageResult<T>;
		try {
			result = await this.#fetchPage({ after, params: this.#params });
		} catch (error) {
			// A request that throws is a failed page like any other.
			result = { error };
		}
		if (seq !== this.#seq) return;
		if (result.error || !result.data) {
			this.failure = result;
			// With nothing shown the whole list failed. Otherwise the rows stay, `hasMore` and
			// the cursors are kept, and `retry` reads the page again.
			if (this.rows.length === 0) {
				this.failed = true;
				this.hasMore = false;
			} else {
				this.nextFailed = true;
				this.#failedRead = { index, after, start };
			}
		} else if (this.mode === 'page' && result.data.length === 0 && index > 0) {
			// Nothing here any more (rows were removed); show the page before it.
			return this.#read(index - 1, this.#cursors[index - 1], this.#starts[index - 1]);
		} else {
			this.#accept(index, after, start, result);
		}
		this.loading = false;
	}

	#accept(index: number, after: string | undefined, start: number, result: PageResult<T>): void {
		const data = result.data ?? [];
		if (this.mode === 'append') {
			this.rows = after === undefined ? data : [...this.rows, ...data];
		} else {
			this.rows = data;
			this.pageIndex = index;
			this.#cursors[index] = after;
			this.#starts[index] = start;
		}
		this.#cursor = nextCursor(result.response?.headers.get('link'));
		this.hasMore = this.#cursor !== null;
		this.total = totalOf(result.response);
	}
}
