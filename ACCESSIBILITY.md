# Accessibility

Menagerist should be usable whatever you use to reach it: keyboard, screen reader, touch, a small screen or high zoom. This page says what the project builds towards, where it falls short and how to report a barrier.

## What we aim for

These are the rules the interface is built to, set out in section 20 of the [design guidelines](frontend/DESIGN_GUIDELINES.md):

- Semantic HTML, with labels and alternative text for controls and images.
- Everything reachable and usable by keyboard, with visible focus. Every shortcut has a button, link or menu equivalent and is listed in the `?` overlay.
- Focus goes somewhere sensible after each action: into a dialog when it opens, back to the control that opened it when it closes, and never left on the page body or an invisible element.
- Updates such as toasts are announced to screen readers without taking focus.
- Contrast that suits both the light and dark themes. Colour is never the only carrier of meaning; important information also has an icon, label or text.
- Touch targets sized for fingers on touch devices, and a layout that works on a phone.
- Reduced motion respected.

## Where it falls short

Menagerist is early alpha. The rules above are how it is built, not a certification:

- It has not had a formal accessibility audit and does not claim conformance with WCAG or any other standard.
- The automated tests do not yet check accessibility, so a regression can slip through.
- Some screens are likely to miss the rules above, particularly newer ones and the advanced Explore view.

## Reporting a barrier

If something does not work with your keyboard, screen reader, zoom or display settings, please [open an issue](https://github.com/samcorky/menagerist/issues/new/choose) using the bug report form. Say what you were trying to do, what stopped you, and which browser and assistive technology you use. Accessibility problems are treated as bugs, not feature requests.
