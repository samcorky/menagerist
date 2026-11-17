# User Avatars Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every account has a picture: uploaded (with a square crop), a random cat from cataas fetched by the server, a cat drawn in the browser when that service is unavailable, or the initials-on-colour default. It shows wherever a person appears.

**Architecture:** This lives in the identity module. `User` holds an optional `Avatar` value object (version, source, time). Three new ports, each with an in-memory sibling: `AvatarImageProcessor` (Pillow), `AvatarStorage` (files under `<media storage>/avatars/`) and `CatPictureSource` (cataas through `OutboundHttp`). Five use cases sit behind four `/me` and `/users` routes. The frontend adds a `UserAvatar` component, a cropper and a drawn-cat generator.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy and Alembic, Pillow; SvelteKit with Svelte 5 runes, Tailwind v4, shadcn-svelte, Vitest and Playwright.

**Spec:** `docs/superpowers/specs/2026-11-16-user-avatars-design.md`

## Global Constraints

- Dependency direction runs `entrypoints → adapters → application → domain`. Identity adapters must not import media adapters. Copy the Pillow guards instead of importing them.
- Every use case sets `access` and implements `_handle`. Commands use `IdentityUnitOfWork` and `commit()`.
- Every new port has an in-memory sibling file next to its adapter.
- Domain and application coverage stays at 100%. `poe typecheck-backend` (strict mypy) and `poe coverage` must pass before completion.
- Frontend: Svelte 5 runes, `resolve()` for internal hrefs, no hand edits under `src/lib/api/generated/`, and `poe typecheck-frontend` must pass.
- Copy: British English. UI text says **picture**, never "avatar". The buttons are **Upload picture**, **Random cat** and **Use initials**.
- Limits: at most **5 MB** (`5 * 1024 * 1024`) per upload; JPEG, PNG, WebP and GIF (first frame) only; output sizes **64, 128, 256** px as WebP with no metadata.
- `avatars.cat_service_enabled` defaults to `True`. `avatars.cat_service_url` defaults to `"https://cataas.com"`.
- **No commits.** Never run `git add` or `git commit`; the user commits. Each task ends with a verification step instead.
- Use `--mode agent` for poe test, lint and typecheck tasks.

## Review Focus

1. **An upload that is a real image but huge, or a decompression bomb** must fail with a 400 `InvalidAvatarError`, never a 500 or an out-of-memory error. Pinned in Task 2 (`test_rejects_too_many_pixels`).
2. **A phone photo with EXIF rotation and a crop** must crop the region the person saw, not the sideways one. Pinned in Task 2 (`test_crop_uses_orientation_corrected_coordinates`).
3. **Rapid Random cat presses** must not leave several versions' files on disk or show an earlier cat at the end. Pinned in Task 5 (`test_replacing_deletes_previous_version_files`) and Task 10 (presses are ignored while one is in flight).
4. **A cataas redirect to another host, or a non-image reply such as an HTML error page**, must count as unavailable and fall back to a drawn cat, never be stored. Pinned in Task 4 (`test_non_image_reply_is_unavailable`, `test_redirect_off_host_is_unavailable`).
5. **A cached picture URL after the picture changes or is removed** must not serve old bytes under the new state. Pinned in Task 6 (`test_stale_version_is_404`, `test_cleared_avatar_is_404`).

---

### Task 1: Domain avatar and persistence

**Files:**
- Create: `backend/src/app/modules/identity/domain/avatar.py`
- Modify: `backend/src/app/modules/identity/domain/user.py`, `backend/src/app/modules/identity/domain/errors.py`
- Modify: `backend/src/app/modules/identity/adapters/persistence/models.py` (`UserModel`), `.../persistence/user_repository.py` (`_to_domain`, `_to_model`)
- Create: `backend/src/app/alembic/versions/<rev>_user_avatars.py` (`down_revision = "d8f3a1c6e2b9"`; check `alembic heads` first)
- Test: `backend/tests/modules/identity/domain/test_avatar.py`, extend `backend/tests/modules/identity/domain/test_user.py`, and the integration test for the user repository

**Interfaces:**
- Produces:
  - `AVATAR_SIZES: tuple[int, ...] = (64, 128, 256)` and `MAX_AVATAR_BYTES = 5 * 1024 * 1024`
  - `class AvatarSource(StrEnum)` with `UPLOAD = "upload"`, `CAT = "cat"` and `DRAWN = "drawn"`
  - `@dataclass(frozen=True, kw_only=True) class Avatar` with `version: str`, `source: AvatarSource` and `updated_at: datetime`
  - `@dataclass(frozen=True, kw_only=True) class CropSquare` with `x: int`, `y: int` and `size: int`. `__post_init__` raises `InvalidAvatarError` unless `x >= 0`, `y >= 0` and `size >= 1`.
  - `User.avatar: Avatar | None = None`, `User.set_avatar(avatar: Avatar) -> None` and `User.clear_avatar() -> None`. Both `touch()`.
  - Errors: `InvalidAvatarError(ValidationError)` and `AvatarNotFoundError(NotFoundError)`
  - Columns `avatar_version: str | None`, `avatar_source: str | None` and `avatar_updated_at: datetime | None` (timezone-aware). All three are null, or all are set.

- [ ] **Step 1:** Write the failing tests: `test_crop_square_rejects_negative_offset`, `test_crop_square_rejects_zero_size`, `test_set_avatar_stores_and_touches` (where `updated_at` advances), `test_clear_avatar_removes_it`, and in the repository integration test, `test_avatar_round_trips` and `test_no_avatar_round_trips_as_none`.
- [ ] **Step 2:** Run `poe test-backend --mode agent -- tests/modules/identity/domain`. Expected: FAIL on import.
- [ ] **Step 3:** Implement the domain types, user methods, model columns and mapping, and a migration that adds the three nullable columns (the downgrade drops them).
- [ ] **Step 4:** Run the domain tests again and expect PASS. Then run `poe db-up` and `poe test-backend-integration --mode agent -- -k user_repository` and expect PASS.

### Task 2: Avatar image processor (Pillow)

**Files:**
- Create: `backend/src/app/platform/imaging.py`. It holds `open_image_safely(data: bytes, *, max_pixels: int, max_jpeg_pixels: int) -> Image.Image`, the decompression-bomb guard and pixel check lifted out of `media/adapters/imaging/pillow_processor.py`, and raises `ImageTooLargeError`/`UndecodableImageError` (defined in the same file as plain `Exception` subclasses that callers map). Change `PillowImageProcessor` to use it, with its behaviour and tests unchanged.
- Create: `backend/src/app/modules/identity/ports/avatar_image_processor.py`
- Create: `backend/src/app/modules/identity/adapters/imaging/__init__.py`, `pillow_avatar_processor.py` and `in_memory_avatar_processor.py`
- Test: `backend/tests/platform/test_imaging.py` and `backend/tests/modules/identity/adapters/imaging/test_pillow_avatar_processor.py`. The existing media processor tests must still pass.

**Interfaces:**
- Consumes: `AVATAR_SIZES`, `CropSquare` and `InvalidAvatarError` from Task 1
- Produces:
  - `@dataclass(frozen=True, kw_only=True) class ProcessedAvatar` with `version: str` (the first 16 hex characters of the SHA-256 of the 256 px bytes) and `images: Mapping[int, bytes]` (keyed by every size in `AVATAR_SIZES`)
  - `class AvatarImageProcessor(Protocol)` with `async def process(self, data: bytes, *, crop: CropSquare | None) -> ProcessedAvatar`. It raises `InvalidAvatarError` for anything undecodable, an unsupported format, too many pixels or a crop entirely outside the image.
  - `PillowAvatarProcessor` runs its synchronous work through `asyncio.to_thread`. Allowed `Image.format` values are `{"JPEG", "PNG", "WEBP", "GIF"}`. It decodes with `open_image_safely(data, max_pixels=40_000_000, max_jpeg_pixels=300_000_000)`, uses `draft` for JPEGs down to 1024 px, and maps both platform errors to `InvalidAvatarError`. The order is: `ImageOps.exif_transpose`, then crop (clamped to the image bounds, or the largest centred square when there's no crop), then resize to each size with `Image.Resampling.LANCZOS`, then save with `format="WEBP", quality=85, method=6`. Pass no `exif` or `icc_profile`, keep RGBA when the image has alpha and use RGB otherwise.
  - `InMemoryAvatarProcessor` returns deterministic fake bytes per size, with the version derived from `data`. `fail_next: bool` makes the next call raise `InvalidAvatarError`.

- [ ] **Step 1:** Write the failing tests, building fixtures in-test with Pillow:
  - `test_outputs_each_size_square_webp` checks that each output opens as WEBP with `size == (n, n)` for every n in (64, 128, 256)
  - `test_strips_metadata` checks that a JPEG saved with EXIF (including GPS) gives outputs whose `getexif()` is empty and `info` has no `"exif"`
  - `test_crop_uses_orientation_corrected_coordinates`: build a 200×100 JPEG with the left half red and right half blue, with EXIF orientation 6 (so it shows as 100×200, red on top). `crop=CropSquare(x=0, y=0, size=100)` must give a mostly red output.
  - `test_no_crop_takes_centre_square`
  - `test_crop_clamped_to_bounds`, where `CropSquare(x=150, y=0, size=100)` on a 200×100 image still gives a 100 px square from the right edge
  - `test_crop_outside_image_is_invalid`, where `x=500` raises `InvalidAvatarError`
  - `test_gif_uses_first_frame`, `test_png_alpha_kept`, `test_rejects_non_image` (b"hello"), `test_rejects_svg` (b"<svg ...>") and `test_rejects_too_many_pixels`
  - `test_version_changes_with_content` and `test_version_stable_for_same_input`
- [ ] **Step 2:** Run `poe test-backend --mode agent -- tests/modules/identity/adapters/imaging`. Expected: FAIL.
- [ ] **Step 3:** Implement the port, the Pillow adapter and the in-memory adapter.
- [ ] **Step 4:** Run the same tests again. Expected: PASS.

### Task 3: Avatar storage (filesystem)

**Files:**
- Create: `backend/src/app/modules/identity/ports/avatar_storage.py`
- Create: `backend/src/app/modules/identity/adapters/storage/__init__.py`, `local_avatar_storage.py` and `in_memory_avatar_storage.py`
- Modify: `backend/src/app/modules/media/adapters/storage/local_filesystem.py`. `list_files` must skip the `avatars` directory, so the stray-files job never deletes avatars. Check how it walks the tree first; if it already ignores names that aren't asset ids, add a test only.
- Modify: `backend/src/app/platform/storage_probe.py`. `storage_directories()` adds `"avatars": media.storage_path / "avatars"`, so the Status page's `StorageCheck` and the start-up warning report `storage:avatarsWritable` and `storage:avatarsFreeSpace`.
- Modify: `backend/src/app/entrypoints/api/startup.py`. Add `ensure_avatar_directory()`, which runs `mkdir(parents=True, exist_ok=True)` on that path before `warn_if_storage_not_writable` (it logs at debug and carries on if the mkdir fails), so a fresh install doesn't report it missing. Call it from the lifespan where the storage warning is called.
- Test: `backend/tests/modules/identity/adapters/storage/test_local_avatar_storage.py`, plus one test in the media storage tests, `test_storage_directories_include_avatars` in the platform tests, and `test_ensure_avatar_directory_creates_it`.

**Interfaces:**
- Consumes: `ProcessedAvatar` (Task 2)
- Produces: `class AvatarStorage(Protocol)` with:
  - `async def save(self, user_id: uuid.UUID, avatar: ProcessedAvatar) -> None`, which writes `<root>/<user_id>/<version>-<size>.webp` atomically (temp file plus `os.replace`)
  - `async def read(self, user_id: uuid.UUID, version: str, size: int) -> bytes | None`
  - `async def remove(self, user_id: uuid.UUID, *, keep: str | None = None) -> None`, which deletes every file for the user except those of version `keep`, and the directory once it's empty
  - `LocalAvatarStorage(root: Path)`, where the caller passes `get_media_settings().storage_path / "avatars"`. Validate `version` with `[0-9a-f]{16}`, so a path can never be built from other input.

- [ ] **Step 1:** Write the failing tests: `test_save_then_read_each_size`, `test_read_unknown_version_is_none`, `test_remove_keeps_named_version`, `test_remove_all_deletes_directory`, `test_rejects_bad_version_string` (`"../x"` raises `ValueError`), and on the media side, `test_list_files_ignores_avatars_directory`.
- [ ] **Step 2:** Run `poe test-backend --mode agent -- tests/modules/identity/adapters/storage tests/modules/media/adapters/storage`. Expected: FAIL.
- [ ] **Step 3:** Implement the storage, in-memory sibling and media skip.
- [ ] **Step 4:** Run the tests again. Expected: PASS.

### Task 4: Cat picture source, settings and the 503 base error

**Files:**
- Modify: `backend/src/app/shared_kernel/errors.py` to add `class UnavailableError(DomainError)`. Modify `backend/src/app/entrypoints/api/shared/http/problem_response.py` to map `UnavailableError: 503` in `_STATUS_BY_DOMAIN_ERROR`.
- Modify: `backend/src/app/modules/identity/domain/errors.py` to add `CatServiceUnavailableError(UnavailableError)`
- Create: `backend/src/app/modules/identity/ports/cat_picture_source.py`
- Create: `backend/src/app/modules/identity/adapters/cats/__init__.py`, `cataas_picture_source.py`, `disabled_cat_picture_source.py` and `in_memory_cat_picture_source.py`
- Create: `backend/src/app/platform/config/avatars.py`. Register it in `platform/config/__init__.py` (`ALL_SETTINGS`, `__all__`).
- Regenerate: `poe generate-settings-docs` (writes `.env.example` and `docs/settings.md`)
- Test: `backend/tests/modules/identity/adapters/cats/test_cataas_picture_source.py`, a shared-kernel error-mapping test and the settings tests

**Interfaces:**
- Produces:
  - `class CatPictureSource(Protocol)` with `async def fetch(self) -> bytes`, which raises `CatServiceUnavailableError`
  - `CataasPictureSource(http: OutboundHttp, base_url: str)` calls `http.get(f"{base_url.rstrip('/')}/avatar/{seed()}", headers={"Accept": "image/*"}` (where `seed` defaults to `secrets.token_hex(8)`, fresh per call, max_bytes=MAX_AVATAR_BYTES, admin_configured=True)`. It accepts only `status == 200`, a `content-type` starting with `image/`, a non-empty body, and a `response.url` host equal to the base URL's host. Anything else, including `OutboundHttpError`, raises `CatServiceUnavailableError("The cat service is not available.")`.
  - `DisabledCatPictureSource` always raises the same error.
  - `AvatarSettings(MenageristBaseSettings, group="avatars")` has `cat_service_enabled: bool = True`, described like `release.check_enabled` ("Whether this instance ever contacts the cat service for Random cat. Off makes the button draw a cat in the browser instead; set by the deployment."). It also has `cat_service_url: str = "https://cataas.com"`, which must be an http(s) URL. Add `get_avatar_settings()` with `lru_cache`.

- [ ] **Step 1:** Write the failing tests, using `InMemoryOutboundHttp`:
  - `test_returns_image_body`
  - `test_non_image_reply_is_unavailable` (an `text/html` 200)
  - `test_error_status_is_unavailable` (500)
  - `test_redirect_off_host_is_unavailable` (where `response.url` is on another host)
  - `test_outbound_failure_is_unavailable`
  - `test_requests_square_with_size_cap`, which asserts the recorded `params` and `max_bytes`
  - `test_disabled_source_always_unavailable`
  - `test_unavailable_error_maps_to_503`
- [ ] **Step 2:** Run `poe test-backend --mode agent -- tests/modules/identity/adapters/cats tests/shared_kernel`. Expected: FAIL.
- [ ] **Step 3:** Implement, then run `poe generate-settings-docs`.
- [ ] **Step 4:** Run the tests and `poe test-backend-fast --mode agent`. Expected: PASS, including the settings-docs drift test.

### Task 5: Use cases and the picture permission

**Files:**
- Create in `backend/src/app/modules/identity/application/`: `set_own_avatar.py`, `set_own_avatar_from_cat_service.py`, `clear_own_avatar.py`, `clear_user_avatar.py` and `get_user_avatar.py`
- Modify: `application/permissions.py` to add `VIEW_PICTURES = "identity:picture:read"`
- Modify: `backend/src/app/entrypoints/api/shared/authorisation.py` to set `MEMBER_PERMISSIONS = CONTENT_PERMISSIONS | {IdentityPermission.VIEW_PICTURES}` and subtract `VIEW_PICTURES` from `TOKEN_GRANTABLE_PERMISSIONS` (pictures are for signed-in people). Update the pins in `tests/architecture/test_permission_catalogue.py`, `test_permission_mapping.py`, `test_token_grants.py` and `tests/architecture/test_access_stances.py` (the `OwnAccount` set).
- Test: `backend/tests/modules/identity/application/test_avatars.py`

**Interfaces:**
- Consumes: Tasks 1–4
- Produces:
  - `SetOwnAvatarCommand(data: bytes, source: AvatarSource = AvatarSource.UPLOAD, crop: CropSquare | None = None)` and `SetOwnAvatar(uow, processor: AvatarImageProcessor, storage: AvatarStorage)` with `access = OwnAccount()`, returning `User`. It raises `InvalidAvatarError` if `source is AvatarSource.CAT` (only the cat use case sets that) or if `len(data) > MAX_AVATAR_BYTES`.
  - `SetOwnAvatarFromCatServiceCommand()` and `SetOwnAvatarFromCatService(uow, cats: CatPictureSource, processor, storage)` with `access = OwnAccount()`, returning `User` with source `CAT`
  - `ClearOwnAvatarCommand()` and `ClearOwnAvatar(uow, storage)` with `access = OwnAccount()`, returning `User`
  - `ClearUserAvatarCommand(user_id: uuid.UUID)` and `ClearUserAvatar(uow, storage)` with `access = Requires(IdentityPermission.UPDATE_USER)`, returning `User`
  - `GetUserAvatarQuery(user_id: uuid.UUID, version: str, size: int)` and `GetUserAvatar(repos, storage)` with `access = Requires(IdentityPermission.VIEW_PICTURES)`, returning `bytes`. It raises `AvatarNotFoundError` when the user is missing, has no avatar or has a different version, when `size not in AVATAR_SIZES`, or when storage returns `None`.
- Write order for each setter: process, then `storage.save`, then `get_for_update`, `set_avatar(Avatar(version, source, now))`, `save` and `commit`, then `storage.remove(user_id, keep=version)`. The clear use cases do `clear_avatar`, `save` and `commit`, then `storage.remove(user_id)`. Log `"picture changed"` or `"picture cleared"` with `user_id` and `source`, never the bytes.

- [ ] **Step 1:** Write the failing tests with the in-memory UoW, processor, storage and cat source:
  - `test_upload_sets_avatar_and_stores_files`
  - `test_drawn_source_recorded`
  - `test_cat_source_refused_on_upload`
  - `test_too_large_refused`
  - `test_crop_passed_to_processor`
  - `test_replacing_deletes_previous_version_files`
  - `test_cat_service_sets_cat_source`
  - `test_cat_unavailable_leaves_avatar_unchanged`
  - `test_clear_own_removes_files`
  - `test_admin_clears_someone_else`
  - `test_member_cannot_clear_someone_else` (`ForbiddenError`)
  - `test_token_actor_cannot_set_own` (`ForbiddenError`)
  - `test_get_returns_bytes_for_current_version`
  - `test_get_wrong_version_not_found`
  - `test_get_unknown_size_not_found`
  - `test_get_no_avatar_not_found`
  - `test_anonymous_cannot_get` (`ForbiddenError`)
- [ ] **Step 2:** Run `poe test-backend --mode agent -- tests/modules/identity/application/test_avatars.py`. Expected: FAIL.
- [ ] **Step 3:** Implement the use cases, then add the permission and update the pins.
- [ ] **Step 4:** Run the tests and `poe test-backend-fast --mode agent`, which includes the architecture tests. Expected: PASS.

### Task 6: API routes and response fields

**Files:**
- Modify: `backend/src/app/modules/identity/adapters/api/auth_router.py` (`me_router`), `user_router.py`, `schemas.py` and `dependencies.py`
- Modify: `backend/src/app/modules/search/domain/search_hit.py` (`SearchHit.avatar_version: str | None = None`, also copied in `rated`), `backend/src/app/modules/search/adapters/api/schemas.py` (`SearchHitResponse.avatar_version`) and `backend/src/app/entrypoints/api/shared/bridges/search_sources.py` (`UserSource` sets `avatar_version`)
- Modify: `backend/src/app/entrypoints/api/shared/http/upload_limit_middleware.py`. Today it guards only `POST` to the media and backup paths, so a `PUT /api/v1/me/avatar` body would be spooled in full before auth. Key the guarded routes on `(method, path)` and add `("PUT", "/api/v1/me/avatar")` with limit `MAX_AVATAR_BYTES + _OVERHEAD_ALLOWANCE`.
- Reuse from `entrypoints/api/shared/http/`: `rate_limited(RateLimitBucket.UPLOADS)` and `RATE_LIMITED_RESPONSE` on `PUT /me/avatar` and `POST /me/avatar/cat`; `PAYLOAD_TOO_LARGE_RESPONSE` on `PUT`; `get_conditional_get`/`ConditionalRequest` and `conditional_get_responses()` for the 304 on `GET …/avatar/{size}`; `error_response(...)` for every documented problem.
- Regenerate: `poe dump-schema`, `poe lint-schema` and `poe generate-frontend-client`
- Test: middleware tests (`test_avatar_put_over_limit_is_413_before_auth`, `test_other_put_paths_untouched`), identity router tests (e.g. `backend/tests/modules/identity/adapters/api/test_avatar_routes.py`) and the search source test

**Interfaces:**
- Consumes: Task 5 use cases
- Produces:
  - `UserResponse.avatar_version: str | None` ("Changes whenever the picture does; null when the account shows its initials.") and `UserResponse.avatar_source: AvatarSource | None`
  - `PUT /me/avatar` (multipart) takes `file: UploadFile`, `source: Literal["upload", "drawn"] = "upload"` and `crop_x`, `crop_y`, `crop_size: int | None` (all three or none; otherwise a 400 problem), and returns `UserResponse`. The router reads at most `MAX_AVATAR_BYTES + 1` bytes and passes them on, so the size rule stays in the use case.
  - `POST /me/avatar/cat` returns `UserResponse`, or a 503 problem.
  - `DELETE /me/avatar` returns `UserResponse`.
  - `DELETE /users/{user_id}/avatar` returns `UserResponse`.
  - `GET /users/{user_id}/avatar/{size}?v={version}` returns `image/webp` with `Cache-Control: private, max-age=31536000, immutable`, `ETag: "<version>-<size>"` and `X-Content-Type-Options: nosniff`. `v` is required.
  - Wiring in `dependencies.py`: `PillowAvatarProcessor()`, `LocalAvatarStorage(get_media_settings().storage_path / "avatars")`, and `CataasPictureSource(get_outbound_http(), settings.cat_service_url)` when `cat_service_enabled`, otherwise `DisabledCatPictureSource()`. Use whichever function the system module already uses to get `OutboundHttp`.
  - Every route gets an OpenAPI summary, a description and documented problem responses, following `docs/API_STYLE.md`.

- [ ] **Step 1:** Write the failing router tests, overriding dependencies with the in-memory adapters:
  - `test_put_avatar_returns_version`
  - `test_put_with_partial_crop_is_400`
  - `test_put_too_large_is_400`
  - `test_post_cat_returns_cat_source`
  - `test_post_cat_unavailable_is_503_problem`
  - `test_delete_own_clears`
  - `test_admin_delete_other_clears`
  - `test_member_delete_other_is_403`
  - `test_get_avatar_bytes_and_cache_headers`
  - `test_get_with_matching_etag_is_304`
  - `test_cat_press_is_rate_limited`
  - `test_stale_version_is_404`
  - `test_cleared_avatar_is_404`
  - `test_get_requires_sign_in` (401 or 403, matching the existing anonymous behaviour)
  - `test_me_includes_avatar_version`
  - `test_user_search_hit_carries_avatar_version`
- [ ] **Step 2:** Run the router tests. Expected: FAIL.
- [ ] **Step 3:** Implement, then run `poe dump-schema`, `poe lint-schema` and `poe generate-frontend-client`.
- [ ] **Step 4:** Run the router tests, `poe lint-backend --mode agent`, `poe typecheck-backend --mode agent` and `poe coverage --mode agent`. Expected: all PASS, with coverage floors met.

### Task 7: `UserAvatar` component and placements

**Files:**
- Create: `frontend/src/lib/avatars/avatar.ts`, `frontend/src/lib/components/user-avatar.svelte` and `frontend/tests/avatar.test.ts`
- Modify: `frontend/src/lib/components/user-menu.svelte` (the trigger shows the 32 px avatar instead of `UserRound`; the label row shows the avatar beside the name), `frontend/src/routes/admin/users/+page.svelte` (beside `user.display_name` at line ~402, plus a **Remove picture** action in each row's actions, shown only when `avatar_version` is set, after a confirm dialog like **Disable**, calling `DELETE /users/{id}/avatar` and replacing the row with the returned user), the `usersGroup` snippet in `frontend/src/lib/components/search-palette.svelte`, and `frontend/src/routes/admin/devices/+page.svelte` wherever a row names a person
- Modify: `frontend/README.md`, adding a one-line entry for `UserAvatar` if it lists shared components

**Interfaces:**
- Produces:
  - `initialsFor(displayName: string): string` returns the first letter of each of the first two words, upper-cased and locale-aware, or the first two characters of a single word. An empty name gives `"?"`.
  - `avatarTone(userId: string): number` gives a stable index into `AVATAR_TONES`, using an FNV-1a hash of the id modulo the length.
  - `AVATAR_TONES`: eight tones defined as CSS custom properties (`--avatar-1` … `--avatar-8`, background and foreground) in `layout.css`, with light and dark values. Each pair must reach at least 4.5:1 contrast; check it with the palette tooling if there is any, otherwise compute it in a test.
  - `avatarUrl(userId: string, version: string, size: 64 | 128 | 256): string` returns `/api/v1/users/${userId}/avatar/${size}?v=${version}`, using the client's base the same way `client.ts` does.
  - `UserAvatar` props: `{ userId: string; displayName: string; avatarVersion?: string | null; size?: 'sm' | 'md' | 'lg' | 'xl'; decorative?: boolean }`. Sizes map to 24/32/40/96 px and load the 64/64/128/256 image respectively. It's circular. `alt` is `displayName`, or `""` with `decorative`. On an `onerror` it falls back to the initials. Initials are `aria-hidden` when decorative; otherwise the element has `role="img"` and `aria-label={displayName}`.

- [ ] **Step 1:** Write the failing Vitest tests:
  - `initialsFor('Alice Example') === 'AE'`
  - `initialsFor('  alice  ') === 'AL'`
  - `initialsFor('Émile zola') === 'ÉZ'`
  - `initialsFor('') === '?'`
  - `avatarTone` is stable for the same id and stays within range
  - `avatarUrl` gives the exact string
  - Contrast is ≥ 4.5 for every tone in both themes, if the tones are computed in TS
- [ ] **Step 2:** Run `poe test-frontend --mode agent -- avatar`. Expected: FAIL.
- [ ] **Step 3:** Implement the helpers and component, then place it. Use the svelte-autofixer MCP on the component.
- [ ] **Step 4:** Run the tests, `poe lint-frontend --mode agent` and `poe typecheck-frontend --mode agent`. Expected: PASS.

### Task 8: Drawn cat generator

**Files:**
- Create: `frontend/src/lib/avatars/drawn-cat.ts` and `frontend/tests/drawn-cat.test.ts`

**Interfaces:**
- Produces:
  - `drawnCatSvg(random: () => number = Math.random): string` returns a self-contained 256×256 SVG string with no external references, scripts, `foreignObject` or `href`. It picks from at least 3 head shapes, 3 ear styles, 6 coat colours, 4 markings (none, stripes, patch, socks/bib) and 4 eye colours, on a pale background that contrasts with the coat.
  - `drawnCatPng(random?: () => number): Promise<Blob>` renders the SVG through an `Image` onto a 256×256 canvas and returns `canvas.toBlob(..., 'image/png')`. If that fails, it rejects with an `Error`.

- [ ] **Step 1:** Write the failing tests:
  - A seeded random (mulberry32) gives the same SVG twice
  - Two different seeds give different SVGs
  - The output parses with `DOMParser` as `image/svg+xml`, with no `parsererror`
  - It contains no `<script`, `href` or `foreignObject`
  - `viewBox="0 0 256 256"`
- [ ] **Step 2:** Run `poe test-frontend --mode agent -- drawn-cat`. Expected: FAIL.
- [ ] **Step 3:** Implement it, with one part table per feature and every value chosen through `random`.
- [ ] **Step 4:** Run the tests. Expected: PASS.

### Task 9: Cropper

**Files:**
- Create: `frontend/src/lib/avatars/crop-geometry.ts`, `frontend/src/lib/components/avatar-cropper.svelte` and `frontend/tests/crop-geometry.test.ts`

**Interfaces:**
- Produces:
  - `type CropView = { zoom: number; centreX: number; centreY: number }` uses natural-pixel centres, with `zoom` running from 1 (the largest square that fits) to 8.
  - `initialView(width: number, height: number): CropView` gives zoom 1, centred.
  - `cropSquare(view: CropView, width: number, height: number): { x: number; y: number; size: number }` uses `size = round(min(width, height) / zoom)` and clamps the centre so the square stays inside the image. All values are integers.
  - `pan(view, dxNatural, dyNatural, width, height): CropView` and `zoomTo(view, zoom, width, height): CropView` are both clamped.
  - `AvatarCropper` props: `{ file: File; onsave: (crop: { x: number; y: number; size: number } | null) => void; oncancel: () => void }`. It loads the file with `createImageBitmap(file, { imageOrientation: 'from-image' })` and draws to a canvas. It handles pointer drag (with pointer capture), a zoom `ui/` slider (use the existing range input pattern, or an `<input type="range">` styled like the kit if there's no slider component), the mouse wheel, and arrow keys (1% of the short side, 10% with Shift) on a focusable frame labelled "Picture crop area". The circular mask is shown with CSS. If decoding fails, it calls `onsave(null)` straight away.

- [ ] **Step 1:** Write the failing tests:
  - `cropSquare(initialView(400, 200), 400, 200)` equals `{x: 100, y: 0, size: 200}`
  - At zoom 2 the size is 100
  - Panning past the edge clamps x to `width - size`
  - `zoomTo` above 8 clamps to 8, and below 1 to 1
  - Results are always integers
- [ ] **Step 2:** Run `poe test-frontend --mode agent -- crop-geometry`. Expected: FAIL.
- [ ] **Step 3:** Implement the geometry, then the component. Run the svelte-autofixer.
- [ ] **Step 4:** Run the tests and `poe typecheck-frontend --mode agent`. Expected: PASS.

### Task 10: Account page Picture section and e2e

**Files:**
- Modify: `frontend/src/routes/settings/account/+page.svelte`, adding a **Picture** section above **Display name**
- Possibly modify: `frontend/src/lib/auth.svelte.ts`, if it needs a setter so the menu updates after a change without a refetch
- Create: `frontend/tests/e2e/avatar.spec.ts`

**Interfaces:**
- Consumes: the generated client functions for the four routes (Task 6), `UserAvatar` (Task 7), `drawnCatPng` (Task 8) and `AvatarCropper` (Task 9)
- Behaviour:
  - The section shows a large `UserAvatar` (`xl`), **Upload picture** (a hidden file input with `accept="image/jpeg,image/png,image/webp,image/gif"`), **Random cat**, and **Use initials** (only when `avatar_version` is set).
  - Upload opens the cropper in `ui/responsive-dialog`. On save it calls `PUT` with the crop fields (or none when the crop is `null`).
  - **Random cat** calls `POST /me/avatar/cat`. On a 503 it calls `drawnCatPng()` and `PUT` with `source=drawn`, then shows a toast reading "The cat service isn't available, so here's a drawn cat." While a request is in flight the button is disabled, shows a `Spinner` and ignores presses.
  - Every success updates `auth.user` with the returned user, so the menu changes straight away. Errors show a toast with the problem's detail. A 400 from upload says "That file can't be used as a picture." when there's no detail.

- [ ] **Step 1:** Write the e2e spec:
  - Upload a fixture PNG and save the crop. The menu trigger then contains an `img` whose `src` matches `/avatar/64?v=`.
  - **Use initials** brings the initials back and the img goes away.
  - **Random cat**, with `page.route('**/me/avatar/cat', r => r.fulfill({status: 503, ...problem}))`, ends with an img and shows the drawn-cat toast.
- [ ] **Step 2:** Run the spec through the e2e poe task (see `pyproject.toml`; e.g. `poe test-e2e --mode agent -- avatar`). Expected: FAIL.
- [ ] **Step 3:** Implement the section.
- [ ] **Step 4:** Run the e2e spec, `poe test-frontend --mode agent`, `poe lint-frontend --mode agent` and `poe typecheck-frontend --mode agent`. Expected: PASS. Take light and dark screenshots of the account page and menu at desktop and phone width for the PR.

### Final verification

- [ ] `poe check-changed --mode agent`, `poe coverage --mode agent` and `poe typecheck-backend --mode agent` all PASS.
- [ ] Check the documentation links in `docs/settings.md` and the spec.
- [ ] Do a whole-branch review, then hand over to the user to commit and open the PR (which closes #403).
