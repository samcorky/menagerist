/**
 * Copies text to the clipboard. Where the async clipboard is unavailable or refused (plain HTTP,
 * some browsers), the field is selected and the legacy copy command is tried. If that fails too,
 * the field stays selected so the text can be copied by hand.
 */
export async function copyText(text: string, field?: HTMLInputElement | null): Promise<boolean> {
	try {
		await navigator.clipboard.writeText(text);
		return true;
	} catch {
		if (!field) return false;
		field.focus();
		field.select();
		try {
			return document.execCommand('copy');
		} catch {
			return false;
		}
	}
}
