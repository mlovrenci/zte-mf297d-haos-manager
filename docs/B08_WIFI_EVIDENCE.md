# MF297D A1 B08 Wi-Fi evidence

Observed 2026-11-07 through ZTE Manager v0.6.4, using bounded GET-only static inspection of the configured router. No JavaScript was executed and no configuration write was sent. The firmware was previously read as `CR_A1HRMF297DV1.0.0B08`; this is observational evidence, not a signed firmware provenance attestation.

## Original service module

- Path: `/js/service.js`
- Size: 169768 bytes
- SHA-256: `8d5588e3b912827bc09a6380a84f4bef2815b56ce0ad487fdc63c5148c13aaa8`
- Command references: `SET_WIFI_INFO`, `SET_WIFI_SSID1_SETTINGS`, `SET_WIFI_SSID2_SETTINGS`.
- Parameter references: `ssid`, `wifiEnabled`, `m_ssid_enable`, `broadcastSsidEnabled`, `MAX_Access_num`, `security_mode`, `cipher`, `NoForwarding`, `passphrase`, `wifi_lbd_enable`.

The scanner finds literal names anywhere in the file. The generic scanner does not associate parameters with commands. The subsequent pinned source review below establishes some builder mappings, but not complete requirements, authentication, radio/SSID mapping, supported values, side effects or successful readback. No new writes are enabled based on these references.

## Other observed original assets

| Asset | SHA-256 |
| --- | --- |
| `/index.html` | `fab8bca6f771e14e94142bc23097b1a5f9da8335ec00a57a8ffcbf72a0eca6b5` |
| `/js/main.js` | `3268807548a2a2e419909eefa6d37420bf8d17a7ad9c8d92d549938001e3b934` |
| `/js/config/config.js` | `5bcda613d55ad9d2da687ffe022712d5419856061dcdcd51c6b654f307d99154` |

`/js/simulate.js` contains similar command references but is a simulator and must not be used as proof of actual firmware behavior. The scan reached its 12-request limit after 11 successfully read assets (the root redirect uses one request), so coverage is partial.

## Remaining verification

1. Inspect UI callers and the shared transport wrapper; establish required unchanged values, configuration flags and radio/SSID selection.
2. Build non-sendable request previews from that evidence and validate against synthetic fixtures.
3. Only after separate user approval, test one controlled live change with before/after reads. A `success` response alone does not establish application.

Channel and bandwidth candidates in the Manager's current read probes did not return values in the actual B08 snapshot. Their editors remain disabled; no values are guessed.

## Pinned service review (v0.6.6)

The static catalogue at `/api/wifi_contracts` records these mappings from the pinned source. It does not contact the router, construct an executable request, or enable writes.

| Builder | Observed mapping / behavior |
| --- | --- |
| `u`, SSID1 | `ssid ← SSID`, `broadcastSsidEnabled ← broadcast`, `MAX_Access_num ← station`, `security_mode ← AuthMode`, `cipher ← cipher`, `NoForwarding ← NoForwarding` |
| `c`, SSID2 | `m_SSID ← m_SSID`, `m_HideSSID ← m_broadcast`, `m_MAX_Access_num ← m_station`, `m_AuthMode ← m_AuthMode`, `cipher ← m_cipher`, `m_NoForwarding ← m_NoForwarding` |
| `f`, SET_WIFI_INFO | Disabling Wi-Fi keeps only `wifiEnabled`; otherwise caller properties pass through. |
| `mt`, SET_WIFI_INFO | `wifiMode ← mode`, `countryCode ← countryCode`, `selectedChannel ← channel`, both station limits; band/rate/width depend on configuration flags. |

Both SSID builders recognize `WPAPSKWPA2PSK` and `WPA2PSK` for their protected branch. The password is base64-encoded only when `config.PASSWORD_ENCODE` is true. SSID2 uses `m_WPAPSK1` and `m_EncrypType`; SSID1 uses `passphrase` and `security_shared_mode`. This does not establish support for WPA3 in these builders. SSID2 must not be equated with a guest network or a particular radio without caller evidence.

Original getter `pt` requests `WirelessMode`, `CountryCode`, `Channel`, `HT_MCS`, `wifi_band`, `wifi_11n_cap`, and corresponding `m_` settings. These non-secret keys are now read separately from the earlier candidates. The UI displays returned channel/width/region values verbatim; width codes are not labelled MHz and are not assigned to chip1/chip2 editors. No passwords or PSKs are requested.

## Stock status getter `gt` (v0.6.8)

The pinned `/js/service.js` status getter returns `ssid` from `wifi_chip1_ssid1_ssid`, `m_ssid` from `wifi_chip2_ssid1_ssid`, `ssidGuest` from `wifi_chip1_ssid2_ssid`, and `m_ssid_guest` from `wifi_chip2_ssid2_ssid`. It separately returns the global `guest_switch`, and per-chip `ssid2_switch_onoff` fields. Thus SSID2 labels are backed by the original status getter as guest SSIDs. **It does not establish that `SET_WIFI_SSID2_SETTINGS` writes a guest SSID**: the similarly named setter uses `m_SSID`, while `gt` maps its `m_ssid` to chip2 SSID1. We still lack the UI caller and a controlled write/readback test.

The stock getter also references `wifi_chip1_ssid2_max_access_num`, `wifi_chip2_ssid2_max_access_num`, `m_ssid_enable` and `m_HideSSID`. v0.6.8 probes only these four additional non-secret fields on explicit preview refresh, renders raw values without collapsing global/per-SSID switches, and adds field-presence flags to the export. Missing responses remain unverified; they are not treated as zero/disabled. The getter also references passwords, but the Manager **never requests or exports them** in this feature.

## Advanced aliases and local-only drafts (v0.6.9)

The pinned source includes additional, distinct setter builders: `WIFI_ADVANCE_SET` (`ft`, with `selectedChannel`, `m_Channel` and conditional width fields), and `SET_M_WIFI_INFO` (`l`, second set of radio fields). The static `/api/wifi_contracts` catalogue records them as **non-sendable** evidence, without building an HTTP request. The status getter `pt` names `Channel`, `m_Channel`, and `wifi_11n_cap` but these did **not** return values during the v0.6.7 read of this firmware.

To investigate whether this B08 variant exposes different names, the preview performs one additional bounded GET with `selectedChannel`, `wifiMode`, `countryCode`, `abg_rate`. These names are **observed as setter parameters only**; GET support is unverified, and missing values remain unknown. The compatibility export includes presence flags, never values.

For each SSID whose switch is explicitly read as `0` or `1`, the browser can build an on/off comparison alongside an SSID draft. A global guest switch of `0` and a per-SSID switch of `1` are not automatically considered contradictory: independent semantics remain unresolved. This never creates a sendable payload. The UI also labels recognized raw security codes, while guest security remains unknown when its getter field is absent.

## Focused Wi-Fi UI module scan (v0.7.0)

The original general WebUI inspection spent its fixed 12-request budget on bootstrap and unrelated library files, before it reached the actual menu/router implementation. The **Sustav → Analiziraj izvorne Wi-Fi module** action now launches a separate bounded inspector starting exclusively at `/js/config/menu.js`, `/js/router.js`, and `/js/config/config.js`. It follows only literal Wi-Fi-related AMD dependencies or Wi-Fi module paths quoted in those static files. This is a source *reference inventory* only, not a declaration that a UI route exists or a command works. No automatic polling, JavaScript execution, source export or Goform writes take place.

The result must be validated against actual B08 asset hashes and observed static names before trusting any claimed parameter-to-screen mapping. Channel/width setters remain disabled until there is verified getter and caller evidence. All other router settings remain untouched.
