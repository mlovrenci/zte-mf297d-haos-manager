# ZTE Manager (MF297D)

Home Assistant OS App using the local Goform API. Open **Documentation** for configuration instructions.

**Warning:** This project targets A1 B08 firmware and has unverified write support. Leave write options disabled until validated.

## v0.5.4: DHCP migration inventory

On app startup, an authenticated read-only snapshot of ZTE DHCP reservations,
current Wi-Fi clients and wired clients is exported once to the local Home
Assistant MQTT diagnostic entity `ZTE migration inventory`. MAC addresses and
IP addresses remain inside the private HA/MQTT system; no credentials are
included. This is an observation snapshot, **not** an exhaustive ZTE DHCP
lease database; disconnected clients may be missing. It does not modify ZTE,
AdGuard, DNS, or DHCP. Remove the temporary MQTT discovery and retained
messages after completing the migration inventory.
