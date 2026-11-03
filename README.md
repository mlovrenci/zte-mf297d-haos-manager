# ZTE MF297D Manager — Home Assistant OS App

Home Assistant OS App for ZTE MF297D routers using local Goform API, with a web interface via HA Ingress. Target firmware: `CR_A1HRMF297DV1.0.0B08`.

## Status

Version: **0.4.5**. Read capabilities include LTE/WAN, LAN/DHCP, Wi-Fi, clients, traffic and diagnostic data.

**Router configuration writes have NOT been verified on the actual A1 B08 firmware.** All write options are disabled by default. DHCP reservations and DHCP Option 6 DNS write are **not implemented/confirmed**. Don't disable DHCP or modify WAN, Wi-Fi, APN or DNS until each operation is independently verified and recovery access is available.

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