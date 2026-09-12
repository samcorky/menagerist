/**
 * Delays a `true` loading state by `delayMs` before exposing it, so callers can
 * gate skeleton/spinner rendering on `.show` instead of the raw loading flag.
 *
 * Per DESIGN_GUIDELINES.md §13a: don't show a loading indicator for operations
 * expected to finish in under 300ms — flip to `false` hides `.show` immediately.
 */
export function delayedLoading(delayMs = 300) {
	let show = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;

	return {
		get show() {
			return show;
		},
		set(loading: boolean) {
			clearTimeout(timer);
			if (loading) {
				timer = setTimeout(() => (show = true), delayMs);
			} else {
				show = false;
			}
		}
	};
}
