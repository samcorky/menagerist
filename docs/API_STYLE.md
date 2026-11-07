# API style guide

How the HTTP API under `/api/v1` is shaped. The committed [`openapi.json`](../openapi.json) is the contract; this guide says what that contract should look like and which parts of it a tool enforces.

The conventions follow the [IBM API Handbook](https://cloud.ibm.com/docs/api-handbook), checked by IBM's [openapi-validator](https://github.com/IBM/openapi-validator), and borrow selectively from [Google's API design guide](https://cloud.google.com/apis/design) (AIPs). Where Menagerist differs, the reason is below. Route naming, request bodies and error wiring are documented with the code in [backend/README.md](../backend/README.md); this guide links to them rather than repeating them.

## How it is enforced

| Check                       | Task                            | What it catches                                                                  |
| --------------------------- | ------------------------------- | -------------------------------------------------------------------------------- |
| Path style tests            | `poe test-backend`              | Plural nouns, one word per segment, the hyphen allowlist, link and example shape |
| Valid OpenAPI 3.1           | `poe validate-schema`           | A malformed document                                                             |
| Schema is current           | `poe check-schema`              | `openapi.json` out of step with the API                                          |
| Breaking changes            | `api-breaking-changes` workflow | A removed or narrowed operation, field or status                                 |
| **Style lint (this guide)** | `poe lint-schema`               | The IBM rules, with the divergences below                                        |

`poe lint-schema` runs in CI as "API schema style". Errors always fail. Warnings are a ratchet: [`scripts/api-lint/baseline.json`](../scripts/api-lint/baseline.json) records the count per rule, and a rule may not gain findings. After fixing some, run `poe lint-schema-baseline` and commit the lower counts. The ruleset is [`scripts/api-lint/.spectral.yaml`](../scripts/api-lint/.spectral.yaml); switching a rule off needs a reason in that file and, if it is a convention, a line here.

To see the individual findings rather than the counts, run the validator directly:

```sh
cd scripts/api-lint && npx ibm-openapi-validator -r .spectral.yaml ../../openapi.json
```

The linter is its own small package, kept apart from the frontend because its dependency tree is large (about 1,200 packages) and would otherwise land in the frontend lockfile and its `npm audit` output.

## Resources and paths

- Plural nouns under `/api/v1`, `{thing_id}` path parameters, singletons for one-per-instance resources, and the signed-in account under `/me`: see [Route naming](../backend/README.md#route-naming).
- **Ids are `uuid7`, so a verb segment can never be mistaken for an id.** `/nodes/search`, `/nodes/random` and `/backups/prune` sit beside `/nodes/{node_id}` without ambiguity, and actions are `POST` sub-resources (`/restore`, `/purge`, `/duplicate`). Google's `:verb` custom-method syntax exists to avoid that clash for slug-keyed resources; we do not need it. **A resource addressed by a slug would break this rule**, so give it an id route and look it up with a filter instead of adding a slug path.
- JSON property names, enum values and query parameters are `snake_case`. (Google uses camelCase; IBM and this API use snake_case.)
- A sub-resource of a soft-deletable resource follows the trash pattern: `GET /x/deleted`, `POST /x/{id}/restore`, `DELETE /x/{id}/purge`.

## Methods and status codes

- `GET` reads and never changes state. `POST` creates (201 with the new resource, linked to its `GET` through OpenAPI `links`) or runs an action. `PATCH` changes some fields of a resource and is declared as `application/merge-patch+json` (RFC 7396): an omitted field is unchanged and `null` clears an optional one. The server parses it as ordinary JSON, so `application/json` still works for existing scripts, but the contract lists only the merge-patch type. `PUT` replaces, and is used for idempotent sets such as `PUT /collections/{id}/items` and `PUT /examples/{pack_id}/installation`. `DELETE` removes (204).
- Domain validation is **400**, a missing or hidden resource **404**, a clash **409**, a failed `If-Match` **412**, an unchanged `If-None-Match` **304**, throttling **429** with `Retry-After`. A request FastAPI cannot parse is **422**; see [Collection errors](DECISIONS.md#collection-errors-400-for-domain-validation-422-for-malformed-requests). IBM prefers 400 for both; we keep 422 because the generated client and tests rely on it.
- 403 is for an authenticated user lacking a permission, documented with `x-required-permission`.

## Errors

Every 4xx and 5xx body is RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail` and `instance`, and every operation documents its errors with an example. See [Error handling wiring](../backend/README.md#error-handling-wiring) and the "Every new route response needs an accurate example" paragraph in the backend README. Do not return `application/json` errors (the IBM rule that asks for it is off).

## Lists and pagination

A list returns a **bare JSON array**, and paging lives in headers, in the style of GitHub's API:

- Keyset pagination: `?after=<cursor>&limit=<n>`, ordered by `id`, never an offset. The cursor is opaque to clients.
- `Link: <url>; rel="next"` (RFC 8288) is present while there is another page and absent on the last.
- `Total-Count` is the number of items matching the filters, with `Total-Count-Capped: true` when a search stopped counting at its cap and the number is a lower bound.

IBM's handbook prefers an envelope (`{"nodes": [...], "limit": ..., "next": ...}`). We keep arrays because the headers carry everything the envelope would and the generated client stays simple. `ibm-no-array-responses` and `ibm-collection-array-property` follow from this and are off or tolerated. Changing it later would be a breaking change to every list endpoint.

## Conditional requests

`GET` responses carry a weak `ETag` (see [Weak ETags](DECISIONS.md#weak-etags-to-survive-a-compressing-proxy-open-question-76)), `If-None-Match` returns 304, and `PATCH` honours `If-Match` and answers 412. The headers are not yet declared as parameters in `openapi.json`, which is what `ibm-precondition-headers` reports.

## Request bodies, names and models

Request bodies are named Pydantic models, with multipart uploads as the one exception: see [Request bodies](../backend/README.md#request-bodies-named-pydantic-models-not-form-fields). Operation ids are `verb_noun` (`list_nodes`, `get_node`, `count_nodes`, `restore_node`). A name that reads as a number (`count_*`) returns a number.

## Where we differ from the sources

| Source         | Their convention                   | Ours                                               | Why                                                         |
| -------------- | ---------------------------------- | -------------------------------------------------- | ----------------------------------------------------------- |
| IBM            | List envelope                      | Bare array, paging headers                         | Headers carry the same data; see above                      |
| IBM            | Errors as `application/json`       | RFC 9457 `application/problem+json`                | A standard media type for errors                            |
| IBM            | 400 for every invalid payload      | 400 for domain rules, 422 for unparseable requests | FastAPI behaviour; the client depends on it                 |
| IBM            | No hyphen in path segments         | `node-types`, `edge-types` only                    | Pinned by `HYPHENATED_SEGMENTS`                             |
| IBM            | Bounds and formats on every scalar | Only where they carry meaning                      | Generated noise; add `ge`/`le`/`max_length` for real limits |
| IBM            | `...Prototype` / `...Patch` request schema names | `XxxRequest`                  | Names the generated client's types; see the backend README  |
| Google AIP-136 | `:verb` custom methods             | `/verb` sub-resources                              | Ids are uuid7; no slug paths to clash with                  |
| Google AIP-193 | `google.rpc.Status` errors         | RFC 9457                                           | HTTP-native                                                 |
| Google AIP-158 | `page_token` / `page_size`         | `after` / `limit` + `Link` header                  | Keyset on a time-ordered id                                 |
| Google (JSON)  | lowerCamelCase                     | snake_case                                         | Matches the Python models and IBM                           |

## Open findings

The remaining warnings are the backlog the ratchet works down. The ones that are real API decisions rather than documentation gaps:

- **Enum casing** (`ibm-enum-casing-convention`): some enum values are not snake_case.
- **Property casing** (`ibm-property-casing-convention`): a few camelCase properties such as `componentType`.
- **Precondition headers** (`ibm-precondition-headers`): declare `If-Match` and `If-None-Match` on the operations that honour them.
- **Operation ids** (`ibm-operationid-naming-convention`): for example `list_user_exports` served from `/me/exports`.
- **Descriptions and examples** (`ibm-property-description`, `ibm-parameter-description`, `ibm-schema-description`, `ibm-success-response-example`): documentation, added as routes are touched.

Treat the numbers in the baseline as the source of truth; this list only names the themes.

## Adding or changing an endpoint

1. Follow the naming and status rules above and the [route checklist](../backend/README.md#route-naming).
2. Run `poe dump-schema`, then `poe lint-schema`. A new route must not add warnings: describe its parameters, properties and schemas, and give its responses examples.
3. If the lint rejects something that is right for this API, change `.spectral.yaml` with a comment saying why, and add a row to the table above.
