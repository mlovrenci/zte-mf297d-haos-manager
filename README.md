# ZTE MF297D Manager — Home Assistant OS App

Home Assistant OS App for ZTE MF297D routers using local Goform API, with a web interface via HA Ingress. Target firmware: `CR_A1HRMF297DV1.0.0B08`.

## Status

Version: **0.5.3**. Read capabilities include LTE/WAN, LAN/DHCP, Wi-Fi, clients, traffic and diagnostic data.

**General router configuration writes remain unverified on the actual A1 B08 firmware and are disabled by default.** DHCP MAC/IP reservation Add/Delete is independently confirmed and implemented. DHCP Option 6 DNS write remains **unimplemented/unconfirmed**. Don't disable DHCP or modify WAN, Wi-Fi, APN or DNS until each operation is independently verified and recovery access is available.

## Add to Home Assistant OS

In **Settings → Apps → Install app → ⋮ → Repositories**, add:

`https://github.com/mlovrenci/zte-mf297d-haos-manager`

The app will appear as **ZTE Manager (MF297D)**; it runs as a HAOS App, not a HACS integration.

## Migration from a local app

A GitHub-hosted repository is a **different Supervisor app identity** from a locally-installed app, even if the internal slug matches (`zte_manager`). Do not uninstall the working local app until you have backed up its settings and verified the repository version. Enter the router password in the new app's HAOS configuration screen; it is never stored in Git. Avoid running both monitors concurrently.

If using the repository app, leave the local app stopped once migration is validated. Reinstall/rollback to the local app if needed. Do not change router configuration during migration.

## Build

The app targets `amd64` and builds locally from `zte_manager/Dockerfile`. No image registry or GitHub Actions build pipeline required.

## Test

Run `python3 -m unittest discover -s tests -q` from the repository root.

## Security

- Do not put passwords, session tokens, debug dumps or `/data/options.json` into this repository.
- HA Ingress restricts direct exposure; do not publish the app on an internet-facing port.
- Router write operations are experimental and can cause loss of access.
- DHCP reservation API diagnostics may recover malformed router responses; recovered values are untrusted and must not be used for write operations.

See `zte_manager/DOCS.md` for details.

## Optional autonomous read-only diagnostics (v0.5.0)

With existing Mosquitto broker and MQTT integration, enable `mqtt_diagnostics_enabled: true` in HAOS App configuration to publish the **metadata only** of the DHCP API probe as `sensor.zte_dhcp_api_probe` (entity naming may vary). This is a one-shot read-only probe at app startup and when the dashboard's DHCP inventory is manually refreshed. No router write, no Home Assistant admin API permission. MQTT is optional (`mqtt:want`).

MQTT publishes retained diagnostics; disable the option to stop updates. Remove the retained discovery topic `homeassistant/sensor/zte_manager_dhcp_probe/config` if you want to delete the entity.

On v0.5.0 the default `startup_probe_once: true` performs one read-only inventory after each app start and publishes its result to MQTT, without needing existing router credentials to be resubmitted through the Supervisor options API. Disable this option to suppress the startup probe.

Startup diagnostic is limited to two read transport probes (`current_static_addr_list` GET and POST-read). Full API inventory remains available in the app UI.

### v0.5.0 MQTT fix

Python launches using S6 `/command/with-contenv` so that the HAOS Supervisor token is available for the MQTT service lookup. The app only reads `GET /services/mqtt`; no extra HAOS administrator permissions are requested. MQTT transport failures now print a non-secret reason code rather than a generic `RuntimeError`.

### v0.5.0 local reservation table

The `LAN / DHCP -> Reservations -> Read` view displays up to 64 recovered rows from `current_static_addr_list` using escaped text in a local Ingress-only table. Because B08 replies can contain invalid bytes, recovered values are marked **untrusted and read-only**. MQTT discovery and logs contain metadata only; no reservation IP/MAC data are sent to MQTT. The router is never modified by these reads.

## v0.5.1: experimental one-time reservation test
New MQTT diagnostic button `Run ZTE static binding test once` is intentionally a **write** test, separate from normal `write_enabled` (which remains false). Only press when authorized. It uses a dummy MAC `02:5A:54:45:00:FE` and `192.168.1.254` outside the current DHCP pool; checks B08 firmware and known LAN/DHCP settings; attempts to delete the dummy reservation immediately after reading back the result. Does not change DHCP server, WAN, DNS, or Wi-Fi. The result is shown in an MQTT diagnostic sensor. If cleanup fails, **do not reboot the router**; review the test status and remove the test MAC before further experiments. Existing static bindings are never deleted.

## v0.5.2: DHCP reservations confirmed on A1 B08
The local HAOS Ingress UI provides **Add/Delete** for MAC-IP reservations, using the exact ZTE form commands verified in a live 9 → 10 → 9 reservation test. Backend validates A1 B08 firmware, existing reservation list, duplicate MAC/IP, subnet, max 10 slots, and requires a separate typed confirmation before each mutation. After sending a write, it re-reads the reservation list to verify the result. `write_enabled: false` still disables all *other* unverified router mutations; reservation writes are a separately verified feature and are available through the local UI's confirmation flow. Edit can be done manually as remove + add, after checking impact on the client. DHCP Option 6 DNS write remains unimplemented/unverified.


## v0.5.3: DHCP DNS Option 6 read-only discovery

On startup, separately checks likely DHCP/LAN DNS Goform keys and reads a bounded allowlist of original ZTE WebUI static JS/HTML assets to identify whether a dedicated DHCP DNS setter exists in the B08 build. Publishes metadata to the HA MQTT diagnostic entity **ZTE DHCP DNS Option 6 probe**. The status `candidate_found` is *not proof* that changing DNS for DHCP clients is supported. WAN DNS/APN DNS is distinct from DHCP Option 6. No DNS, DHCP pool, APN, Wi-Fi or other router settings are changed during this probe.