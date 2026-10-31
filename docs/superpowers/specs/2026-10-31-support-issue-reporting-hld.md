# Menagerist — Support & Issue Reporting

**High-Level Design (HLD)**
**Status:** Proposed / for review
**Version:** 0.3 (corrected against the code)
**Date:** 2026-10-31
**Target:** `feature/initial-implementation`
**Scope:** Provider-independent bug reports, feature requests and general suggestions, with privacy-preserving diagnostics

## 1. Summary

Provide a first-class **Report a problem / Request a feature / Share a suggestion** experience in Menagerist. The frontend collects a small, explicitly allowlisted diagnostic snapshot and previews it before sharing. A backend **query endpoint** resolves the appropriate external issue creation URL (GitHub initially). The frontend renders a normal external link, opened in a new tab by the user.

The backend owns provider selection, report-type-to-template mapping, diagnostic formatting and URL construction. The frontend owns the user experience and safe capture of client context. **Menagerist never creates the issue itself.** No third-party API credentials, persistence, telemetry or background jobs are required.

### Goals

- Make reporting bugs, requesting features and sharing suggestions easy from Settings and unexpected errors.
- Include useful non-private technical context without sharing collection content or instance identity.
- Keep frontend independent of GitHub, GitLab and template field names.
- Reuse build metadata, API client, SvelteKit routing and existing UI patterns.
- Keep the implementation small, testable and extensible.

### Non-goals

- Anonymous issue submission, embedded issue creation or tracker authentication.
- Automatic uploading of logs, screenshots, traces or support bundles.
- Monitoring/telemetry, error history, issue tracking inside Menagerist.
- A dynamically installed plugin system for issue providers.

## 2. Current codebase touchpoints (verified)

Inspected on `feature/initial-implementation`:

| Existing path | Relevant finding / proposed change |
|---|---|
| `frontend/src/routes/settings/+page.svelte` | Card-style Settings index, including System status. Add a Help & Feedback card, and a matching destination in `lib/manage-nav.ts`, which feeds the app sidebar. |
| `frontend/src/routes/+error.svelte` | Three branches: 404, 5xx and any other status. Add the report action to the 5xx and other branches only. |
| `frontend/src/routes/+layout.svelte` | Svelte 5 shell, navigation, Sonner toasts. Keep reporting logic out of root layout. |
| `frontend/src/lib/components/user-menu.svelte` | Existing account dropdown. Optional secondary entry point, not required for MVP. |
| `frontend/src/routes/status/+page.svelte` | Uses `getVersion` (public: name and version) and `getVersionDetail` (administrators only: commit, branch, dirty flag, build time). A member's report page can only call `getVersion`; the richer build data stays on the backend. |
| `frontend/openapi-ts.config.ts` | `@hey-api/openapi-ts` with `@hey-api/client-fetch`, TypeScript and SDK generation. Add backend schema and regenerate; do not edit generated code. |
| `frontend/package.json` | Svelte 5, SvelteKit, Bits UI, Lucide, Sonner, Vitest, Playwright. No new frontend dependencies expected. |

**Verified backend:** there is no `support` module. The modules are `backup`, `collections`, `examples`, `graph`, `identity`, `media`, `presets`, `scheduling`, `settings` and `system`; the version endpoints and `AppInfo` live in `system`, so the new query belongs in `modules/system/application/`, not a new module. `platform/app_info.py` already loads build metadata including `build.repository_url`, which is the trusted repository for URL building. Public routes go on `public_v1_router` (no cookie, no CSRF check), and every use case declares an `access` stance, pinned in `tests/architecture/test_access_stances.py`. The frontend error path is `lib/api/errors.ts` (`errorMessage`, `networkAwareError`) plus the auth and ETag interceptors in `lib/api/`; nothing central records the failed operation, so Stage B needs a new hook. `.github/ISSUE_TEMPLATE/` does not exist, so the three issue forms are new files.

## 3. User stories and acceptance criteria

### US-01 — Report a bug
As a user, I can open a report page, review the diagnostics, and follow a link to the upstream issue tracker so I can report a problem without locating the project repository.

**Acceptance:** accessible from Settings; selects bug template; link opens a new tab; no issue is submitted automatically.

### US-02 — Request a feature
As a user, I can request new functionality and describe the problem it would solve, without sending irrelevant error diagnostics.

**Acceptance:** distinct `feature` type; backend selects provider-specific feature form; diagnostics off by default; the tracker form asks for the user problem, desired outcome, examples and possible alternatives, not technical reproduction steps.

### US-02a — Share an improvement or suggestion
As a user, I can suggest an improvement to an existing feature, workflow, documentation or user experience without having to present it as a bug or a fully formed feature request.

**Acceptance:** distinct `suggestion` type and tracker template; form asks what could improve, why it matters and an optional example; no error diagnostics by default.

### US-02b — Report from a relevant page
As a user, I can suggest an improvement while viewing the relevant area of Menagerist.

**Acceptance:** the report page may offer the matched frontend route pattern as optional context, clearly shown to the user; no concrete item IDs, names, search terms or URL query parameters are transferred.

### US-02c — Use a tracker other than GitHub
As a maintainer, I can map bug, feature and suggestion reports to different issue templates or labels on the configured provider.

**Acceptance:** provider/template mappings are backend-owned; frontend never needs to know GitHub/GitLab form field names; a provider may intentionally map multiple report types to the same form when necessary.

### US-03 — Report an unexpected error
As a user encountering an unexpected application error, I can report it with relevant route, status and error details already supplied.

**Acceptance:** action on 5xx/unexpected error screens; 404 not treated as a bug by default; diagnostics visible before leaving.

### US-04 — Report an API failure
As a user encountering a failed operation, I can optionally report the operation, HTTP method, endpoint pattern, status and stable error code.

**Acceptance:** no raw request URL, query string, body, response body, arbitrary error message or item ID enters the report.

### US-05 — Control disclosure
As a user, I can see exactly what information will be shared and opt out of diagnostics.

**Acceptance:** preview is readable; default data is minimal; explicit checkbox to include diagnostics; request IDs excluded by default.

### US-06 — Change issue provider
As a maintainer, I can migrate from GitHub to another provider without changing the frontend route or frontend report UI.

**Acceptance:** backend selects destination; provider-specific form parameters and template filenames remain backend-only.

### US-07 — Failure fallback
As a user, if the destination cannot be resolved, I receive a useful error and can still access a safe upstream project/issues link when available.

**Acceptance:** no blank tab or silent failure; no arbitrary client-provided redirect URL.

## 4. User experience

### Entry points

1. **Settings → Help & Feedback**: card and sidebar entry linking to `/support/report` (or `/support/report?type=feature` or `/support/report?type=suggestion`). The sidebar already reaches the page, so it uses `<BackButton peer ...>`.
2. **Unexpected/5xx error screen**: `Report this problem` action; contextual snapshot passed in ephemeral client state, not in the frontend URL.
3. **Future:** contextual action on failed API operations via Sonner toast or inline error UI.

### Report page

- Choose `Bug report`, `Feature request` or `Suggestion / improvement`. Provide brief explanations of when to use each.
- Display target provider label once resolved.
- Display a concise diagnostics preview and a **Include diagnostics** toggle (default on for bug reports, off for features and suggestions).
- Offer **Copy diagnostics**.
- Fetch destination from backend; display a **normal external anchor** (`target="_blank"`, `rel="noopener noreferrer"`) once ready. This avoids popup blockers caused by `window.open()` after an awaited fetch.
- Provide loading, unavailable and retry states.

Do not show raw tracker URLs containing diagnostic query parameters in the page copy; the destination link is sufficient.


## 4a. Feature requests and suggestions: distinct reporting experience

The three report types share the same route, API resolver, external-link flow and provider abstraction, but **should not share a bug-oriented form**. They differ in user intent and appropriate context:

| Type | When to use | Tracker form fields | Automatic context |
|---|---|---|---|
| `bug` | Existing behaviour is broken | What happened; reproduction steps; expected behaviour; diagnostics | Safe version/route/error diagnostics, opt-out |
| `feature` | Add a new capability | Problem or use case; desired outcome; example workflow; alternatives (optional) | None by default; optional version and route pattern |
| `suggestion` | Improve an existing experience or share an idea | Area to improve; suggestion; why it helps; example (optional) | None by default; optional route pattern |

**Avoid forcing users to invent technical details.** A feature request can be an outcome rather than a proposed implementation. A suggestion can be informal and may concern usability, onboarding, wording, documentation, performance or workflow.

### Suggested frontend presentation

```text
Help & Feedback

What would you like to do?

[Report a bug]       Something isn't working as expected.
[Request a feature]  There's something new I'd like Menagerist to do.
[Share a suggestion] An existing experience could be better.

When selected:
  → Optional safe context preview (minimal for ideas)
  → Continue to GitHub / configured tracker ↗
```

Entry points can preselect a type (`/support/report?type=feature`, `?type=suggestion`), but type remains editable. The URL carries **only the report type**; any context stays ephemeral in the frontend.

### GitHub Issue Forms (illustrative contracts)

Provide three forms under `.github/ISSUE_TEMPLATE/` (exact filenames are implementation decisions):

- `bug_report.yml`: `description`, `reproduction`, `expected`, `diagnostics`.
- `feature_request.yml`: `problem`, `outcome`, `example`, `alternatives`, optional `context`.
- `suggestion.yml`: `area`, `suggestion`, `benefit`, optional `context`.

Field IDs are provider adapter configuration, **not frontend API fields**. The backend may prefill a short optional `context` field with approved route/version data; the main descriptive fields are normally left blank for the user to complete in the tracker. Don't put arbitrary user-written proposals in a GET query or attempt to build a full in-app issue composer in the MVP.

If the project prefers fewer templates, `feature` and `suggestion` may map to one `idea.yml` form with an issue-type selector; preserve separate types in the Menagerist API so the distinction remains useful later.

### Data and consent policy for ideas

- Default to **no diagnostics** for features and suggestions.
- Optional context: app version and matched route pattern, with a separate preview and explicit user choice.
- Never infer the suggestion's topic from item names, collection titles, user content or a full browser URL.
- No automatic error status, request ID or API endpoint for feature/suggestion reports.
- Keep the external tracker responsible for the user's written explanation and final submission.

### Acceptance tests specific to ideas

- Both report types are selectable from the general support page and via deep links.
- Each resolves to the intended provider form and preserves its report type even if templates are consolidated.
- Diagnostics are absent by default for both types; opting into safe context adds only allowlisted fields.
- Switching from a bug report to a suggestion clears error-specific diagnostics from the outbound request.
- An unsupported/missing template mapping fails gracefully without sending users to the wrong form.

## 5. Interaction flow

```text
Settings or contextual error
          |
          v
Frontend /support/report
  - route pattern + safe context
  - diagnostic preview + consent
          |
          v
GET /api/v1/system/issues/new?type=bug&...
          |
          v
Backend GetIssueReportUrl (query)
  - validate fields and limits
  - read trusted repository/build metadata
  - choose provider and template
  - format approved diagnostics
  - build destination URL
          |
          v
200 { provider, label, url }
          |
          v
User clicks external link -> new tab -> GitHub Issue Form
```

The backend does **not** contact GitHub and does **not** return a redirect. Its response is a URL for the frontend to render. No database writes.

## 6. API contract (proposed)

`GET /api/v1/system/issues/new`, in the `system` router beside `/version` and the health routes. The `/api/v1` prefix is confirmed. The frontend consumes the generated client, so run `poe generate-frontend-client` after adding it.

**Query parameters (all optional except type, with safe defaults):**

| Parameter | Type | Notes |
|---|---|---|
| `type` | enum `bug`, `feature`, `suggestion` | Explicit selection preferred; default `bug` only for contextual errors |
| `route` | bounded string | SvelteKit matched route ID, e.g. `/items/[id]/edit`; never full URL |
| `method` | HTTP method enum | e.g. `PATCH` |
| `endpoint` | bounded string | Declared API path template, e.g. `/api/v1/nodes/{node_id}` |
| `status` | integer 100–599 | HTTP status if available |
| `code` | bounded stable identifier | e.g. `VALIDATION_ERROR` |
| `include_diagnostics` | boolean | User-controlled, default `true` for bug |

Do **not** accept arbitrary JSON, raw browser URL, request body, exception string, repository URL, issue template or destination URL. Validate max length and characters. Unknown parameters should not be propagated into the tracker URL. A route or endpoint string must be treated as untrusted even when it claims to be a pattern; apply strict validation/allowlisting rather than relying on regex redaction alone.

**Response:**

```json
{
  "provider": "github",
  "label": "GitHub",
  "url": "https://github.com/OWNER/REPO/issues/new?template=bug_report.yml"
}
```

The URL is illustrative; the actual repository and template come from trusted backend configuration/build metadata. Return a typed Pydantic response with an HTTP URL. Avoid exposing a separate frontend contract for GitHub field IDs.

**Errors:** 422 for invalid input; a controlled 503/501-style error if reporting is unavailable or provider unsupported. Never reflect attacker-controlled input into an error message. Set `Cache-Control: no-store` for URLs containing diagnostic context; ensure proxy access logs do not retain sensitive query values (or keep diagnostics out of GET entirely if this cannot be guaranteed).

### GET trade-off

GET is simple and generated-client-friendly, but diagnostic parameters appear in local request URLs and access logs. The fields are deliberately non-private, yet this still merits a deployment review. If future diagnostics grow or contain anything potentially identifying, change to `POST /api/v1/support/issues/resolve` with a validated JSON body; it remains a side-effect-free query despite using POST for payload size/privacy reasons.

## 7. Diagnostics policy

### Default safe fields

| Source | Field | Rule |
|---|---|---|
| Backend build metadata | App version / commit / channel | Trusted server-owned values, only if available |
| SvelteKit | Route pattern | Use `page.route.id`, not `page.url` |
| Client | Browser family and major version | Optional; `bowser` already installed |
| Client | OS family | Optional; avoid device fingerprinting |
| Client | Timestamp | UTC ISO timestamp, optional |
| Error context | HTTP method / status | Only from known operation |
| Error context | API endpoint template | Declared route, never interpolated URL |
| Error context | Stable error code | Strict identifier, never arbitrary exception text |

**Never collect by default:** instance hostname/origin, complete page URL, query strings, hashes, item/collection/user IDs, authentication headers, cookies, tokens, request/response bodies, user-entered text, stack traces, logs, IP address or detailed browser/device fingerprint.

**Request ID:** optional future opt-in; useful for operator-side correlation but can link a public report to private logs. Keep out of the MVP.

Diagnostics are an **ephemeral snapshot**. Do not persist in local storage, analytics or a global history store. Display the exact data that will be sent, and allow omission. Do not include arbitrary user-generated content in the issue title.

## 8. Backend architecture

Prefer a small query use case and a provider-specific URL builder. Fit the actual package layout after inspecting current backend modules.

**Logical responsibilities:**

- **API adapter:** bind/validate query, return typed response; the use case declares `access = Public`.
- **Application query (`GetIssueReportUrl`):** obtain trusted repository/build metadata, select provider, apply policy, produce destination.
- **GitHub URL builder:** map `bug`/`feature`/`suggestion` to issue-form template and field IDs; encode with standard URL utilities.
- **Future GitLab builder:** same internal contract; no frontend change.

Avoid creating a full domain aggregate, repository, persistence model or plugin registration mechanism for this feature. Introduce an `IssueDestinationBuilder` protocol only when a second provider is actually implemented or if existing project conventions require it.

**Provider selection:** derive from `AppInfo.build.repository_url` (already used for the licence URL) for GitHub initially, and refuse anything that is not an HTTPS `github.com` URL. If supporting self-hosted GitLab later, add explicit provider configuration instead of inferring from arbitrary hostnames. An instance admin must not be able to turn this into an arbitrary redirect/open-link endpoint without an explicit trust policy.

**Build metadata:** reuse `AppInfo` and the existing version dependency wiring. Do not add a network call to the provider (the update check already talks to GitHub from the scheduler, not per request). Decide explicitly whether a fork should report to its own repository or the canonical upstream; default to canonical upstream for official Menagerist builds.

## 9. Frontend architecture

**Suggested additions (names provisional):**

```text
frontend/src/lib/support/
  diagnostics.ts        # allowlisted, ephemeral context builder
  types.ts              # UI types
  report-context.svelte.ts  # optional short-lived context handoff

frontend/src/lib/components/support/
  diagnostic-summary.svelte

frontend/src/routes/support/report/
  +page.svelte
```

**Existing touchpoints:**

- `settings/+page.svelte`: Help & Feedback card using existing card style.
- `+error.svelte`: report action on unexpected/5xx errors.
- `$lib/api/client`: use generated typed endpoint after schema regeneration.
- API error boundary/wrapper: inspect actual implementation before adding contextual capture. Do not modify `$lib/api/generated`.
- Existing `status/+page.svelte` uses version endpoints; reuse those models/queries where appropriate.

A normal external `<a>` is preferred to programmatic `window.open()` after fetch. The report page can resolve the URL when type/context/consent changes, then let the user click. Avoid re-fetching on every keystroke; debounce if needed. Do not put diagnostic details into the frontend route's query string.

## 10. Security and privacy

- URL generation must use trusted repository metadata; never accept `return_to`, `redirect`, `url` or `host` from the caller.
- Only allow HTTPS tracker destinations and known provider hosts/configuration.
- Restrict diagnostics to an explicit schema with lengths, enums and patterns.
- Never include the instance URL in GitHub/GitLab query parameters, issue body or referrer. External links use `rel="noopener noreferrer"`; the SPA shell sends `Referrer-Policy: strict-origin-when-cross-origin`, so `rel="noopener noreferrer"` on the link is what keeps the instance origin out of the tracker's referrer.
- Backend-provided URL is still untrusted at the browser boundary: validate it as an HTTPS URL to an allowed provider before rendering an external link, or ensure the backend enforces that contract and test it.
- Query URLs may appear in reverse proxy logs, and the API logs request paths; check whether query strings are recorded before sending diagnostics by GET. Keep data small, bounded and non-sensitive; evaluate POST if privacy requirements tighten.
- No need for application login just to obtain a generic upstream issue URL, but follow existing API/auth conventions and consider abuse/rate-limiting if publicly accessible.
- Display a warning that GitHub/GitLab issues are public and the user should review their own issue description before submitting.

## 11. Tests and acceptance gates

**Backend unit tests:** all three report types → correct template; encoding of field IDs; absent metadata; unknown provider; invalid/oversized diagnostic fields; no arbitrary destination; URL length cap; missing optional diagnostics.

**Backend API tests:** typed 200 response; 422 validation; no state change; no external HTTP request; no-store policy; expected auth behaviour.

**Frontend unit tests:** route ID extraction; allowlist; no raw URL/body/token; opt-out removes diagnostics; graceful failed resolution; no stale context after navigation.

**Frontend E2E:** Settings entry; bug/feature/suggestion destination; error-page action; preview/consent; external link opens new tab; unavailable backend fallback.

**Quality:** existing Ruff/mypy/pytest and frontend lint/check/Vitest/Playwright workflows; regenerate OpenAPI client using the existing `poe` workflow.

## 12. Incremental delivery

### Stage A — Useful MVP

- Backend `GetIssueReportUrl` and GitHub builder.
- Typed API endpoint and generated client.
- `/support/report` page and Settings entry.
- Build version, route pattern and browser summary with consent/preview.
- GitHub bug/feature/suggestion templates (new files under `.github/ISSUE_TEMPLATE/`; the directory does not exist today).
- Tests and no-store/privacy controls.

**Usable result:** users can report bugs, request features and share suggestions from Menagerist.

### Stage B — Contextual errors

- Error-page action for unexpected/5xx errors.
- Short-lived diagnostic context handoff.
- Capture safe method/endpoint/status/code at the existing API error boundary if supported.
- Targeted tests for redaction and missing context.

**Usable result:** one-click contextual reporting from failures.

### Stage C — Provider flexibility (when needed)

- Introduce provider interface if justified by a second implementation.
- GitLab builder and explicit provider configuration.
- Optional request-ID opt-in and richer diagnostics only after review.

**Usable result:** migration to another tracker without changing frontend reporting flows.

## 13. Decisions and open questions

| Topic | Recommendation / decision needed |
|---|---|
| Frontend URL | `/support/report` rather than nested Settings route. |
| Backend URL | `/api/v1/system/issues/new`, in the `system` module. |
| HTTP method | GET for small safe context; POST if URL logging/privacy becomes a concern. |
| Default diagnostics | On for bugs with preview and opt-out; off for feature requests and suggestions. Optional route context can be separately enabled for feature/suggestion reports. |
| Provider | GitHub initially; backend owns mapping. |
| Template filenames | Create `.github/ISSUE_TEMPLATE/` (none exists); choose the YAML field IDs when writing the three forms. |
| Repository | Canonical upstream vs fork: decide explicitly; default official upstream. |
| API error integration | Inspect `$lib/api/client` and error handling before designing interception. |
| Authentication | `Public` stance on `public_v1_router`, like `/version`. There is no general rate limit (only the sign-in throttle), so keep the query cheap and side-effect free. |
| Build metadata | Reuse `AppInfo` (`platform/app_info.py`); the public `/version` endpoint exposes only name and version. |

## 14. Architecture decision summary

**Chosen:** frontend reporting page + preview, backend query returning an external issue URL, browser-opened anchor, safe structured diagnostics, GitHub adapter first.

**Rejected for MVP:** direct frontend GitHub URL construction (provider coupling), backend 302 redirect (less flexible preview/loading flow), backend GitHub API integration (credentials and complexity), telemetry/history storage (privacy and scope), dynamic provider plugins (premature abstraction).

**Review gate:** confirm current backend routing/build metadata and frontend API error handling, then refine this HLD into an implementation plan without altering the public design unless existing conventions warrant it.
