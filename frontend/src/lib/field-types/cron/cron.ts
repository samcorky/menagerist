import { readPropMeta } from '$lib/prop-meta';
import { registerCore } from '../core';
import CronInput from './CronInput.svelte';
import CronView from './CronView.svelte';

/**
 * A recurring-job schedule, stored as a raw five-part cron string. It is chosen only by an
 * explicit `kind` (rank 0), has no schema-editor half, so item types can never use it.
 */
registerCore({
	kind: 'cron',
	label: 'Schedule',
	matches: (prop) => prop.type === 'string' && readPropMeta(prop).kind === 'cron',
	rank: () => 0,
	InputWidget: CronInput,
	ViewWidget: CronView
});
