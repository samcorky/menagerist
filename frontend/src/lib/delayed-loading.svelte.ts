/** Delays a loading state by delayMs to avoid UI flicker for quick operations. */
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
