// Inputs that open no on-screen keyboard.
const NO_KEYBOARD = new Set([
	'checkbox',
	'radio',
	'button',
	'submit',
	'reset',
	'file',
	'range',
	'color',
	'image',
	'hidden'
]);

type Focusable = { tagName: string; type?: string; isContentEditable?: boolean } | null;

/** Whether focusing this element brings up a phone's keyboard. */
export function isTextEntry(el: Focusable): boolean {
	if (!el) return false;
	if (el.isContentEditable) return true;
	if (el.tagName === 'TEXTAREA') return true;
	return el.tagName === 'INPUT' && !NO_KEYBOARD.has((el.type ?? 'text').toLowerCase());
}
