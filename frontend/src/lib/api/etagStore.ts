type EtagRecord = { etag?: string; lastModified?: string; data?: unknown };

const store = new Map<string, EtagRecord>();

export const getEtag = (url: string): EtagRecord | undefined => store.get(url);

export const setEtag = (url: string, record: EtagRecord): void => {
	store.set(url, record);
};

export const clearEtag = (url: string): void => {
	store.delete(url);
};
