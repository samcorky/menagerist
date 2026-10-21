// A small TLS-terminating reverse proxy for the cookie e2e tests (no dependencies).
//
//   node tls-proxy.mjs <listen-port> <target-port> [--strip-browser-headers]
//
// It serves HTTPS on <listen-port> with a self-signed certificate made at start-up (needs the
// `openssl` command) and forwards to http://127.0.0.1:<target-port>, passing the browser's
// headers through and adding X-Forwarded-For and X-Forwarded-Proto: https. The backend must list 127.0.0.1 in
// MENAGERIST_TRUSTED_PROXIES so it sees the HTTPS request, as behind a real proxy.
// With --strip-browser-headers it also removes Origin and Sec-Fetch-*, as a badly configured
// proxy would, so the browser check on the status page can be shown to notice it.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { request as httpRequest } from 'node:http';
import { createServer } from 'node:https';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2);
const strip = args.includes('--strip-browser-headers');
const [listenPort, targetPort] = args.filter((arg) => !arg.startsWith('--')).map(Number);
if (!listenPort || !targetPort) {
	console.error('usage: node tls-proxy.mjs <listen-port> <target-port> [--strip-browser-headers]');
	process.exit(2);
}

const dir = mkdtempSync(join(tmpdir(), 'menagerist-e2e-tls-'));
const keyFile = join(dir, 'key.pem');
const certFile = join(dir, 'cert.pem');
try {
	execFileSync(
		'openssl',
		[
			...['req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes'],
			...['-keyout', keyFile, '-out', certFile, '-days', '2', '-subj', '/CN=localhost'],
			...['-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1']
		],
		{ stdio: 'ignore' }
	);
} catch (error) {
	console.error('Could not make a self-signed certificate; is `openssl` installed?', error.message);
	process.exit(1);
}
const credentials = { key: readFileSync(keyFile), cert: readFileSync(certFile) };
rmSync(dir, { recursive: true, force: true });

const server = createServer(credentials, (req, res) => {
	const forwarded = { ...req.headers };
	if (strip) {
		for (const name of Object.keys(forwarded)) {
			if (name === 'origin' || name.startsWith('sec-fetch-')) delete forwarded[name];
		}
	}
	const upstream = httpRequest(
		{
			host: '127.0.0.1',
			port: targetPort,
			method: req.method,
			path: req.url,
			// The Host the browser used is kept, so the app rebuilds https://localhost:<listen-port>.
			headers: {
				...forwarded,
				// The app only reads X-Forwarded-Proto when X-Forwarded-For is present too.
				'x-forwarded-for': req.socket.remoteAddress ?? '127.0.0.1',
				'x-forwarded-proto': 'https'
			}
		},
		(answer) => {
			res.writeHead(answer.statusCode ?? 502, answer.headers);
			answer.pipe(res);
		}
	);
	upstream.on('error', () => {
		if (!res.headersSent) res.writeHead(502);
		res.end();
	});
	req.pipe(upstream);
});

server.listen(listenPort, '127.0.0.1', () => {
	console.log(`TLS proxy https://localhost:${listenPort} -> http://127.0.0.1:${targetPort}`);
});
for (const signal of ['SIGINT', 'SIGTERM'])
	process.on(signal, () => server.close(() => process.exit(0)));
