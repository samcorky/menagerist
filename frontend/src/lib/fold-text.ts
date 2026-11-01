/** Lower-cased text with accents removed, so "Café" and "cafe" compare equal. */
export function foldText(text: string): string {
	return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}
