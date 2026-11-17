# User avatars, with a random cat button (#403)

## Intent

Give every account a picture so the app can show who someone is wherever a person appears: the account menu, the account page, the administrator's users list, the sessions views and the user rows of the `/` search popup (#402, shipped in #532). Today an account is a username and a display name and nothing shows a face or a mark.

## Goals

- A person can upload, replace and remove their own picture from their account page. An administrator can remove anyone's.
- Without a picture, a default that is never blank: initials on a colour derived from the user id, readable in light and dark themes.
- A **random cat** button. Each press gives a new cat and saves it immediately, so the one the person stops on stays.
  - Cats come from [cataas](https://cataas.com/#usage), fetched **by the server** through `OutboundHttp`, checked and processed exactly like an upload. The browser never talks to cataas.
  - When the cat service is off or unreachable, the browser draws a cat itself (generated SVG, rendered to PNG) and uploads it through the normal upload route, so the button works offline and on closed networks.
- A **Use initials** action that removes the picture and returns to the colour-and-initials default.
- Every picture has a text alternative.

- **Cropping on upload.** After choosing a file, the person picks the square to keep: drag to move, slider or wheel to zoom, arrow keys to nudge. It opens on the largest centred square.

## Non-goals

- Gravatar and an account email address: tracked in #540.
- Re-cropping a picture that is already saved, or cropping a cat. Cats arrive square.
- Animated avatars. A GIF keeps its first frame.
- Pictures on anything other than accounts.

## Anti-goals

- The browser making any third-party request.
- Uploaded files served as they arrived (unstripped metadata, original format, original dimensions).
- A picture URL that serves stale bytes after a change, or one that forces a full reload on every page view.

## Constraints

- Hexagonal layering (`entrypoints → adapters → application → domain`), access stances on every use case, in-memory adapter for every port, 100% domain/application coverage.
- `identity` may not import `media` (enforced by `test_identity_module_is_independent_of_other_modules`). Shared HTTP plumbing in `entrypoints/api/shared/http/` is reused: upload rate limit, early 413 middleware (extended to `PUT /me/avatar`, which it didn't guard), conditional GET and problem docs. The Pillow decompression-bomb guard moves to `platform/imaging.py`, so media and identity share one copy.
- Media assets belong to item attachments and are permission-checked as content, so avatars do **not** reuse `MediaAsset`. They reuse the Pillow know-how (`ImageOps.exif_transpose`, pixel-count guard) and live under the media storage path. Instance backups carry them as `avatars/<user>/<version>-<size>.webp` members listed in the manifest's `pictures`, restored with the same undo as media (added after the final review found backups did not include them).
- Alpha: no compatibility shims needed.

## Approaches

| Approach | Trade-off | Outcome |
| --- | --- | --- |
| **cataas through the server, generated-cat fallback in the browser** | Live photos plus offline support; extra work for the SVG cat builder | **Chosen** |
| cataas through the server, button hidden when off | Smaller, but closed networks get no cats | Rejected |
| Bundled illustration set | Needs licensed artwork and runs out of variety | Rejected |
| Crop in the browser (canvas) and upload the result | No server change, but the image is encoded twice and phones hit canvas memory limits on large photos | Rejected |
| **Send the crop square with the original; the server crops after applying the EXIF orientation** | One place handles rotation and cropping, with a single encode | **Chosen** |
| Reuse `MediaAsset` for storage | Shares upload code, but drags in attachment lifecycle and content permissions that do not fit an account | Rejected |

## Design

### Domain (identity)

- `User` gains `avatar: Avatar | None`. `Avatar` is a frozen value object: `version` (short hex digest of the processed 256 px bytes, used in URLs), `source` (`upload` | `cat` | `drawn`) and `updated_at`.
- `User.set_avatar(avatar)` and `User.clear_avatar()` both `touch()`.
- Migration adds nullable `avatar_version`, `avatar_source`, `avatar_updated_at` to `users`.

### Processing and storage (identity ports, with in-memory siblings)

- `AvatarImageProcessor` port, with a Pillow adapter. It accepts JPEG, PNG, WebP and GIF (first frame) up to **5 MB** and a pixel-count limit. It applies the EXIF orientation, converts to RGB(A), then crops. With an optional `crop` square (`x`, `y`, `size` in pixels of the **orientation-corrected** image), it cuts that square, clamped to the image. Without one, it takes the largest centred square. A crop with `size < 1`, or one lying entirely outside the image, is an invalid-avatar error. Then it resizes to **64, 128 and 256 px** and encodes WebP **with no metadata**. If a file won't decode, the domain raises an invalid-avatar error (422). SVG is refused.
- `AvatarStorage` port, with a local filesystem adapter at `<media storage_path>/avatars/<user_id>/<version>-<size>.webp`. Writes happen before the row commits. Old files are removed once the new version is saved, and when the picture is cleared. Check that the stray-files job in `media` ignores the `avatars/` subdirectory.
- `CatPictureSource` port, with a cataas adapter. It calls `OutboundHttp.get(f"{base}/avatar/{secrets.token_hex(8)}", max_bytes=5 MB, admin_configured=True)`. The seed is fresh and random on every press, so each press gives a new cat and nothing identifying is sent and requires a 200 with an `image/*` content type. Failures map to a domain `CatServiceUnavailableError` (503 problem). The result goes through the same processor.

### Settings (`AvatarSettings`, group `avatars`)

- `cat_service_enabled: bool = True`. This is a deployment switch, like `release.check_enabled`: off means the server never contacts the service.
- `cat_service_url: str = "https://cataas.com"`. The base address is administrator-configured.
- Run `poe generate-settings-docs` afterwards.

### Use cases

| Use case | Stance | Effect |
| --- | --- | --- |
| `SetOwnAvatar` (upload bytes, source `upload` or `drawn`) | `OwnAccount` | process, store, set |
| `SetOwnAvatarFromCatService` | `OwnAccount` | fetch, process, store, set; 503 when off or failing |
| `ClearOwnAvatar` | `OwnAccount` | clear and delete files |
| `ClearUserAvatar` | `Requires(UPDATE_USER)` | administrator removes someone else's |
| `GetUserAvatar` (id, size) | any signed-in actor (the plan settles the exact stance) | stream bytes |

### API

- `PUT /me/avatar` (multipart: `file`, optional `source=drawn`, optional `crop_x`, `crop_y`, `crop_size`, all three or none), `POST /me/avatar/cat`, `DELETE /me/avatar`, and `DELETE /users/{id}/avatar`. Each write returns the updated user.
- `GET /users/{id}/avatar/{size}?v={version}` serves `image/webp` with `Cache-Control: private, max-age=31536000, immutable` and an ETag. The `v` changes with the picture, so the URL changes when the picture does. A request whose `v` doesn't match returns 404.
- `UserResponse`, the current-user payload, the users list and the search popup's user hits gain `avatar_version: str | None`. The frontend builds URLs from the id and version, so URL shape stays a client concern in one helper.
- Then `poe dump-schema`, `poe lint-schema` and `poe generate-frontend-client`.

### Frontend

- `ui/avatar` (or `lib/components/user-avatar.svelte`): takes `id`, `displayName`, `avatarVersion` and `size`. It shows the picture through a resolved URL, or initials (the first letters of up to two words of the display name) on a colour picked by hashing the id into a fixed palette of theme tokens that meet contrast in both themes. If the image fails to load, it falls back to initials. `alt` is the display name, or `""` when the name is printed beside it.
- It's used in the user menu (trigger and header), on the account page, in the admin users list, in the user rows of the search popup and in the admin sessions/devices lists where they name a person.
- The account page gets a **Picture** section with a large preview and three actions: **Upload picture**, **Random cat** and **Use initials** (shown only when a picture is set).
- **Upload picture** opens a responsive dialog containing the cropper (`lib/components/avatar-cropper.svelte`, hand-rolled, no new dependency). It loads the file with `createImageBitmap(file, { imageOrientation: 'from-image' })`, so the crop is chosen on the same orientation-corrected image the server crops. It shows a square frame with a circular preview mask, pointer drag to move, a zoom slider (and wheel), and arrow keys that move by 1% (10% with Shift). **Save** uploads the original file with the crop in natural pixels. If the browser can't decode the file, the cropper is skipped and the upload is sent without a crop, so the server's centre crop or its 422 decides.
- Random cat calls `POST /me/avatar/cat`. On a 503 it builds a generated cat in the browser (`lib/avatars/drawn-cat.ts`: random head shape, ears, coat colour, markings and eye colour as SVG, rendered to a 256 px PNG on a canvas) and uploads it with `source=drawn`. A short note says the cat was drawn because the cat service is unavailable. While a press is in flight, the button shows a spinner and further presses are ignored.
- Copy follows design §24 ("picture", not "avatar", in UI text).

## Left to the builder

- The exact access stance for `GetUserAvatar`, and whether any existing listing needs a new projection to carry `avatar_version`.
- Palette choice and contrast check for initials.
- Which admin sessions/devices views name a person and so get the avatar.
- Test split: domain/application with in-memory adapters, a Pillow adapter test with real images (EXIF-rotated JPEG, PNG with alpha, GIF, a non-image, a crop on a rotated JPEG, out-of-bounds crops), a pure crop-geometry helper on the frontend (zoom/drag clamping and conversion to natural pixels), a cataas adapter test with the in-memory `OutboundHttp`, router tests, Vitest for the initials/colour and drawn-cat helpers, and one e2e for upload → menu shows picture → Use initials.
