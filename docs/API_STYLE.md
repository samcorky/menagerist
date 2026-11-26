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

`poe lint-schema` runs in CI as "API schema style". Errors always fail, and every rule is now an error. Warnings are a ratchet for any rule added later at `warn`: [`scripts/api-lint/baseline.json`](../scripts/api-lint/baseline.json) records the count per rule, and a rule may not gain findings. After fixing some, run `poe lint-schema-baseline` and commit the lower counts. The ruleset is [`scripts/api-lint/.spectral.yaml`](../scripts/api-lint/.spectral.yaml); switching a rule off needs a reason in that file and, if it is a convention, a line here. An exception for a single schema or path goes under `overrides` in the same file, so the rule still guards everything else.

When a rule goes over its baseline the failure also lists the new findings by rule and schema path. The baseline holds only counts, so "new" means a finding that is not in the committed `openapi.json` on `origin/main` (or `main`); if neither ref exists, as in a shallow clone, it lists every warning of the rules that went over instead, up to 40 lines. To see every finding, run the validator directly:

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

- Keyset pagination: `?after=<cursor>&limit=<n>`, never an offset. The cursor is opaque to clients: pass back the one the `Link` header carries and read nothing into it.
- `Link: <url>; rel="next"` (RFC 8288) is present while there is another page and absent on the last. The next URL repeats the request's other parameters, so `sort`, `order` and `q` carry on to every page.
- `Total-Count` is the number of items matching the filters, with `Total-Count-Capped: true` when a search stopped counting at its cap and the number is a lower bound.

### Sort, order and search

A list route that pages declares all four of `after`, `limit`, `sort` and `order`, and adds `q` where it has text to search. `PageParams` and `SearchPageParams` in `entrypoints/api/shared/http/parameters.py` declare `after`, `limit` (`ge=1, le=100`, default 50), `sort` and `order`, and `q` for the searchable form. They are generic over the route's sort enum, so a route takes `page: Annotated[SearchPageParams[CollectionSort], Query()]` and writes only that enum. FastAPI flattens the fields into ordinary query parameters, so the schema and generated client are the same as if each were declared on the route, and `page.sort` is typed as the enum. A route with a different cap subclasses the model and overrides `limit`.

| Parameter | Meaning                                                                                                  |
| --------- | -------------------------------------------------------------------------------------------------------- |
| `sort`    | One key from the route's own allow-list, declared as an enum so the generated client types it. Leaving it out sorts by `id`. |
| `order`   | `asc` (the default) or `desc`. It applies to `sort`, or to `id` when `sort` is left out, so `order=desc` alone lists the newest first. |
| `q`       | Keep the rows whose searchable text contains this, ignoring case and accents, the same matching as the main search. At most 200 characters. |

- **Keys:** the name of the response field the list is ordered by, so a client sorts by what it sees. A route offers only the keys that carry meaning for it (typically `name`, `created_at`, `updated_at`, and the route's own, such as `slug` or `kind`), and documents them in the enum. Sorting by a custom field is only for item search, which has its own query-body `sort`.
- **Page size:** `limit` is 1 to 100 on every list. The paging helpers also never return more than 1,000 rows in a page, so a caller that builds a request itself cannot ask for everything. A client that needs every row follows `Link` to the end.
- **Default order:** `id` ascending, which is creation order because ids are uuid7. A route that lists something other than live rows in creation order says so on its own description: the recently deleted lists run newest deletion first.
- **Ties and gaps:** every sort adds `id` as the final key, in the same direction as `order`, so rows with equal values keep a fixed order and a page never repeats or skips one. A row with no value for the key (an empty optional field) sorts after the rest in both directions.
- **Text keys** compare ignoring case, using the database's collation.
- **The cursor** is base64url JSON holding a version, the sort keys and their directions, the last row's value for each key, and its id, so the next page resumes from that row. It is not signed, because it grants no access: the actor's scope applies to every page, and a forged cursor can only land on another page of rows the actor may already see. It is only valid with the `sort` and `order` that produced it. A bare id is still accepted as a cursor for the default order, so links and clients from before sorting keep working.
- **When values change between pages** the cursor stays valid, and a row that was edited may be seen twice or missed. That is the usual keyset trade-off, and the price of never counting rows from the start.
- **Errors:** an unknown `sort` or `order` is an unparseable request, so a 422 problem listing the accepted values, like any other enum parameter. A cursor that cannot be read, or that came from a different `sort` or `order`, is a 400 problem.
- **No offsets, even for tables:** a table pages with "next" and shows `Total-Count`; it does not jump to page 3 of 12. Counting from the start is slow on a large list and wrong once rows change, and the sort and search controls find a row faster than the page number would.

IBM's handbook prefers an envelope (`{"nodes": [...], "limit": ..., "next": ...}`). We keep arrays because the headers carry everything the envelope would and the generated client stays simple. `ibm-no-array-responses` and `ibm-collection-array-property` follow from this and are off. Changing it later would be a breaking change to every list endpoint.

## Conditional requests

`GET` responses carry a weak `ETag` (see [Weak ETags](DECISIONS.md#weak-etags-to-survive-a-compressing-proxy-open-question-76)), `If-None-Match` returns 304, and `PATCH` honours `If-Match` and answers 412 with a problem body and the current `ETag`. A route takes `ConditionalGetDep` or `ConditionalPatchDep`, which declare `If-None-Match` or `If-Match` as parameters so they appear in `openapi.json` and the generated client. The date forms, `If-Modified-Since` and `If-Unmodified-Since`, are honoured but not declared, so the contract steers clients to ETags as IBM recommends.

## Request bodies, names and models

Request bodies are named Pydantic models, with multipart uploads as the one exception: see [Request bodies](../backend/README.md#request-bodies-named-pydantic-models-not-form-fields). Operation ids are `verb_noun` (`list_nodes`, `get_node`, `count_nodes`, `restore_node`). A name that reads as a number (`count_*`) returns a number.

A list route returns a bare array (`response_model=list[PresetResponse]`), never an object wrapping one, and its operation id is `list_<plural>` (`list_presets`, `list_example_packs`). An install route is `install_<noun>` (`install_example_pack`). IBM's rules for list envelopes and path-derived operation ids are off, so match the existing routes rather than IBM's suggestions.

## Where we differ from the sources

| Source         | Their convention                   | Ours                                               | Why                                                         |
| -------------- | ---------------------------------- | -------------------------------------------------- | ----------------------------------------------------------- |
| IBM            | List envelope                      | Bare array, paging headers                         | Headers carry the same data; see above                      |
| IBM            | Errors as `application/json`       | RFC 9457 `application/problem+json`                | A standard media type for errors                            |
| IBM            | 400 for every invalid payload      | 400 for domain rules, 422 for unparseable requests | FastAPI behaviour; the client depends on it                 |
| IBM            | No hyphen in path segments         | `node-types`, `edge-types` only                    | Pinned by `HYPHENATED_SEGMENTS`                             |
| IBM            | Bounds and formats on every scalar | Only where they carry meaning                      | Generated noise; add `ge`/`le`/`max_length` for real limits |
| IBM            | `...Prototype` / `...Patch` request schema names | `XxxRequest`                  | Names the generated client's types; see the backend README  |
| IBM            | Shared path parameters on the path item | Declared on each operation                    | How FastAPI emits them                                      |
| IBM            | Dictionaries with one value type   | Free-form JSON for field values, preset definitions and search queries | Field types validate them, not the schema |
| IBM            | Operation ids derived from the path | `verb_noun` with the domain's verbs (`revoke_session`) | Names the generated client's functions               |
| IBM            | `errors` and `trace` on every error | RFC 9457; `errors` only on validation              | The standard's shape; a trace would leak internals          |
| IBM            | snake_case enum values             | Permissions are `module:resource:action`           | Scope-style, like OAuth scopes; each part is snake_case     |
| IBM            | No `const`, no `$ref` siblings     | Both allowed                                       | Valid OpenAPI 3.1 (JSON Schema 2020-12)                     |
| IBM            | A `servers` entry                  | None                                               | Self-hosted: each instance has its own origin               |
| IETF health draft | camelCase health properties     | Kept on the probes (`componentType`)               | Follows draft-inadarei-api-health-check                     |
| Google AIP-136 | `:verb` custom methods             | `/verb` sub-resources                              | Ids are uuid7; no slug paths to clash with                  |
| Google AIP-193 | `google.rpc.Status` errors         | RFC 9457                                           | HTTP-native                                                 |
| Google AIP-158 | `page_token` / `page_size`         | `after` / `limit` + `Link` header                  | Keyset on a time-ordered id                                 |
| Google (JSON)  | lowerCamelCase                     | snake_case                                         | Matches the Python models and IBM                           |

## Adding or changing an endpoint

1. Follow the naming and status rules above and the [route checklist](../backend/README.md#route-naming).
2. Run `poe dump-schema`, then `poe lint-schema`. A new route must not add findings: describe its parameters, properties and schemas with `description=`, and give each response model an example in `json_schema_extra`, which `openapi_examples.py` copies onto every success response that returns it. A parameter without a description is an error, and so is a DELETE with a body (use query parameters). For the ones that recur (`after`, `limit`, `node_id` and the other ids, a field's `key`) use the aliases in `entrypoints/api/shared/http/parameters.py`.
3. If the lint rejects something that is right for this API, change `.spectral.yaml` with a comment saying why, and add a row to the table above.
