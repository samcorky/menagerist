// Records which openapi.json the generated client was built from, so `poe` can tell when
// the client has gone stale (see ensure_api_client in scripts/poe_run.py).
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

const schema = readFileSync(new URL('../../openapi.json', import.meta.url));
const digest = createHash('sha256').update(schema).digest('hex');
writeFileSync(new URL('../src/lib/api/generated/schema.sha256', import.meta.url), `${digest}\n`);
