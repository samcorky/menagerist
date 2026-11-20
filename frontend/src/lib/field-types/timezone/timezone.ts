import { readPropMeta } from '$lib/prop-meta';
import { registerCore } from '../core';
import TimezoneInput from './TimezoneInput.svelte';
import TimezoneView from './TimezoneView.svelte';

/**
 * A time zone setting: "browser" or an IANA name. Like the cron schedule it is chosen only by an
 * explicit `kind` (rank 0) and has no schema-editor half, so item types can never use it.
 */
registerCore({
	kind: 'timezone',
	label: 'Time zone',
	matches: (prop) => prop.type === 'string' && readPropMeta(prop).kind === 'timezone',
	rank: () => 0,
	InputWidget: TimezoneInput,
	ViewWidget: TimezoneView
});
