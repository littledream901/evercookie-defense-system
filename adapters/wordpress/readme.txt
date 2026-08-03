=== Fangyu Defense ===
Contributors: fangyuteam
Requires at least: 5.9
Tested up to: 6.7
Requires PHP: 7.4
Stable tag: 2.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Anti-bot visitor defense plugin powered by the Fangyu V2 gateway.

== Description ==

Fangyu Defense integrates WordPress with the Fangyu V2 gateway to identify and
respond to bot traffic, scrapers, and hostile visitors using evercookie-based
fingerprinting combined with HMAC-SHA256-signed adapter requests.

**How it works**

1. On each front-end page request, the plugin extracts the visitor's IP, User-Agent,
   evercookie repeat value, and current URL.
2. These are sent as a signed JSON payload to your Fangyu V2 gateway (`/v2/decide`).
3. The gateway returns a disposition (pass / serve_alt / redirect / challenge / deny /
   not_found).
4. The plugin executes that disposition before WordPress renders the page.

**Mechanisms**

* `pass` — visitor is allowed through normally.
* `serve_alt` — the gateway's alternate page content is served (e.g. a decoy landing
  page injected with the SDK), with no trace of the real site content.
* `redirect` — visitor is redirected to the configured URL (302 by default).
* `challenge` — visitor sees a security-check page (CAPTCHA or JS challenge).
* `deny` — visitor receives HTTP 403.
* `not_found` — visitor sees a realistic 404 page.

**Security notes**

* Only `CF-Connecting-IP`, `True-Client-IP`, and `X-Real-IP` are trusted for IP
  extraction (when the peer is in a known Cloudflare / CloudFront CIDR).
  `X-Forwarded-For` is deliberately ignored to prevent spoofing.
* Requests are signed with HMAC-SHA256; the `app_secret` never leaves your server.
* Logged-in administrators are never intercepted, preventing self-lockout.

== Installation ==

1. Upload the `fangyu-defense` directory to `/wp-content/plugins/`.
2. Activate the plugin in **Plugins > Installed Plugins**.
3. Go to **Settings > Fangyu Defense** and fill in:
   - **Gateway URL** — base URL of your Fangyu V2 gateway (no trailing slash).
   - **App ID** — numeric application ID from the gateway admin.
   - **API Key** — sent as the `X-App-Key` request header.
   - **App Secret** — used to sign requests (never transmitted to the gateway).
   - **Fail Mode** — `open` (default) or `closed`.
4. Click **Run Check** to verify the connection.

== Frequently Asked Questions ==

= What PHP version is required? =
PHP 7.4 or higher. The plugin avoids PHP 8+ features to maintain broad hosting compatibility.

= What happens if the gateway is unreachable? =
With **Fail Mode: open** (default), all traffic is allowed through. With **Fail Mode: closed**,
all traffic receives a 403 until the gateway comes back.

= Is `app_secret` transmitted to the gateway? =
No. It is used only on your server to compute the HMAC signature. The gateway verifies
the signature using its own copy of `app_secret`.

= Why is X-Forwarded-For ignored? =
`X-Forwarded-For` is trivially spoofable by any client. The plugin only reads trusted
CDN-specific headers (`CF-Connecting-IP`, `True-Client-IP`, `X-Real-IP`) when the
socket peer is in a known CDN IP range.

== Changelog ==

= 2.0.0 =
* Initial V2 release. HMAC-SHA256 signing, V2 three-layer disposition model,
  evercookie SDK bundled, WP-options-based configuration.
