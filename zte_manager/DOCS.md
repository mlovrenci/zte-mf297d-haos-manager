# ZTE Manager v0.4.0 — MF297D

Local HAOS App with Home Assistant Ingress and **no exposed host port**. The ZTE remains the WAN gateway, NAT, Wi-Fi and LAN switch. It does not install AdGuard or alter DHCP at installation time.

## Features

- Status overview, active WAN/network/SIM/APN, LTE radio metrics and aggregation info (where firmware reports values)
- DHCP/LAN and WAN DNS readout (do **not** confuse WAN DNS with DHCP option 6)
- Wi-Fi 2.4/5 GHz, guest SSIDs and status when returned
- Connected clients — preserved **single-key `station_list`** read from v0.1
- Traffic counters and current throughput when provided by B08
- Optional, password-free SQLite metrics history of RSRP/RSRQ/SINR and traffic (14 days)
- NAT/IPv6 readouts only if B08 returns these fields
- Per-feature API availability matrix; safe diagnostic copy (field names only, never passwords/tokens)
- Write plan + approval for the existing three experimental operations: DHCP settings, primary Wi-Fi SSID/password and network bearer preference. **No write has been verified live on B08.**
- DHCP reservations and DHCP-client DNS (Option 6) are **read-probed** on several known ZTE field names. They are **not writable** until the B08 request schema and read-back are verified. UPnP, DMZ, restart and WAN link have approval-gated experimental write; APN, SMS and port forwarding are unavailable for write. No generic arbitrary Goform passthrough.

## Safe initial config

`router_ip` — ZTE LAN IPv4 address.

`router_password` — configure *only* in HAOS App settings; never insert into source code, notes, chat exports or GitHub.

`monitor_enabled: false` — enable optional background sampling every 300 seconds; logs no sensitive identifiers.

`write_enabled: false` — disable configuration mutations.

`allow_experimental_writes: false` — dedicated opt-in for unverified B08 writes; no values are changed automatically. `b08_write_verified: false` is documentary status only; do not misrepresent it as verified until read-back confirms real operation.

`allow_disruptive_changes: false` — additionally guards DHCP OFF, Wi-Fi SSID/password, bearer preference.

`allow_apn_changes: false` — reserved; APN write remains disabled in the code.

### When user eventually enables writes

1. Backup ZTE configuration; have local access and a static-IP recovery computer ready.
2. Compare actual read values and firmware on the API diagnostics screen.
3. Enable `write_enabled` and (only after understanding the uncertainty) `allow_experimental_writes`; the app *also* requires matching `expected_firmware`.
4. For disruptive changes enable `allow_disruptive_changes` temporarily.
5. Submit a plan; type a one-time confirmation phrase; the app re-reads the router and rejects if tracked values changed.
6. Check actual post-change state; `result:0` **does not prove** all settings took effect. Revert guards after use.

**Never turn off ZTE DHCP until AdGuard DHCP on HAOS has been tested with a real client and a ZTE rollback route exists.**

### Monitor storage

Under private App `/data/zte_history.sqlite3`; max 14-day retention. Stores timestamps, radio metrics, throughput API numeric values, WAN status/operator and cell label. No passwords, token, MAC, IMEI, IMSI, phone number, SMS bodies or raw API dumps.

### Troubleshooting

- No clients: `station_list` may be empty when no Wi-Fi clients are active or after firmware changes. Check the Clients tab. This endpoint does **not** equal a complete DHCP lease table.
- Empty fields: unsupported, currently missing, or a firmware Goform response issue. See API Diagnostics.
- Wrong router password / login failures: check HAOS App options, then reboot **only the App**, not the ZTE.
- Historics empty: turn `monitor_enabled` on and restart the App; wait for samples. Tests use simulated ZTE data, so live B08 support remains to be confirmed.
- If desired, uninstall the app without changing ZTE LAN settings; the App has no cloud dependency.

#### v0.3.1 B08 diagnostic corrections
Traffic: byte counters are available even when real-time throughput is not reported. SNTP config values do not imply uptime support. Network snapshot in diagnostics includes only allowed LAN/DHCP/DNS values for preparing non-disruptive schema validation. Write APIs remain unverified on B08.

### Preferred architecture — ZTE DHCP + AdGuard DNS
If B08 supports setting DNS served to DHCP clients (Option 6), keep ZTE's DHCP ON and reserve HAOS a fixed LAN IP. Point **DHCP client DNS** at HAOS; WAN DNS changes alone do not demonstrate Option 6 support. Check actual client DHCP lease first (DNS and gateway must differ). Do not use public DNS as a second DHCP resolver, or filtering can be bypassed. If Option 6 support cannot be shown, don't pretend that changing `ROUTER_DNS_SETTING` achieves it.

Version 0.4.1 includes a read-only per-field Goform inventory for `current_static_addr_list` and possible DHCP DNS properties. No blind reservation write.

### v0.4.1
DHCP inventura sada prikazuje prazne liste kao zaseban status, bez poistovjećivanja s nepostojećim poljem. Dodatni read-only probes; write ostaje nepodržan do B08 validacije.

### v0.4.2 — Reservation read transport diagnostics
For current_static_addr_list, safely probe both GET and POST on the **get** endpoint and expose only sanitized shape/error classifications. No reservation write.

### v0.4.3 — Safe HTTP response diagnosis
When A1 B08 returns non-UTF-8 data for `current_static_addr_list`, the app re-requests the same read endpoint for bounded diagnosis. Captures only HTTP status, generalized content headers, payload kind and length, optional gzip/deflate decoding, JSON field existence, value type and list length. No raw body, cookies, MAC/IP list, passwords or response strings are shown. No DHCP write.

## v0.4.4: JSON-syntax diagnosis for DHCP reservations

The B08 `current_static_addr_list` probe returned a 767-byte JSON-like body with `text/html` MIME, but none of the v0.4.3 JSON decoder candidates parsed it. v0.4.4 adds content-free JSON syntax error classification for the read-only endpoint, distinguishing UTF-8 failure, syntactic invalidity, and presence of the fixed reservation field token. This does not verify DHCP reservation read or write support.


## v0.4.5 — B08 malformed JSON read-only recovery

For `current_static_addr_list` only, the diagnostic probe can salvage a JSON object
containing raw control characters and/or invalid UTF-8 in string values. It tries
UTF-8 replacement and Latin-1 with a non-strict JSON string decoder, and **only
returns field presence, type, and list length** (not corrupt reservation values).
An explicit `recovered_untrusted_values` flag means entries have NOT been verified
for a safe DHCP reservation write. No write API has been added or unlocked.


## Wi-Fi pregled i navigacija (0.5.6)

Wi-Fi je pod **Lokalna mreža → Wi-Fi**; DHCP rezervacije ostaju pod LAN/DHCP,
Option 6 pod DNS/AdGuard, a audit pod Sustav → API dijagnostika / Audit.
Gornja grupa pamti posljednji otvoreni podizbornik samo dok je stranica otvorena.

Wi-Fi detalji se čitaju pri otvaranju podizbornika i gumbom Očitaj; filtri,
sortiranje i izvoz ne pozivaju router. Izvoz JSON-a sadrži samo filtrirane
klijente, vrijeme očitanja i korištene filtre. Sadrži osobne mrežne podatke
(ime/IP/MAC); ne uključuje lozinke, session tokene ili WPS PIN.

Usporedba radio parametara vrijedi samo za polja vraćena u oba uzastopna
uspješna odgovora. Prazan/neuspješan odgovor nije dokaz da je uređaj offline,
radio isključen ili funkcija nepodržana. Vrijeme je lokalno vrijeme završetka
HTTP očitanja u pregledniku, a ne timestamp routera. RSSI se sortira prema
numeričkoj API vrijednosti, bez pretpostavke o jedinici; nepoznate vrijednosti
su posljednje. SSID indeksi se ne mapiraju automatski u frekvencijske pojaseve.

Daljnji prioriteti nakon verifikacije izvornog A1 B08 API-ja: neovisno
upravljanje 2,4/5 GHz, guest mreža i izolacija, kanal/širina, band steering.
Za te nove kontrole u ovoj verziji nema write naredbi. Testiranje u ovoj verziji
koristi simulirane odgovore; nije potvrda kompatibilnosti novih polja na živom B08.


### Write mode iz sučelja

Tipka u zaglavlju izravno uključuje/isključuje write mode bez poziva ZTE-u.
Prekidač je zajednički svim prozorima ove instance Managera i vrijedi do restarta
App-a. Ne zapisuje Supervisor options.json; nakon restarta vrijede konfigurirane
vrijednosti write_enabled i allow_experimental_writes. Svako prebacivanje poništava
pripremljene promjene. Isključivanje obuhvaća i DHCP rezervacije. Postojeća
provjera firmwarea, potvrda pojedinačnih radnji, allow_disruptive_changes,
allow_system_reboot i wifi_password_format ostaju na snazi.
