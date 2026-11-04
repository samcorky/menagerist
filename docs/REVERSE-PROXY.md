# Running behind a reverse proxy

Menagerist serves plain HTTP and leaves TLS to whatever sits in front of it. This page is the contract any reverse proxy has to meet, with a minimal Caddy and Traefik example. For everything else about running it, see [DEPLOYING.md](DEPLOYING.md).

## What the proxy must do

| Requirement | Why |
|---|---|
| Forward `Host`, `X-Forwarded-Proto` and `X-Forwarded-For` | Sign-in and first-run setup compare the browser's `Origin` with the address and scheme the app sees, and sign-in limits count the real client address. Caddy and Traefik send the forwarding headers by default; nginx needs `proxy_set_header` lines for them. |
| Be listed in `MENAGERIST_API_TRUSTED_PROXIES`, and nothing broader | The app believes forwarding headers only from these peers. List the proxy's own address or network, for example `172.21.0.0/16`, not a wide default range. `*` trusts every peer, so use it only when the proxy is the sole way in and overwrites the header. |
| Accept request bodies at least as large as the app's upload limits | A photo or document is refused by the proxy before the app sees it if the proxy's limit is lower. Menagerist's limit is `MENAGERIST_MEDIA_MAX_UPLOAD_SIZE` (100 MiB by default). Restoring a backup archive through the browser is capped by `MENAGERIST_BACKUP_MAX_UPLOAD_SIZE` (8 GiB by default); the `menagerist backup` commands do not pass through the proxy. nginx refuses anything over 1 MB until you set `client_max_body_size`. |
| Redirect `http` to `https` itself | The app never redirects, because it cannot tell it is behind TLS. Caddy does this on its own; Traefik needs a redirect on its plain `web` entrypoint. |
| Send `Strict-Transport-Security` | See [Send HSTS from the proxy](#send-hsts-from-the-proxy). |

## Settings

Set these in the `.env` file next to `compose.yaml`, then recreate the container.

| Setting | Value |
|---|---|
| `MENAGERIST_API_TRUSTED_PROXIES` | The proxy's address or network. Find the network with `docker network inspect <network>`. |
| `MENAGERIST_API_PUBLIC_ORIGIN` | The public address, for example `https://menagerist.example.com`. |
| `MENAGERIST_IDENTITY_COOKIE_SECURE` | `origin` when the proxy terminates TLS. |

Without the first, every visitor shares the proxy's address and 20 failed sign-ins from anyone lock sign-in for everyone for 15 minutes; without the others, the session cookie may be sent without `Secure`. `MENAGERIST_IDENTITY_COOKIE_SECURE` is `auto` by default (Secure when the app sees HTTPS), `origin` (follow the scheme of the public address, and refuse to start if none is set), or `always` / `never`. Signing in over plain `http://` sends the password and session cookie unencrypted, which is fine on `localhost` and a home network you trust, and not over the internet. Details are in [CONTRIBUTING.md](../CONTRIBUTING.md#first-run-and-accounts).

## Examples

Both examples assume the proxy can reach the `menagerist` container's port 8000 over a Docker network it shares with it, and that the public name is `menagerist.example.com`.

### Caddy

```caddyfile
menagerist.example.com {
	reverse_proxy menagerist:8000
	header Strict-Transport-Security "max-age=15552000"
}
```

Caddy gets its certificate, redirects `http` to `https`, forwards the headers and sets no body limit, so the file above covers every row of the table. Put the Caddy container on the `menagerist` network (or put both on a shared one), and list that network in `MENAGERIST_API_TRUSTED_PROXIES`.

### Traefik

This goes in `compose.override.yaml` (see [DEPLOYING.md](DEPLOYING.md#your-own-changes-composeoverrideyaml)). It assumes Traefik already runs with a `websecure` entrypoint, a `letsencrypt` certificate resolver and a shared Docker network called `proxy`; rename them to match yours.

```yaml
services:
  menagerist:
    networks:
      - menagerist
      - proxy
    labels:
      - traefik.enable=true
      - traefik.docker.network=proxy
      - traefik.http.routers.menagerist.rule=Host(`menagerist.example.com`)
      - traefik.http.routers.menagerist.entrypoints=websecure
      - traefik.http.routers.menagerist.tls.certresolver=letsencrypt
      - traefik.http.routers.menagerist.middlewares=menagerist-hsts
      - traefik.http.middlewares.menagerist-hsts.headers.stsSeconds=15552000
      - traefik.http.services.menagerist.loadbalancer.server.port=8000

networks:
  proxy:
    external: true
```

Traefik forwards the headers and sets no body limit unless you add a `buffering` middleware. Redirecting `http` to `https` is a setting on Traefik's own `web` entrypoint, not on this service. List the `proxy` network (`docker network inspect proxy`) in `MENAGERIST_API_TRUSTED_PROXIES`, because Traefik reaches the app over it. Publishing `8080` in `compose.yaml` still exposes the app directly; add `ports: !override []` to the service if the proxy should be the only way in.

## Rate-limit at the proxy

Menagerist counts failed sign-ins, password checks and API-token checks itself (see "Sign-in lockouts" in [CONTRIBUTING.md](../CONTRIBUTING.md)), but a proxy can also cap the raw request rate per address before a request reaches the app. This is coarse and per address; the app's own limits are what protect accounts.

nginx, limiting the sign-in route to 10 requests a minute per address with a short burst:

```nginx
# http {} context
limit_req_zone $binary_remote_addr zone=menagerist_signin:10m rate=10r/m;
limit_req_status 429;

# server {} context
location = /api/v1/auth/login {
    limit_req zone=menagerist_signin burst=5 nodelay;
    proxy_pass http://menagerist:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

The app sees the real client address only when the proxy is listed in `MENAGERIST_API_TRUSTED_PROXIES`. Without that, every request appears to come from the proxy, so the app's per-address counters (sign-in and API-token failures) are shared by everyone behind it.

## Sign-in and first-run setup refuse requests from other sites

The browser's own `Sec-Fetch-Site` header decides: `cross-site` is refused and `same-origin` is accepted, whatever the proxy does to the scheme or host. Without that header (very old browsers, or plain HTTP on a LAN address) or when it says `same-site`, the request's `Origin` must match the origin the app sees, so there the proxy must pass `Host` and `X-Forwarded-Proto` through and be listed in `MENAGERIST_API_TRUSTED_PROXIES`. `MENAGERIST_API_CORS_ORIGINS` is not the fix for a proxy problem.

## If the proxy setup looks wrong, Menagerist says so

The first time in an hour it sees forwarding headers from a peer it does not trust, or a browser whose origin differs from the one it saw, it logs a warning (`reverse proxy may be misconfigured`) with the setting to change. With `MENAGERIST_API_PUBLIC_ORIGIN` set it also notices requests that arrive at a different address (`publicOriginMismatch`) or over plain `http` when the public address is `https` (`insecureOrigin`); the container's own health check is ignored. Administrators also see a warning for `proxy:configuration` at `/api/v1/system/health/ready/detail` for the next hour. It is a warning only: `/api/health/ready` still answers pass. Find your proxy's network with `docker network inspect <network>` and list it, for example `MENAGERIST_API_TRUSTED_PROXIES=172.21.0.0/16`, in `.env`, then recreate the container.

## Send HSTS from the proxy

Menagerist trusts the browser's headers, and the browser only keeps using HTTPS if the proxy tells it to. Set `Strict-Transport-Security` at the TLS-terminating proxy so a browser never falls back to plain HTTP for your address (Caddy `header Strict-Transport-Security "max-age=15552000"`, nginx `add_header Strict-Transport-Security "max-age=15552000" always;`, Traefik's `stsSeconds` headers middleware, as in the examples above). The app does not send it itself because it cannot know it is reached over HTTPS.
