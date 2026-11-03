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