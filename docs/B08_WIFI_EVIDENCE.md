# MF297D A1 B08 Wi-Fi evidence

Observed 2026-11-07 through ZTE Manager v0.6.4, using bounded GET-only static inspection of the configured router. No JavaScript was executed and no configuration write was sent. The firmware was previously read as `CR_A1HRMF297DV1.0.0B08`; this is observational evidence, not a signed firmware provenance attestation.

## Original service module

- Path: `/js/service.js`
- Size: 169768 bytes
- SHA-256: `8d5588e3b912827bc09a6380a84f4bef2815b56ce0ad487fdc63c5148c13aaa8`
- Command references: `SET_WIFI_INFO`, `SET_WIFI_SSID1_SETTINGS`, `SET_WIFI_SSID2_SETTINGS`.
- Parameter references: `ssid`, `wifiEnabled`, `m_ssid_enable`, `broadcastSsidEnabled`, `MAX_Access_num`, `security_mode`, `cipher`, `NoForwarding`, `passphrase`, `wifi_lbd_enable`.

The scanner finds literal names anywhere in the file. It does NOT yet associate each parameter with a command or establish required fields, value encoding, authentication handling, radio/SSID mapping, supported channels, side effects, or successful readback. No new writes are enabled based on these references.

## Other observed original assets

| Asset | SHA-256 |
| --- | --- |
| `/index.html` | `fab8bca6f771e14e94142bc23097b1a5f9da8335ec00a57a8ffcbf72a0eca6b5` |
| `/js/main.js` | `3268807548a2a2e419909eefa6d37420bf8d17a7ad9c8d92d549938001e3b934` |
| `/js/config/config.js` | `5bcda613d55ad9d2da687ffe022712d5419856061dcdcd51c6b654f307d99154` |

`/js/simulate.js` contains similar command references but is a simulator and must not be used as proof of actual firmware behavior. The scan reached its 12-request limit after 11 successfully read assets (the root redirect uses one request), so coverage is partial.

## Remaining verification

1. Inspect individual service functions and their UI callers; map fields, required unchanged values, encoding and band selection.
2. Build non-sendable request previews from that evidence and validate against synthetic fixtures.
3. Only after separate user approval, test one controlled live change with before/after reads. A `success` response alone does not establish application.

Channel and bandwidth candidates in the Manager's current read probes did not return values in the actual B08 snapshot. Their editors remain disabled; no values are guessed.
