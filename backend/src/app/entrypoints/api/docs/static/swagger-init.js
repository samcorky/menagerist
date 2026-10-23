/*
 * Swagger UI setup for the Menagerist interactive API docs.
 *
 * - Sends same-origin cookies, so a session started with POST /auth/login works, and adds
 *   the server's own Origin to the generated curl snippets.
 * - Leaves the bearer-token scheme in the Authorize dialog (the cookie cannot be set by hand),
 *   under a "Browser session" block with Sign in and Sign out.
 * - Shows the page-level status in Swagger's scheme bar (session or API token, and whether the
 *   token works), and the logo.
 *   The two sign-in requests start at once, but the banner is only put on the page when Swagger
 *   has finished rendering. It shows a "checking" state if the answer is still on its way.
 *
 * The pure helpers are exposed on globalThis.MenageristSwaggerInit for tests.
 */
(function (root) {
  "use strict";

  var API_PREFIX = "/api/v1";
  var SESSION_PATHS = [
    "/auth/login",
    "/auth/logout",
    "/auth/setup",
    "/auth/password",
  ];

  /**
   * Sends same-origin cookies and tidies what the curl snippet shows. The browser sets the
   * real Origin and Sec-Fetch-Site itself, which is what the server's same-origin check uses.
   */
  function prepareRequest(req, origin) {
    req.credentials = "same-origin";
    var headers = req.headers || (req.headers = {});
    // Swagger adds a Cookie header for the placeholder lock authorisation. Browsers drop it
    // (the real cookie goes with the request), but it would mislead in the curl snippet.
    for (var name in headers) {
      if (name.toLowerCase() === "cookie") delete headers[name];
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

  var LOGIN_PATH = "/login";
  var DOCS_PATH = "/api/docs";

  /** The app's sign-in page, returning to these docs afterwards. */
  function loginHref() {
    return LOGIN_PATH + "?next=" + encodeURIComponent(DOCS_PATH);
  }

  /** Plural-aware count for the token banner. */
  function permissionCount(n) {
    return n + (n === 1 ? " permission" : " permissions");
  }

  var TOKEN_REJECTED =
    "This API token was not accepted (invalid, expired or revoked).";
  var TOKEN_UNCHECKED = "Could not check the API token.";
  var TOKEN_PRECEDENCE =
    "An API token, when set below, takes precedence over the session for Try it out.";
  var TOKEN_HINT = "Or use a token instead of a session.";

  /**
   * What the banner and the dialog's session block show. `text` and `actions` are the page
   * banner (the page-level status); `sessionText` and `sessionActions` are the browser session
   * alone, for the dialog. An action is a link ({label, href}) or a button ({label, action}).
   * `token` is null when Swagger holds no API token, else {status: checking | ok | rejected |
   * failed, count}. While `checking` the sign-in answer is not known yet, so it is busy.
   */
  function bannerModel(status, me, failed, notice, checking, token) {
    if (checking) {
      return {
        tone: "info",
        text: "Checking sign-in state…",
        sessionText: "Checking sign-in state…",
        busy: true,
        actions: [],
        sessionActions: [],
      };
    }
    if (failed) {
      return {
        tone: "error",
        text: "Could not check the sign-in state.",
        sessionText: "Could not check the sign-in state.",
        actions: [],
        sessionActions: [],
      };
    }
    if (me && me.password_expired) {
      var change = [{ label: "Change password", href: "/settings/account" }];
      var expired = "Password change required before the API can be used.";
      return {
        tone: "warn",
        text: expired,
        sessionText: expired,
        actions: change,
        sessionActions: change,
      };
    }
    var tokenState = token && token.status;
    if (me) {
      var sessionText =
        "Signed in as " + me.display_name + " (browser session).";
      var text = sessionText;
      var tone = "ok";
      if (token) {
        text =
          "Signed in as " +
          me.display_name +
          ". An API token is also set and takes precedence for Try it out.";
        if (tokenState === "rejected") {
          text += " " + TOKEN_REJECTED;
          tone = "warn";
        } else if (tokenState === "failed") {
          text += " " + TOKEN_UNCHECKED;
          tone = "warn";
        }
      }
      var signOut = { label: "Sign out", action: "signout" };
      return {
        tone: notice ? "error" : tone,
        text: text,
        sessionText: sessionText,
        notice: notice || "",
        actions: [{ label: "Open Menagerist", href: "/" }, signOut],
        sessionActions: [signOut],
      };
    }
    var setup = !!(status && status.setup_required);
    var signedOutText = setup
      ? "First run: create the administrator account."
      : "Not signed in.";
    var sessionActions = setup
      ? [{ label: "Set up", href: "/setup" }]
      : [{ label: "Sign in", href: loginHref() }];
    var model = {
      tone: "warn",
      text: setup
        ? "First run: create the administrator account. Use Authorize to set up."
        : "Not signed in. Use Authorize to sign in or add an API token.",
      sessionText: signedOutText,
      actions: [],
      sessionActions: sessionActions,
    };
    if (token) {
      if (tokenState === "ok") {
        model.tone = "ok";
        model.text =
          "Using an API token with " + permissionCount(token.count) + ".";
      } else if (tokenState === "rejected") {
        model.text = TOKEN_REJECTED;
      } else if (tokenState === "failed") {
        model.tone = "error";
        model.text = TOKEN_UNCHECKED;
      } else {
        model.tone = "info";
        model.text = "Using an API token.";
      }
    }
    return model;
  }

  /**
   * Verifies a bearer token once. Resolves {status: 'ok', count}, {status: 'rejected'} (401)
   * or {status: 'failed'} (anything else, or no answer). Cookies are omitted so a session
   * cannot mask a bad token. The token is only ever sent as the header.
   */
  function checkToken(token, fetchFn) {
    return (fetchFn || fetch)(API_PREFIX + "/auth/me/permissions", {
      credentials: "omit",
      headers: { Accept: "application/json", Authorization: "Bearer " + token },
    }).then(
      function (res) {
        if (res.status === 401) return { status: "rejected" };
        if (!res.ok) return { status: "failed" };
        return res.json().then(
          function (body) {
            var list = body && body.permissions;
            return Array.isArray(list)
              ? { status: "ok", count: list.length }
              : { status: "failed" };
          },
          function () {
            return { status: "failed" };
          },
        );
      },
      function () {
        return { status: "failed" };
      },
    );
  }

  /** Names of the HTTP bearer schemes in a plain `securityDefinitions` object. */
  function bearerSchemes(definitions) {
    return Object.keys(definitions || {}).filter(function (name) {
      var scheme = definitions[name];
      return (
        scheme &&
        scheme.type === "http" &&
        String(scheme.scheme || "").toLowerCase() === "bearer"
      );
    });
  }

  /** The token Swagger holds for the first bearer scheme that has one, from a plain `authorized` object. */
  function bearerToken(authorized, names) {
    for (var i = 0; i < names.length; i++) {
      var entry = authorized && authorized[names[i]];
      if (entry && typeof entry.value === "string" && entry.value)
        return entry.value;
    }
    return "";
  }

  /** The logo URL when it is a same-origin path; otherwise null. */
  function safeLogoUrl(logo, origin) {
    var url = logo && logo.url;
    if (
      typeof url !== "string" ||
      url.charAt(0) !== "/" ||
      url.charAt(1) === "/"
    )
      return null;
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
      return scheme && scheme.type === "apiKey" && scheme.in === "cookie";
    });
  }

  /**
   * The Authorize dialog's blocks for the named schemes. Swagger titles a block with the
   * scheme name, so a block is the one whose heading starts with it.
   */
  function findSchemeBlocks(container, names) {
    var found = [];
    container.querySelectorAll(".auth-container").forEach(function (block) {
      var heading = block.querySelector("h4");
      // Swagger puts a no-break space after the name.
      var title = (heading ? heading.textContent : "")
        .replace(/\u00a0/g, " ")
        .trim();
      var match = names.some(function (name) {
        return title === name || title.indexOf(name + " ") === 0;
      });
      if (match) found.push(block);
    });
    return found;
  }

  /** Hides the Authorize dialog's block for each named scheme. Returns how many it hid. */
  function hideSchemeBlocks(container, names) {
    var blocks = findSchemeBlocks(container, names);
    blocks.forEach(function (block) {
      if (!block.hidden) block.hidden = true;
    });
    return blocks.length;
  }

  /** Puts the "use a token instead" hint under each named block's heading, once. */
  function hintSchemeBlocks(doc, container, names) {
    findSchemeBlocks(container, names).forEach(function (block) {
      if (block.querySelector(".menagerist-token-hint")) return;
      var heading = block.querySelector("h4");
      if (!heading || !heading.parentNode) return;
      var hint = doc.createElement("p");
      hint.className = "menagerist-token-hint";
      hint.textContent = TOKEN_HINT;
      heading.parentNode.insertBefore(hint, heading.nextSibling);
    });
  }

  /** Closes or opens Swagger's locks; never throws (they are only an indicator). */
  function applyLocks(ui, names, signedIn) {
    names.forEach(function (name) {
      try {
        if (signedIn) ui.preauthorizeApiKey(name, "session");
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
    box.className = "menagerist-session menagerist-session-" + model.tone;
    box.setAttribute("aria-busy", model.busy ? "true" : "false");
    var body = el("div", "menagerist-session-body");
    var text = el("span", "menagerist-session-text", model.text);
    if (model.busy) {
      var spinner = el("span", "menagerist-spinner");
      spinner.setAttribute("aria-hidden", "true");
      var lead = el("span", "menagerist-session-lead");
      lead.appendChild(spinner);
      lead.appendChild(text);
      body.appendChild(lead);
    } else {
      body.appendChild(text);
    }
    if (model.notice)
      body.appendChild(el("span", "menagerist-session-notice", model.notice));
    var actions = el("span", "menagerist-session-actions");
    model.actions.forEach(function (action) {
      var node;
      if (action.href) {
        node = el("a", "btn", action.label);
        node.setAttribute("href", action.href);
      } else {
        node = el("button", "btn", action.label);
        node.setAttribute("type", "button");
        node.addEventListener("click", onSignOut);
      }
      actions.appendChild(node);
    });
    body.appendChild(actions);
    box.replaceChildren(body);
    return box;
  }

  /**
   * Fills the Authorize dialog's Browser session block with the model, in the markup and classes Swagger
   * uses for its own scheme blocks. Sign in is a link (it navigates) styled as the primary button.
   */
  function renderDialogSession(doc, section, model, onSignOut) {
    function el(tag, className, text) {
      var node = doc.createElement(tag);
      if (className) node.className = className;
      if (text) node.textContent = text;
      return node;
    }
    section.className = "auth-container";
    section.setAttribute("aria-busy", model.busy ? "true" : "false");
    var nodes = [
      el("h4", "", "Browser session"),
      el("p", "menagerist-session-text", model.sessionText || model.text),
    ];
    if (model.notice)
      nodes.push(el("p", "menagerist-session-notice", model.notice));
    var buttons = el("div", "auth-btn-wrapper");
    (model.sessionActions || model.actions).forEach(function (action) {
      var node;
      if (action.href) {
        node = el("a", "btn modal-btn auth authorize button", action.label);
        node.setAttribute("href", action.href);
      } else {
        node = el("button", "btn modal-btn auth button", action.label);
        node.setAttribute("type", "button");
        node.addEventListener("click", onSignOut);
      }
      buttons.appendChild(node);
    });
    nodes.push(buttons);
    nodes.push(el("p", "menagerist-token-precedence", TOKEN_PRECEDENCE));
    section.replaceChildren.apply(section, nodes);
    return section;
  }

  /**
   * Fetches JSON. Resolves null for 401 when allowed (signed out); rejects on any other
   * non-OK status or a network error.
   */
  function fetchJson(url, allow401, fetchFn) {
    return (fetchFn || fetch)(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }).then(function (res) {
      if (res.ok) return res.json();
      if (allow401 && res.status === 401) return null;
      throw new Error("HTTP " + res.status);
    });
  }

  function init() {
    var script = document.currentScript;
    var openapiUrl = script.getAttribute("data-openapi-url");
    var oauth2Redirect = script.getAttribute("data-oauth2-redirect");
    var origin = root.location.origin;

    var host = document.getElementById("swagger-ui");
    if (!root.SwaggerUIBundle) {
      var failure = document.createElement("div");
      failure.className = "menagerist-session menagerist-session-error";
      failure.setAttribute("role", "alert");
      failure.textContent = "Could not load the Swagger UI assets from the CDN";
      host.appendChild(failure);
      return;
    }

    var ui;
    var state = {
      status: null,
      me: null,
      failed: false,
      notice: "",
      checking: true,
    };
    var sequence = 0;
    var locksFor = null;
    // The API token Swagger holds (kept here only to notice a change, never shown) and its check.
    var tokenSeen = "";
    var tokenState = null;
    var tokenSequence = 0;
    // The banner stays off the page until Swagger has rendered, so it never sits above an empty page.
    var revealed = false;

    // One live region, created once so screen readers announce text changes inside it.
    var box = document.createElement("div");
    box.id = "menagerist-session";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");

    // The same sign-in state inside the Authorize dialog, in Swagger's own block markup, in
    // place of its cookie block (whose Logout only clears the placeholder lock).
    var dialogSection = document.createElement("div");
    dialogSection.id = "menagerist-session-dialog";
    dialogSection.setAttribute("role", "status");
    dialogSection.setAttribute("aria-live", "polite");

    function paint() {
      var model = bannerModel(
        state.status,
        state.me,
        state.failed,
        state.notice,
        state.checking,
        tokenState,
      );
      renderBanner(document, box, model, signOut);
      renderDialogSession(document, dialogSection, model, signOut);
    }

    function signOut() {
      fetch(API_PREFIX + "/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      })
        .then(function (res) {
          return res.ok ? "" : "Could not sign out (HTTP " + res.status + ").";
        })
        .catch(function () {
          return "Could not sign out: the server did not answer.";
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
        var logo = ui.specSelectors.specJson().getIn(["info", "x-logo"]);
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

    function bearerSchemeNames() {
      try {
        return bearerSchemes(ui.specSelectors.securityDefinitions().toJS());
      } catch (e) {
        return [];
      }
    }

    // Verify the token Swagger holds once per change, so the banner can say if it works.
    function syncToken() {
      var token = "";
      try {
        token = bearerToken(
          ui.authSelectors.authorized().toJS(),
          bearerSchemeNames(),
        );
      } catch (e) {
        token = "";
      }
      if (token === tokenSeen) return;
      tokenSeen = token;
      var mine = ++tokenSequence;
      if (!token) {
        tokenState = null;
        paint();
        return;
      }
      tokenState = { status: "checking" };
      paint();
      checkToken(token).then(function (result) {
        if (mine !== tokenSequence) return; // the token changed meanwhile
        tokenState = result;
        paint();
        ensure();
      });
    }

    function cookieSchemeNames() {
      try {
        return cookieSchemes(ui.specSelectors.securityDefinitions().toJS());
      } catch (e) {
        return [];
      }
    }

    // Swagger re-renders with React, so (re)insert whatever has gone missing. If its scheme bar
    // is missing (the spec failed to load) the banner sits at the top of the page instead.
    function ensure() {
      if (!state.checking) syncLocks();
      syncToken();
      var dialog = host.querySelector(".dialog-ux");
      if (dialog) {
        hideSchemeBlocks(dialog, cookieSchemeNames());
        hintSchemeBlocks(document, dialog, bearerSchemeNames());
        var content = dialog.querySelector(".modal-ux-content");
        if (content && dialogSection.parentNode !== content) {
          content.insertBefore(dialogSection, content.firstChild);
        }
      }
      if (revealed) {
        var slot =
          host.querySelector(".scheme-container .schemes") ||
          host.querySelector(".scheme-container");
        if (slot) {
          if (box.parentNode !== slot) slot.insertBefore(box, slot.firstChild);
        } else if (!host.contains(box)) {
          host.insertBefore(box, host.firstChild);
        }
      }
      var info = host.querySelector(".info");
      if (info && !info.querySelector(".menagerist-logo")) {
        var logo = currentLogo();
        var url = safeLogoUrl(logo, origin);
        if (url) {
          var img = document.createElement("img");
          img.className = "menagerist-logo";
          img.setAttribute("src", url);
          img.setAttribute("alt", String(logo.altText || ""));
          info.insertBefore(img, info.firstChild);
        }
      }
    }

    function reveal() {
      revealed = true;
      ensure();
    }

    function refreshBanner() {
      var mine = ++sequence;
      state = Object.assign({}, state, { checking: true });
      paint();
      ensure();
      // The sign-in state comes from /auth/me; a failing /auth/status only loses the setup hint.
      return Promise.all([
        fetchJson(API_PREFIX + "/auth/status", false).catch(function () {
          return null;
        }),
        fetchJson(API_PREFIX + "/auth/me", true).then(
          function (me) {
            return { me: me, failed: false };
          },
          function () {
            return { me: null, failed: true };
          },
        ),
      ]).then(function (results) {
        if (mine !== sequence) return; // a newer refresh is in flight
        state = {
          status: results[0],
          me: results[1].me,
          failed: results[1].failed,
          notice: "",
          checking: false,
        };
        locksFor = null;
        paint();
        ensure();
      });
    }

    ui = root.SwaggerUIBundle({
      url: openapiUrl,
      dom_id: "#swagger-ui",
      layout: "BaseLayout",
      deepLinking: true,
      showExtensions: true,
      showCommonExtensions: true,
      tryItOutEnabled: true,
      filter: true,
      persistAuthorization: false,
      withCredentials: true,
      oauth2RedirectUrl: root.location.origin + oauth2Redirect,
      presets: [
        root.SwaggerUIBundle.presets.apis,
        root.SwaggerUIBundle.SwaggerUIStandalonePreset,
      ],
      requestInterceptor: function (req) {
        return prepareRequest(req, origin);
      },
      responseInterceptor: function (res) {
        if (isSessionChange(res.url, origin)) setTimeout(refreshBanner, 0);
        return res;
      },
      onComplete: reveal,
    });
    // If Swagger never completes (for example the spec fails to load) still show the sign-in state.
    root.addEventListener("load", function () {
      setTimeout(reveal, 3000);
    });
    new MutationObserver(ensure).observe(host, {
      childList: true,
      subtree: true,
    });
    // Ask now, in parallel with Swagger loading the spec.
    refreshBanner();
  }

  root.MenageristSwaggerInit = {
    prepareRequest: prepareRequest,
    isSessionChange: isSessionChange,
    bannerModel: bannerModel,
    checkToken: checkToken,
    bearerSchemes: bearerSchemes,
    bearerToken: bearerToken,
    hintSchemeBlocks: hintSchemeBlocks,
    findSchemeBlocks: findSchemeBlocks,
    renderBanner: renderBanner,
    renderDialogSession: renderDialogSession,
    cookieSchemes: cookieSchemes,
    applyLocks: applyLocks,
    hideSchemeBlocks: hideSchemeBlocks,
    loginHref: loginHref,
    safeLogoUrl: safeLogoUrl,
    fetchJson: fetchJson,
  };

  if (root.document && root.document.currentScript) init();
})(globalThis);
