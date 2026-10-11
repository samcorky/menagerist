type EtagRecord = { etag?: string; lastModified?: string; data?: unknown };

const store = new Map<string, EtagRecord>();

export const getEtag = (url: string): EtagRecord | undefined => store.get(url);

let generation = 0;
const stamps = new WeakMap<Request, number>();

/** Remember which cache generation a request started in. */
export const stampRequest = (request: Request): Request => {
	stamps.set(request, generation);
	return request;
};

/** Carry the stamp of `from` onto a rebuilt copy of the same request. */
export const carryStamp = (from: Request, to: Request): Request => {
	const stamp = stamps.get(from);
	if (stamp !== undefined) stamps.set(to, stamp);
	return to;
};

/** False when the cache was cleared after this request started. */
export const isCurrent = (request: Request): boolean => {
	const stamp = stamps.get(request);
	return stamp === undefined || stamp === generation;
};

export const setEtag = (url: string, record: EtagRecord): void => {
	store.set(url, record);
};

export const clearEtag = (url: string): void => {
	store.delete(url);
};

/** Forget every cached body, e.g. when someone signs in or out. */
export const clearAllEtags = (): void => {
	generation++;
	store.clear();
};
