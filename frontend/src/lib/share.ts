import { toast } from 'svelte-sonner';
import { copyText } from '$lib/clipboard';

/** What happened to a share: the person picked somewhere, backed out, or the link was copied. */
export type ShareResult = 'shared' | 'cancelled' | 'copied' | 'failed';

/** The parts of `navigator` sharing uses, so tests can pass their own. */
export type ShareTarget = Pick<Navigator, 'share' | 'canShare'>;

/** A page's address on this origin, with the app's base path, ready to hand to another app. */
export function absoluteUrl(path: string, origin: string = window.location.origin): string {
	return new URL(path, origin).href;
}

/**
 * Hands a title and link to the device's share sheet (the Web Share API). Where the browser has
 * none, or refuses, the link is copied instead, so there is always a way to pass it on.
 */
export async function shareLink(
	{ title, url }: { title: string; url: string },
	nav: Partial<ShareTarget> | undefined = typeof navigator === 'undefined' ? undefined : navigator
): Promise<ShareResult> {
	const data = { title, url };
	if (nav?.share && (nav.canShare?.(data) ?? true)) {
		try {
			await nav.share(data);
			return 'shared';
		} catch (error) {
			// Backing out of the share sheet is a choice, not a failure.
			if (error instanceof DOMException && error.name === 'AbortError') return 'cancelled';
			// Anything else (a refused share) falls back to copying.
		}
	}
	return (await copyText(url)) ? 'copied' : 'failed';
}

/** `shareLink`, telling the person when the link was copied or could not be passed on. */
export async function shareLinkWithFeedback(link: { title: string; url: string }): Promise<void> {
	const result = await shareLink(link);
	if (result === 'copied') toast.success('Link copied');
	else if (result === 'failed') toast.error('Could not share or copy the link');
}
