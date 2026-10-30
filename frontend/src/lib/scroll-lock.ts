type Root = Pick<Element, 'setAttribute' | 'removeAttribute'>;

// The app scrolls inside #main-scroll, not the body, so a modal's own body lock does not stop the
// page behind it moving (on a phone, with the keyboard open, it drags along under a sheet).
// Holders are counted so stacked dialogs release the page only when the last one closes.
let holders = 0;

export function lockPageScroll(root: Root = document.documentElement): () => void {
	holders += 1;
	root.setAttribute('data-scroll-locked', '');
	let released = false;
	return () => {
		if (released) return;
		released = true;
		holders -= 1;
		if (holders === 0) root.removeAttribute('data-scroll-locked');
	};
}
