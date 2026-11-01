import { describe, expect, it } from 'vitest';
import { isTextEntry } from '$lib/text-entry';

const el = (tagName: string, extra: Record<string, unknown> = {}) => ({ tagName, ...extra });

describe('isTextEntry', () => {
	it.each(['text', 'search', 'email', 'password', 'url', 'tel', 'number', 'date'])(
		'is true for an input of type %s',
		(type) => expect(isTextEntry(el('INPUT', { type }))).toBe(true)
	);

	it('is true for a textarea and a select-free contenteditable', () => {
		expect(isTextEntry(el('TEXTAREA'))).toBe(true);
		expect(isTextEntry(el('DIV', { isContentEditable: true }))).toBe(true);
	});

	it.each(['checkbox', 'radio', 'button', 'submit', 'file', 'range', 'color'])(
		'is false for an input of type %s, which opens no keyboard',
		(type) => expect(isTextEntry(el('INPUT', { type }))).toBe(false)
	);

	it('is false for buttons, links, selects and nothing', () => {
		expect(isTextEntry(el('BUTTON'))).toBe(false);
		expect(isTextEntry(el('A'))).toBe(false);
		expect(isTextEntry(el('SELECT'))).toBe(false);
		expect(isTextEntry(null)).toBe(false);
	});
});
