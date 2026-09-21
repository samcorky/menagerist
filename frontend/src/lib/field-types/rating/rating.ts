import { register } from '../registry';
import { readPropMeta } from '$lib/schema-meta';
import RatingInput from './RatingInput.svelte';
import RatingView from './RatingView.svelte';

export const MAX_STARS = 5;

// Shape alone cannot tell a rating from a number, so it only matches an explicit kind.
register({
	kind: 'rating',
	label: 'Rating',
	canBeSubField: true,
	toSchema: (f) => ({
		title: f.label,
		type: 'number',
		minimum: 1,
		maximum: MAX_STARS,
		multipleOf: 1
	}),
	fromSchema: (key, prop, required) =>
		prop.type === 'number' && readPropMeta(prop).kind === 'rating'
			? { key, label: prop.title, kind: 'rating', required, options: [], subFields: [] }
			: null,
	InputWidget: RatingInput,
	ViewWidget: RatingView
});
