# Fangyu Defense — WordPress Plugin

WordPress adapter for the **Fangyu V2 anti-bot gateway**.  
Requires a running Fangyu V2 gateway instance; this plugin is the adapter layer only.

---

## Requirements

| Item | Version |
|------|---------|
| PHP | ≥ 7.4 |
| WordPress | ≥ 5.9 |
| Fangyu gateway | V2 (this plugin is **not** compatible with V1) |

---

## Installation

```bash
# Copy into your WP plugins directory
cp -r adapters/wordpress /path/to/wp-content/plugins/fangyu-defense
```

Then: **Plugins → Activate → Settings → Fangyu Defense**.

---

## Configuration

| Field | Description |
|-------|-------------|
| Gateway URL | Base URL, no trailing slash — e.g. `https://defense.example.com` |
| Site ID | Numeric ID from the gateway admin |
| API Key | Sent as `X-App-Key`; authenticates the adapter to the gateway |
| Site Secret | Used **locally** for HMAC-SHA256 signing; never transmitted |
| Fail Mode | `open` (allow on gateway error) or `closed` (deny on gateway error) |

Click **Run Check** to send a signed test request and verify credentials.

---

## How signing works

Every request to `/v2/decide` carries three top-level fields alongside `context`:

```json
{
  "context": { "siteId": 1, "ingress": "adapter", ... },
  "requireDetails": false,
  "timestamp": 1700000000,
  "nonce": "0123456789abcdef0123456789abcdef",
  "sign": "<hmac-sha256>"
}
```

The HMAC is computed over a URL-encoded, lexicographically sorted key=value string —
identical to the Python and TypeScript implementations.
Cross-language parity is locked by `client-sdk/tests/fixtures/sign_vectors.json`.

Run the PHP parity test from the `Evercookie Defense System V2/` directory:

```bash
php tests/parity/sign_parity_test.php
```

---

## Disposition mechanics

| Mechanism | WordPress action |
|-----------|-----------------|
| `pass` | Normal page render continues |
| `serve_alt` | Gateway's `pageContent` field is echoed (SDK injected before `</body>`) |
| `redirect` | `wp_redirect()` with gateway-selected URL (302 default) |
| `challenge` | Security-check page rendered; SDK handles CAPTCHA / JS challenge |
| `deny` | `wp_die()` with HTTP 403 |
| `not_found` | Theme 404 template loaded with HTTP 404 |

Round-robin redirect pools (`target.urls`) are resolved **server-side by the gateway**;
the plugin always receives a single `targetUrl`.

---

## Security notes

- `X-Forwarded-For` is **deliberately ignored** to prevent IP spoofing.
  Only `CF-Connecting-IP` / `True-Client-IP` / `X-Real-IP` are read,
  and only when the socket peer is in a known CDN CIDR range.
- Logged-in `manage_options` users are never intercepted.
- All redirect targets are validated for `http`/`https` scheme before use.

---

## File layout

```
fangyu-defense.php              Plugin entry point + front-end hook
includes/
  class-fangyu-config.php       WP-options based config read/write
  class-fangyu-signer.php       HMAC-SHA256 signing (parity-locked)
  class-fangyu-visitor.php      IP, repeat token, URL, referer extraction
  class-fangyu-client.php       wp_remote_post → /v2/decide
  class-fangyu-executor.php     Mechanism → WP action mapping
  class-fangyu-admin.php        Settings page + connectivity check
assets/
  sd-sdk.min.js                 Bundled V2 client SDK (from client-sdk/dist/)
readme.txt                      WordPress.org readme
README.md                       This file
```
