import { Validator } from '@cfworker/json-schema';

export type ClientError = {
	keyword: string;
	keywordLocation: string;
	instanceLocation: string;
	error: string;
};

export type SafeValidator = {
	/** True once a pattern the browser rejected made the validator skip all pattern rules. */
	readonly degraded: boolean;
	validate: (attributes: unknown) => ClientError[];
};

type Schema = Record<string, unknown>;

/** Copy of a schema without `pattern` keywords. Property names such as `pattern` are kept. */
export function stripPatterns(schema: Schema): Schema {
	const out: Schema = {};
	for (const [key, value] of Object.entries(schema)) {
		if (key === 'pattern' && typeof value === 'string') continue;
		if (key === 'properties' && typeof value === 'object' && value !== null) {
			out[key] = Object.fromEntries(
				Object.entries(value as Record<string, Schema>).map(([k, v]) => [k, stripPatterns(v)])
			);
		} else if (key === 'items' && typeof value === 'object' && value !== null) {
			out[key] = stripPatterns(value as Schema);
		} else if (key === 'allOf' && Array.isArray(value)) {
			const kept = value
				.map((item) => stripPatterns(item as Schema))
				.filter((item) => Object.keys(item).length > 0);
			if (kept.length > 0) out[key] = kept;
		} else {
			out[key] = value;
		}
	}
	return out;
}

/**
 * Wrap `@cfworker/json-schema`, which throws from `validate()` when a pattern is not a valid
 * JavaScript regular expression (for example one written through the API). Rather than break the
 * form, drop the pattern rules and carry on; the server still enforces them.
 */
export function createSafeValidator(schemaObject: object): SafeValidator {
	const schema = schemaObject as Schema;
	let validator = new Validator(schema as object, '2020-12', false);
	let degraded = false;

	const run = (attributes: unknown): ClientError[] =>
		validator.validate(attributes).errors.map((e) => ({
			keyword: e.keyword,
			keywordLocation: e.keywordLocation,
			instanceLocation: e.instanceLocation,
			error: e.error
		}));

	return {
		get degraded() {
			return degraded;
		},
		validate(attributes) {
			try {
				return run(attributes);
			} catch {
				if (degraded) return [];
				degraded = true;
				validator = new Validator(stripPatterns(schema) as object, '2020-12', false);
				try {
					return run(attributes);
				} catch {
					return [];
				}
			}
		}
	};
}
