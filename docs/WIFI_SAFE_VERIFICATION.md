# Wi-Fi verification without router configuration changes

## Completed

- Actual B08 read captured through Manager 0.6.6 on 2026-11-08. Sanitized fixture: `tests/fixtures/b08-read-redacted.json`. SSIDs are substituted, clients omitted, sample time replaced. This is an observed response, not an invented successful configuration.
- Offline replay checks before/after SSID drafts, missing channels and widths, invalid SSIDs, and unsupported security changes. A request remains non-sendable with `command: null` because radio/caller mapping is unverified.
- Browser tests cover disconnected refresh, HTTP 403, malformed response, stale data, and HTML escaping. Only allowlisted GET calls are permitted in the preview tests.
- Python suite runs with outbound sockets blocked except loopback test servers. No write test is sent to the router.

## Capture needed from the original UI

On a computer in the router's LAN, open the original ZTE UI and sign in normally. Open browser Developer Tools → Network, clear the list, then open Wi-Fi basic and advanced pages. Do not press Apply/Save, change switches, reconnect or select a different radio if doing so applies a change. Export a HAR with response content. Do not enable export of sensitive headers. Keep the original HAR private; even sanitized browser exports can contain session or Wi-Fi secrets in bodies.

Analyze locally from this checkout:

```sh
python tools/analyze_wifi_har.py wifi.har --output wifi-read-review.json
```

Share only `wifi-read-review.json`. The analyzer has no networking code. It keeps allowlisted Wi-Fi read keys, GET status, multi_data and field presence/emptiness. It omits origin, credentials, cookies, POST bodies, unknown keys and all response values. It does not execute or replay captured requests. Empty results mean no eligible GET was captured, not that Wi-Fi is unsupported. POST-form reads and dynamic radio selectors require a separate reviewed implementation, never blind replay.

## Remaining boundary

Compare the captured original queries with Manager probes before implementing further read calls. The current source catalogue documents builders, not a verified full request. Do not generate a guessed executable payload. A complete write claim still requires separate approval and a controlled write/readback, preferably on a spare MF297D running the same B08 firmware.
