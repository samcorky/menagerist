import { previewCache, previewPlan, nextRuns, type NextRuns } from '$lib/schedule-preview';

export type PreviewState =
	| { status: 'idle' }
	| { status: 'off' }
	| { status: 'loading'; previous: NextRuns }
	| { status: 'ready'; runs: NextRuns }
	| { status: 'error' };

const DEBOUNCE_MS = 400;

/** When the expression would next run. Call during component initialisation. */
export function useSchedulePreview(expression: () => string): { readonly state: PreviewState } {
	let state = $state<PreviewState>({ status: 'idle' });
	let last: NextRuns = null;
	let first = true;

	$effect(() => {
		const expr = expression();
		const plan = previewPlan(expr);
		last = plan === 'fetch' ? last : null;
		if (plan !== 'fetch') {
			state = { status: plan === 'off' ? 'off' : 'idle' };
			return;
		}
		state = { status: 'loading', previous: last };

		let stale = false;
		const load = async () => {
			const result = await previewCache.get(expr);
			if (stale) return;
			if (result instanceof Error) {
				last = null;
				state = { status: 'error' };
			} else if (result === 'unavailable') {
				last = null;
				state = { status: 'idle' };
			} else {
				last = nextRuns(result);
				state = { status: 'ready', runs: last };
			}
		};

		let timer: ReturnType<typeof setTimeout> | undefined;
		if (first) void load();
		else timer = setTimeout(load, DEBOUNCE_MS);
		first = false;

		return () => {
			stale = true;
			clearTimeout(timer);
		};
	});

	return {
		get state() {
			return state;
		}
	};
}
