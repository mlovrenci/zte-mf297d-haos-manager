## 0.5.5 - Wi-Fi radio diagnostics (read-only)

- Add a Wi-Fi-tab-only read-only radio probe for band steering, DFS, automatic channel selection, channel and channel width candidates, and guest client counts. Unknown B08 fields are explicitly marked as not returned, not invented as supported.
- Add a connected Wi-Fi client snapshot grouped by ZTE-reported SSID index, with optional RSSI and link-rate values only if present in the original `station_list` response; do not assume SSID index means 2.4 or 5 GHz.
- Preserve single-key `station_list` semantics and normal status polling latency. No new router writes; DHCP/DNS and existing write logic unchanged.

## 0.5.0
- Display recovered `current_static_addr_list` records in a read-only LAN/DHCP table, with untrusted-value warning.
- Keep reservation values off MQTT and service logs; no router writes added.

## 0.5.0
- Run Python under S6 `with-contenv` to expose HAOS Supervisor token for read-only MQTT service discovery.
- Add non-secret MQTT transport error reason codes and token-path tests. No ZTE write changes.

## 0.5.0
- Startup self-test uses only two read requests instead of the 20+ field inventory, avoiding long timeouts.
- No router configuration changes.

## 0.4.7
- One read-only DHCP inventory self-test at app startup, enabled by default via `startup_probe_once`.
- Can be disabled in HAOS app options. Existing secrets/config remain untouched during update.
- No router write changes.

# Changelog

## 0.4.6
- Show recovered DHCP reservation probe result in UI (previously invisible).
- Optional one-shot MQTT diagnostics sensor, using MQTT service permission only (no Home Assistant admin API).
- Classify recovered list/dict/string structural metadata without publishing raw IP/MAC records.
- No additional router writes. All writes remain locked by default.

# Changelog

## 0.4.5
- Read-only recovery of malformed DHCP reservation API response with untrusted values excluded from write operations.
- Kept experimental router writes disabled by default.

## 0.4.4
- Read-only JSON encoding and syntax diagnostics for `current_static_addr_list`.

## 0.4.3
- Read-only compressed/content-type response diagnostics.

## 0.4.2
- GET/POST read-path diagnostics for DHCP reservation field.

## 0.4.1
- DHCP reservation inventory: distinguish empty values from failed queries.

## 0.4.0
- Expanded router management UI with gated experimental write operations.

## 0.5.1 - One-time MAC-IP static reservation test
- Added dedicated MQTT-discovered diagnostic button for a single controlled test of A1 B08 DHCP reservation write commands.
- Uses original ZTE WebUI fields for DHCP_RESERVATION_ADD/DEL and fixed dummy locally administered MAC plus 192.168.1.254 (outside known DHCP pool).
- Checks firmware, subnet, DHCP lease range, existing entries, then attempts to verify add and remove only the exact test entry.
- One-time marker prevents re-execution after reboot. No WAN/DHCP/Wi-Fi setting changes. Test button explicitly triggers a configuration write even with general writes disabled.

## 0.5.2 - Verified DHCP reservation management
- Add/Delete reservation editor in LAN / DHCP, backed by B08-tested `DHCP_RESERVATION_ADD` / `DHCP_RESERVATION_DEL`.
- Two-phase prepare + typed confirmation, 90-second expiry, fresh MAC/IP-list fingerprint and firmware checks, max 10 entries, duplicate checks, IPv4/subnet validation.
- Best-effort check for online clients using the requested IP with another MAC. Verified re-read after every write; no automatic retries or router reboots.
- Independent scope: general `write_enabled` remains false, but reservation Add/Delete is enabled after successful A1 B08 functional test. No DNS Option 6 write until separately verified.

## 0.5.3 - Read-only DHCP DNS Option 6 exploration

- Independently test likely LAN/DHCP DNS Goform field names against the actual B08 router.
- Read and scan a fixed list of stock WebUI JS/HTML paths for DHCP DNS handling.
- Publish sanitized metadata to `ZTE DHCP DNS Option 6 probe` in Home Assistant over MQTT.
- Never submit DNS or DHCP configuration writes; `option6_verified` remains false.
