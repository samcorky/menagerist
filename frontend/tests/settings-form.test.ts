import { describe, it, expect } from 'vitest';
import type { SettingResponse } from '../src/lib/api/client';
import { coreForProp } from '../src/lib/field-types';
import {
	choicesOf,
	coerce,
	formProp,
	groupLabel,
	groupSettings,
	isChanged,
	lockedNote,
	restartNote,
	schemaProperties,
	sourceLabel,
	staleNote,
	updateBody
} from '../src/lib/settings-form';

function setting(over: Partial<SettingResponse>): SettingResponse {
	return {
		key: 'backup.schedule',
		group: 'backup',
		title: 'Backup schedule',
		description: null,
		value: '0 3 * * *',
		source: 'default',
		locked: false,
		env_name: 'MENAGERIST_BACKUP_SCHEDULE',
		restart_required: false,
		stored_invalid: false,
		...over
	};
}

describe('grouping', () => {
	it('labels known groups and tidies unknown ones', () => {
		expect(groupLabel('backup')).toBe('Backups');
		expect(groupLabel('scheduler')).toBe('Scheduled tasks');
		expect(groupLabel('media_storage')).toBe('Media storage');
	});

	it('keeps groups in the order they first appear', () => {
		const groups = groupSettings([
			setting({ key: 'backup.schedule' }),
			setting({ key: 'scheduler.run_history_per_job', group: 'scheduler' }),
			setting({ key: 'backup.other' })
		]);
		expect(groups.map((g) => [g.group, g.items.map((i) => i.key)])).toEqual([
			['backup', ['backup.schedule', 'backup.other']],
			['scheduler', ['scheduler.run_history_per_job']]
		]);
		expect(groups[0].label).toBe('Backups');
	});
});

describe('schema', () => {
	it('reads the properties of the schema document', () => {
		expect(schemaProperties({ properties: { a: { type: 'string' } } })).toEqual({
			a: { type: 'string' }
		});
		expect(schemaProperties(null)).toEqual({});
		expect(schemaProperties({ properties: 3 })).toEqual({});
	});

	it('turns an integer into a whole number the widgets know', () => {
		const prop = formProp({ type: 'integer', minimum: 1, title: 'Runs' });
		expect(prop).toMatchObject({ type: 'number', multipleOf: 1, minimum: 1, title: 'Runs' });
	});

	it('leaves other properties alone, including their hints', () => {
		const prop = { type: 'string', 'x-menagerist': { kind: 'cron' }, title: 'Schedule' };
		expect(formProp(prop)).toEqual(prop);
	});
});

describe('notes', () => {
	it('labels where a value came from', () => {
		expect(sourceLabel({ source: 'env' })).toBe('Set by your deployment');
		expect(sourceLabel({ source: 'instance' })).toBe('Changed here');
		expect(sourceLabel({ source: 'default' })).toBe('Default');
	});

	it('names the variable when the deployment sets a value', () => {
		expect(lockedNote({ locked: true, env_name: 'MENAGERIST_BACKUP_SCHEDULE' })).toBe(
			'Your deployment sets this (MENAGERIST_BACKUP_SCHEDULE). Remove it there to change it here.'
		);
		expect(lockedNote({ locked: true, env_name: null })).toMatch(/^Your deployment sets this\./);
		expect(lockedNote({ locked: false, env_name: 'X' })).toBeNull();
	});

	it('mentions a restart or a stale saved value only when it applies', () => {
		expect(restartNote({ restart_required: true })).toMatch(/restart/);
		expect(restartNote({ restart_required: false })).toBeNull();
		expect(staleNote({ stored_invalid: true })).toMatch(/default is in use/);
		expect(staleNote({ stored_invalid: false })).toBeNull();
	});
});

describe('coerce', () => {
	const runs = formProp({ type: 'integer', minimum: 1, title: 'Runs' });
	const schedule = formProp({ type: 'string', title: 'Schedule' });

	it('reads a number typed as text', () => {
		expect(coerce(runs, '100')).toEqual({ ok: true, value: 100 });
		expect(coerce(runs, ' 7 ')).toEqual({ ok: true, value: 7 });
		expect(coerce(runs, 12)).toEqual({ ok: true, value: 12 });
	});

	it('explains a number that will not do', () => {
		expect(coerce(runs, '')).toEqual({ ok: false, message: 'Enter a number.' });
		expect(coerce(runs, 'many')).toEqual({ ok: false, message: 'Enter a number.' });
		expect(coerce(runs, '2.5')).toEqual({ ok: false, message: 'Use a whole number.' });
		expect(coerce(runs, '0')).toEqual({ ok: false, message: 'Must be at least 1.' });
		expect(coerce(formProp({ type: 'number', maximum: 5 }), '6')).toEqual({
			ok: false,
			message: 'Must be at most 5.'
		});
	});

	it('trims a schedule and lets it be empty, which means off', () => {
		expect(coerce(schedule, ' 0 3 * * * ')).toEqual({ ok: true, value: '0 3 * * *' });
		expect(coerce(schedule, '')).toEqual({ ok: true, value: '' });
		expect(coerce(schedule, 5).ok).toBe(false);
	});

	it("accepts only one of a choice setting's options", () => {
		const channel = formProp({ type: 'string', enum: ['stable', 'preview'], title: 'Channel' });
		expect(coerce(channel, 'preview')).toEqual({ ok: true, value: 'preview' });
		expect(coerce(channel, 'nightly')).toEqual({
			ok: false,
			message: 'Choose one of the options.'
		});
		expect(coerce(channel, '').ok).toBe(false);
		expect(choicesOf(channel)).toEqual(['stable', 'preview']);
		// The page needs no widget of its own: the existing choice field renders it.
		expect(coreForProp(channel)?.kind).toBe('choice');
		expect(choicesOf(schedule)).toBeNull();
	});

	it('passes booleans and lists of strings through', () => {
		expect(coerce(formProp({ type: 'boolean' }), true)).toEqual({ ok: true, value: true });
		expect(coerce(formProp({ type: 'boolean' }), 'yes').ok).toBe(false);
		const list = formProp({ type: 'array', items: { type: 'string' } });
		expect(coerce(list, ['a', 'b'])).toEqual({ ok: true, value: ['a', 'b'] });
		expect(coerce(list, ['a', 1]).ok).toBe(false);
	});
});

describe('change tracking', () => {
	const runs = formProp({ type: 'integer', minimum: 1 });

	it('is unchanged when the draft means the current value', () => {
		expect(isChanged(runs, 100, '100')).toBe(false);
		expect(isChanged(runs, 100, '101')).toBe(true);
	});

	it('counts a draft that cannot be read as a change, so the error shows', () => {
		expect(isChanged(runs, 100, '')).toBe(true);
	});

	it('compares lists by content', () => {
		const list = formProp({ type: 'array', items: { type: 'string' } });
		expect(isChanged(list, ['a'], ['a'])).toBe(false);
		expect(isChanged(list, ['a'], ['b'])).toBe(true);
	});
});

describe('update body', () => {
	it('names one setting inside the values wrapper', () => {
		expect(updateBody('backup.schedule', '0 4 * * *')).toEqual({
			values: { 'backup.schedule': '0 4 * * *' }
		});
	});
});
