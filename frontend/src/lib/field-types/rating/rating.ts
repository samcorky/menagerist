import { register } from '../registry';
import { readPropMeta } from '$lib/schema-meta';
import RatingInput from './RatingInput.svelte';
import RatingView from './RatingView.svelte';
import RatingSummary from './RatingSummary.svelte';

export const MAX_STARS = 5;

// Shape alone cannot tell a rating from a number, so it only matches an explicit kind.
register({
	kind: 'rating',
	label: 'Rating',
	canBeSubField: true,
	highlightable: true,
	displayOptions: [
		{
			key: 'stars',
			label: 'Stars',
			choices: [
				{ value: '3', label: '3 stars' },
				{ value: '5', label: '5 stars' },
				{ value: '10', label: '10 stars' }
			],
			default: String(MAX_STARS)
		}
	],
	toSchema: (f) => ({
		title: f.label,
		type: 'number',
		minimum: 1,
		maximum: Number(f.config?.stars ?? MAX_STARS),
		multipleOf: 1
	}),
	fromSchema: (key, prop, required) =>
		prop.type === 'number' && readPropMeta(prop).kind === 'rating'
			? {
					key,
					label: prop.title,
					kind: 'rating',
					required,
					options: [],
					subFields: [],
					config: { stars: String(prop.maximum ?? MAX_STARS) }
				}
			: null,
	InputWidget: RatingInput,
	ViewWidget: RatingView,
	SummaryWidget: RatingSummary
});
