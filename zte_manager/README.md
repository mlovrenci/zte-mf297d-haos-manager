# ZTE Manager (MF297D)

Home Assistant OS App using the local Goform API. Open **Documentation** for configuration instructions.

**Warning:** This project targets A1 B08 firmware and has unverified write support. Leave write options disabled until validated.

## v0.5.5: Wi-Fi radio diagnostics

Open the **Wi-Fi** tab to read available steering/DFS and channel/channel-width
fields plus currently connected wireless clients. The API keys for channel and
bandwidth are only candidates from related ZTE firmware: their support on A1
B08 is not yet confirmed. Values are shown only when the router returns them.
SSID index is kept as reported (not guessed as 2.4 or 5 GHz). Optional client
RSSI/link-rate fields appear only if present in `station_list`.

These extra queries run only when opening the Wi-Fi tab or pressing **Očitaj**.
No Wi-Fi settings, DHCP, DNS or router configuration are modified.

## v0.5.4: DHCP migration inventory

On app startup, an authenticated read-only snapshot of ZTE DHCP reservations,
current Wi-Fi clients and wired clients is exported once to the local Home
Assistant MQTT diagnostic entity `ZTE migration inventory`. MAC addresses and
IP addresses remain inside the private HA/MQTT system; no credentials are
included. This is an observation snapshot, **not** an exhaustive ZTE DHCP
lease database; disconnected clients may be missing. It does not modify ZTE,
AdGuard, DNS, or DHCP. Remove the temporary MQTT discovery and retained
messages after completing the migration inventory.
