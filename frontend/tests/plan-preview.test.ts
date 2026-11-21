// Server-renders PlanPreview: what an import done before leaves alone, changes and leaves out.
import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import PlanPreview from '$lib/components/plan-preview.svelte';
import type { ImportPlan } from '$lib/import-plan';

type Entity = ImportPlan['entities'][number];

function item(label: string, over: Partial<Entity>): Entity {
	return {
		kind: 'item',
		ref: label,
		label,
		action: 'unchanged',
		reason: null,
		changed: [],
		deleted: false,
		...over
	};
}

function html(entities: Entity[], fieldTitles: Record<string, string> = {}): string {
	const plan: ImportPlan = { ready: true, blockers: [], entities };
	return render(PlanPreview, {
		props: { plan, fieldTitles, onCancel: () => {}, onConfirm: () => {} }
	}).body;
}

describe('PlanPreview', () => {
	it('says what changed in the file, by the names people know the fields by', () => {
		const body = html(
			[
				item('Alien', {
					reason: 'Already imported.',
					matched_id: 'x',
					matched_name: 'Alien',
					changed: ['attributes.price', 'name']
				})
			],
			{ 'attributes.price': 'Price', name: 'Name' }
		);

		expect(body).toContain('Alien · Already imported. · Changed in the file: Price, Name');
	});

	it('names your item when it is called something else now', () => {
		const body = html([
			item('Alien', {
				reason: 'Already imported.',
				matched_id: 'x',
				matched_name: 'Alien (signed)'
			})
		]);

		expect(body).toContain('Yours is called Alien (signed)');
	});

	it('lists rows left out, with why', () => {
		const body = html([item('Ada', { action: 'skip', reason: 'No key.' })]);

		expect(body).toContain('Left out');
		expect(body).toContain('Ada · No key.');
	});
});
