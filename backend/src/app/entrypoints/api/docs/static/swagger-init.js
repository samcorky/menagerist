/*
 * Swagger UI setup for the Menagerist interactive API docs.
 *
 * - Sends same-origin cookies, so a session started with POST /auth/login works, and adds
 *   the server's own Origin to the generated curl snippets.
 * - Shows who is signed in (with sign-in actions) in Swagger's scheme bar, and the logo.
 *
 * The pure helpers are exposed on globalThis.MenageristSwaggerInit for tests.
 */
(function (root) {
	'use strict';

	var API_PREFIX = '/api/v1';
	var SESSION_PATHS = ['/auth/login', '/auth/logout', '/auth/setup', '/auth/password'];

	/**
	 * Sends same-origin cookies and tidies what the curl snippet shows. The browser sets the
	 * real Origin and Sec-Fetch-Site itself, which is what the server's same-origin check uses.
	 */
	function prepareRequest(req, origin) {
		req.credentials = 'same-origin';
		var headers = req.headers || (req.headers = {});
		// Swagger adds a Cookie header for the placeholder lock authorisation. Browsers drop it
		// (the real cookie goes with the request), but it would mislead in the curl snippet.
		for (var name in headers) {
			if (name.toLowerCase() === 'cookie') delete headers[name];
		}
		// Origin is a forbidden header name: fetch drops this and sends the identical real
		// value, so only the generated curl snippet shows it.
		headers.Origin = origin;
		return req;
	}

	/** True when a response URL is one that changes the session. */
	function isSessionChange(url, origin) {
		var parsed;
		try {
			parsed = new URL(url, origin);
		} catch (e) {
			return false;
		}
		if (parsed.origin !== origin) return false;
		for (var i = 0; i < SESSION_PATHS.length; i++) {
			if (parsed.pathname === API_PREFIX + SESSION_PATHS[i]) return true;
		}
		return false;
	}

	var LOGIN_PATH = '/login';
	var DOCS_PATH = '/api/docs';

	/** The app's sign-in page, returning to these docs afterwards. */
	function loginHref() {
		return LOGIN_PATH + '?next=' + encodeURIComponent(DOCS_PATH);
	}

	/**
	 * What the banner shows: a tone (ok, warn, error), a message and its actions.
	 * An action is either a link ({label, href}) or a button ({label, action}).
	 */
	function bannerModel(status, me, failed, notice) {
		if (failed) {
			return { tone: 'error', text: 'Could not check the sign-in state.', actions: [] };
		}
		if (me && me.password_expired) {
			return {
				tone: 'warn',
				text: 'Password change required before the API can be used.',
				actions: [{ label: 'Change password', href: '/settings/account' }]
			};
		}
		if (me) {
			return {
				tone: notice ? 'error' : 'ok',
				text: 'Signed in as ' + me.display_name + ' (' + me.role + ')',
				notice: notice || '',
				actions: [
					{ label: 'Open Menagerist', href: '/' },
					{ label: 'Sign out', action: 'signout' }
				]
			};
		}
		if (status && status.setup_required) {
			return {
				tone: 'warn',
				text: 'First run: create the administrator account.',
				actions: [{ label: 'Set up', href: '/setup' }]
			};
		}
		return {
			tone: 'warn',
			text: 'Not signed in. Sign in to try the API, or run POST /api/v1/auth/login below.',
			actions: [{ label: 'Sign in', href: loginHref() }]
		};
	}

	/** The logo URL when it is a same-origin path; otherwise null. */
	function safeLogoUrl(logo, origin) {
		var url = logo && logo.url;
		if (typeof url !== 'string' || url.charAt(0) !== '/' || url.charAt(1) === '/') return null;
		// Control characters, spaces and backslashes are stripped or rewritten by URL parsers.
		if (/[\u0000-\u0020\u007f\\]/.test(url)) return null;
		try {
			origin = origin || root.location.origin;
			return new URL(url, origin).origin === origin ? url : null;
		} catch (e) {
			return null;
		}
	}

	/** Names of the apiKey-in-cookie schemes in a plain `securityDefinitions` object. */
	function cookieSchemes(definitions) {
		return Object.keys(definitions || {}).filter(function (name) {
			var scheme = definitions[name];
			return scheme && scheme.type === 'apiKey' && scheme.in === 'cookie';
		});
	}

	/** Closes or opens Swagger's locks; never throws (they are only an indicator). */
	function applyLocks(ui, names, signedIn) {
		names.forEach(function (name) {
			try {
				if (signedIn) ui.preauthorizeApiKey(name, 'session');
				else ui.authActions.logout([name]);
			} catch (e) {
				// Leave this lock as it is.
			}
		});
	}

	/** Fills the banner element with the model, using text nodes only. */
	function renderBanner(doc, box, model, onSignOut) {
		function el(tag, className, text) {
			var node = doc.createElement(tag);
			node.className = className;
			if (text) node.textContent = text;
			return node;
		}
		box.className = 'menagerist-session menagerist-session-' + model.tone;
		var body = el('div', 'menagerist-session-body');
		body.appendChild(el('span', 'menagerist-session-text', model.text));
		if (model.notice) body.appendChild(el('span', 'menagerist-session-notice', model.notice));
		var actions = el('span', 'menagerist-session-actions');
		model.actions.forEach(function (action) {
			var node;
			if (action.href) {
				node = el('a', 'btn', action.label);
				node.setAttribute('href', action.href);
			} else {
				node = el('button', 'btn', action.label);
				node.setAttribute('type', 'button');
				node.addEventListener('click', onSignOut);
			}
			actions.appendChild(node);
		});
		body.appendChild(actions);
		box.replaceChildren(body);
		return box;
	}

	/**
	 * Fetches JSON. Resolves null for 401 when allowed (signed out); rejects on any other
	 * non-OK status or a network error.
	 */
	function fetchJson(url, allow401, fetchFn) {
		return (fetchFn || fetch)(url, {
			credentials: 'same-origin',
			headers: { Accept: 'application/json' }
		}).then(function (res) {
			if (res.ok) return res.json();
			if (allow401 && res.status === 401) return null;
			throw new Error('HTTP ' + res.status);
		});
	}

	function init() {
		var script = document.currentScript;
		var openapiUrl = script.getAttribute('data-openapi-url');
		var oauth2Redirect = script.getAttribute('data-oauth2-redirect');
		var origin = root.location.origin;

		var host = document.getElementById('swagger-ui');
		if (!root.SwaggerUIBundle) {
			var failure = document.createElement('div');
			failure.className = 'menagerist-session menagerist-session-error';
			failure.setAttribute('role', 'alert');
			failure.textContent = 'Could not load the Swagger UI assets from the CDN';
			host.appendChild(failure);
			return;
		}

		var ui;
		var state = { status: null, me: null, failed: false, notice: '', loaded: false };
		var sequence = 0;
		var locksFor = null;

		// One live region, created once so screen readers announce text changes inside it.
		var box = document.createElement('div');
		box.id = 'menagerist-session';
		box.setAttribute('role', 'status');
		box.setAttribute('aria-live', 'polite');

		function paint() {
			var model = bannerModel(state.status, state.me, state.failed, state.notice);
			renderBanner(document, box, model, signOut);
		}

		function signOut() {
			fetch(API_PREFIX + '/auth/logout', { method: 'POST', credentials: 'same-origin' })
				.then(function (res) {
					return res.ok ? '' : 'Could not sign out (HTTP ' + res.status + ').';
				})
				.catch(function () {
					return 'Could not sign out: the server did not answer.';
				})
				.then(function (notice) {
					return refreshBanner().then(function () {
						if (notice) {
							state.notice = notice;
							paint();
						}
					});
				});
		}

		function currentLogo() {
			try {
				var logo = ui.specSelectors.specJson().getIn(['info', 'x-logo']);
				return logo && logo.toJS ? logo.toJS() : null;
			} catch (e) {
				return null;
			}
		}

		// Make the per-operation locks follow the real session. Swagger only knows its own
		// credentials, so mark the cookie scheme authorised with a placeholder (not a credential;
		// the browser sends the real cookie) while signed in, and clear it otherwise.
		function syncLocks() {
			var signedIn = !!state.me;
			if (locksFor === signedIn) return;
			var names;
			try {
				names = cookieSchemes(ui.specSelectors.securityDefinitions().toJS());
			} catch (e) {
				names = [];
			}
			if (!names.length) return;
			locksFor = signedIn; // set first: the changes below trigger the observer again
			applyLocks(ui, names, signedIn);
		}

		// Swagger re-renders with React, so (re)insert whatever has gone missing.
		function ensure() {
			if (!state.loaded) return;
			syncLocks();
			var slot =
				host.querySelector('.scheme-container .schemes') || host.querySelector('.scheme-container');
			if (slot && box.parentNode !== slot) slot.insertBefore(box, slot.firstChild);
			var info = host.querySelector('.info');
			if (info && !info.querySelector('.menagerist-logo')) {
				var logo = currentLogo();
				var url = safeLogoUrl(logo, origin);
				if (url) {
					var img = document.createElement('img');
					img.className = 'menagerist-logo';
					img.setAttribute('src', url);
					img.setAttribute('alt', String(logo.altText || ''));
					info.insertBefore(img, info.firstChild);
				}
			}
		}

		function refreshBanner() {
			var mine = ++sequence;
			// The sign-in state comes from /auth/me; a failing /auth/status only loses the setup hint.
			return Promise.all([
				fetchJson(API_PREFIX + '/auth/status', false).catch(function () {
					return null;
				}),
				fetchJson(API_PREFIX + '/auth/me', true).then(
					function (me) {
						return { me: me, failed: false };
					},
					function () {
						return { me: null, failed: true };
					}
				)
			]).then(function (results) {
				if (mine !== sequence) return; // a newer refresh is in flight
				state = {
					status: results[0],
					me: results[1].me,
					failed: results[1].failed,
					notice: '',
					loaded: true
				};
				locksFor = null;
				paint();
				ensure();
			});
		}

		ui = root.SwaggerUIBundle({
			url: openapiUrl,
			dom_id: '#swagger-ui',
			layout: 'BaseLayout',
			deepLinking: true,
			showExtensions: true,
			showCommonExtensions: true,
			tryItOutEnabled: true,
			filter: true,
			persistAuthorization: false,
			withCredentials: true,
			oauth2RedirectUrl: root.location.origin + oauth2Redirect,
			presets: [root.SwaggerUIBundle.presets.apis, root.SwaggerUIBundle.SwaggerUIStandalonePreset],
			requestInterceptor: function (req) {
				return prepareRequest(req, origin);
			},
			responseInterceptor: function (res) {
				if (isSessionChange(res.url, origin)) setTimeout(refreshBanner, 0);
				return res;
			},
			onComplete: refreshBanner
		});
		new MutationObserver(ensure).observe(host, { childList: true, subtree: true });
	}

	root.MenageristSwaggerInit = {
		prepareRequest: prepareRequest,
		isSessionChange: isSessionChange,
		bannerModel: bannerModel,
		renderBanner: renderBanner,
		cookieSchemes: cookieSchemes,
		applyLocks: applyLocks,
		loginHref: loginHref,
		safeLogoUrl: safeLogoUrl,
		fetchJson: fetchJson
	};

	if (root.document && root.document.currentScript) init();
})(globalThis);
