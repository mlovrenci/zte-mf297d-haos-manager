"""MF297D Goform API with strict allowlisted writes.

ZTE firmware variants differ: supported API field presence does NOT prove a write
works on CR_A1HR...B08. No arbitrary goformId passthrough exists by design.
"""
import hashlib
import http.cookiejar
import ipaddress
import json
import zlib
import time
import urllib.error
import urllib.parse
import urllib.request


class RouterError(Exception):
    pass


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


GROUPS = {
    "device": ["cr_version", "wa_inner_version", "hardware_version", "web_version", "Language"],
    "internet": ["modem_main_state", "ppp_status", "network_type", "network_provider", "wan_ipaddr", "pin_status", "wan_apn", "pdp_type", "apn_interface_version", "opms_wan_mode", "BearerPreference", "ConnectionMode", "dial_mode", "simcard_roam"],
    "signal": ["lte_rsrp", "lte_rsrq", "lte_rssi", "lte_snr", "Z_SINR", "wan_active_band", "wan_active_channel", "wan_lte_ca", "lte_ca_pcell_band", "lte_ca_scell_band", "cell_id"],
    "lan": ["lan_ipaddr", "lan_netmask", "router_mode_gateway", "LocalDomain", "mac_address"],
    "dhcp": ["dhcpEnabled", "dhcp_enable", "dhcpStart", "dhcpEnd", "dhcpLease_hour", "dhcpLeaseTime", "dhcp_lease", "dhcpLease"],
    "dns": ["dns_mode", "prefer_dns_manual", "standby_dns_manual", "dns_primary_dns", "dns_secondary_dns"],
    "traffic": ["realtime_tx_thrpt", "realtime_rx_thrpt", "realtime_tx_thrp", "realtime_rx_thrp", "realtime_tx_bytes", "realtime_rx_bytes", "monthly_tx_bytes", "monthly_rx_bytes", "total_tx_bytes", "total_rx_bytes", "monthly_time"],
    "wifi_extra": ["wifi_chip1_ssid1_switch_onoff", "wifi_chip2_ssid1_switch_onoff", "wifi_chip1_ssid2_switch_onoff", "wifi_chip2_ssid2_switch_onoff", "wifi_chip1_ssid2_ssid", "wifi_chip2_ssid2_ssid", "wifi_chip1_ssid1_wifi_coverage"],
    "network_extra": ["rj45_state", "upnp_enable", "upnp_status", "upnp_setting_option", "dmz_switch", "dmz_ip_address", "DMZEnable", "DMZIPAddress", "nat_type", "port_mapping_enable", "ipv6_enable", "ipv6_wan_status"],
    "system_extra": ["uptime", "sys_uptime", "system_uptime", "router_uptime", "sntp_time_set_mode", "sntp_timezone", "sms_data_total"],
    "wifi": ["wifi_onoff_state", "wifi_chip1_ssid1_ssid", "wifi_chip2_ssid1_ssid", "wifi_chip1_ssid1_auth_mode", "wifi_chip2_ssid1_auth_mode", "wifi_chip1_ssid1_switch_onoff", "wifi_chip2_ssid1_switch_onoff", "wifi_chip1_ssid1_max_access_num", "wifi_chip2_ssid1_max_access_num", "guest_switch", "wifi_chip1_ssid1_access_sta_num", "wifi_chip2_ssid1_access_sta_num", "PASSWORD_ENCODE"],
}


class RouterClient:
    def __init__(self, router_ip, timeout=6):
        parsed = ipaddress.ip_address(router_ip)
        if not isinstance(parsed, ipaddress.IPv4Address) or not parsed.is_private or parsed.is_loopback or parsed.is_link_local:
            raise RouterError("Router mora biti privatna IPv4 adresa")
        self.ip = router_ip
        self.base = f"http://{router_ip}"
        self.timeout = timeout
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPRedirectHandler(),
        )
        self.authenticated = False

    def _request(self, path, data=None):
        headers = {"Referer": self.base + "/", "Origin": self.base,
                   "X-Requested-With": "XMLHttpRequest",
                   "Accept": "application/json, text/javascript, */*; q=0.01",
                   "User-Agent": "ZTE-Manager/0.4.7"}
        encoded = None
        if data is not None:
            encoded = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        req = urllib.request.Request(self.base + path, data=encoded, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                if resp.geturl().split("/", 3)[:3] != self.base.split("/", 3)[:3]:
                    raise RouterError("Router API preusmjerava na drugi host")
                raw = resp.read(131073)
                if len(raw) > 131072:
                    raise RouterError("Prevelik odgovor ZTE API-ja")
                obj = json.loads(raw.decode("utf-8"))
                if not isinstance(obj, dict):
                    raise RouterError("Neispravan API format")
                return obj
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
            raise RouterError(f"Nema ispravnog odgovora ZTE-a ({type(exc).__name__})") from exc

    def get(self, fields):
        if not fields or any(not k.replace("_", "").isalnum() for k in fields):
            raise RouterError("Nevaljana API polja")
        args = {"isTest": "false", "cmd": ",".join(fields),
                "_": str(int(time.time()*1000))}
        if len(fields) > 1:
            args["multi_data"] = "1"
        q = urllib.parse.urlencode(args)
        try:
            return self._request("/goform/goform_get_cmd_process?" + q)
        except RouterError:
            return self._request("/goform/goform_get_cmd_process", args)

    def login(self, password):
        if not password or len(password) > 256:
            raise RouterError("Lozinka nije konfigurirana")
        ld = self.get(["LD"]).get("LD")
        if not isinstance(ld, str) or not ld:
            raise RouterError("ZTE nije vratio LD challenge")
        resp = self._request("/goform/goform_set_cmd_process", {
            "isTest": "false", "goformId": "LOGIN", "password": sha(sha(password)+ld)})
        if str(resp.get("result", "")).lower() not in ("0", "success"):
            raise RouterError("Prijava na ZTE odbijena; provjeri lozinku")
        self.authenticated = True
        return True

    def query_groups(self, selected=None):
        result, errors = {}, {}
        groups = GROUPS if selected is None else {name: GROUPS[name] for name in selected if name in GROUPS}
        for name, keys in groups.items():
            try:
                values = self.get(keys)
                result[name] = {k: values[k] for k in keys if k in values and values[k] not in (None, "")}
            except RouterError as e:
                result[name] = {}
                errors[name] = str(e)
        return result, errors

    def clients(self):
        # IMPORTANT: MF297D / A1 B08: v0.1 queried station_list *alone*.
        # v0.2 combined it with host_name_web/mac_addr_web/ip_addr_web,
        # which can change Goform multi_data behavior and hide valid clients.
        # Keep the proven v0.1 single-key request, even when additional
        # client metadata is available on other ZTE firmware builds.
        raw = self.get(["station_list"])
        result = raw.get("station_list", [])
        if isinstance(result, str):
            try:
                result = json.loads(result) if result else []
            except (ValueError, TypeError):
                result = []
        if not isinstance(result, list):
            result = []
        clients = [{k: item.get(k, "") for k in ("hostname", "ip_addr", "mac_addr", "ssid_index")}
                   for item in result[:128] if isinstance(item, dict)]
        return clients, {}

    def lan_clients(self):
        try:
            raw = self.get(["lan_station_list"]).get("lan_station_list", [])
            if isinstance(raw, str):
                raw = json.loads(raw) if raw else []
            if not isinstance(raw, list):
                raw = []
            return [{k: item.get(k, "") for k in ("hostname", "ip_addr", "mac_addr", "ssid_index")}
                    for item in raw[:128] if isinstance(item, dict)]
        except (RouterError, ValueError, TypeError):
            return []

    def _diagnose_reservation_body(self, path, form=None):
        """Inspect HTTP transport without exposing router body or credentials.

        Called ONLY after a UTF-8 failure from the legacy read request.
        No config changes, no raw response logging, no sensitive header echo.
        """
        headers = {"Referer": self.base + "/", "Origin": self.base,
                   "X-Requested-With": "XMLHttpRequest",
                   "Accept": "application/json, text/javascript, */*; q=0.01",
                   "User-Agent": "ZTE-Manager/0.4.7"}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode("ascii")
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        req = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                if urllib.parse.urlsplit(resp.geturl()).netloc != urllib.parse.urlsplit(self.base).netloc:
                    return {"status": "redirect_to_other_host"}
                raw = resp.read(131073)
                if len(raw) > 131072:
                    return {"status": "response_too_large"}
                raw_type = resp.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                raw_enc = resp.headers.get("Content-Encoding", "").strip().lower()
                mime = raw_type if raw_type in ("application/json", "text/json", "text/plain", "text/html", "application/octet-stream") else "other_or_missing"
                encoding = raw_enc if raw_enc in ("gzip", "deflate", "identity", "") else "other"
                info = {"http_status": int(resp.status), "content_type": mime,
                        "content_encoding": encoding or "none", "bytes": len(raw)}
                if not raw:
                    return {"status": "empty_body", **info}
                kind = ("gzip_magic" if raw.startswith(b"\x1f\x8b") else
                        "zip_magic" if raw.startswith(b"PK\x03\x04") else
                        "utf8_bom" if raw.startswith(b"\xef\xbb\xbf") else
                        "json_like" if raw.lstrip().startswith((b"{", b"[")) else
                        "html_like" if raw.lstrip().lower().startswith((b"<!doctype", b"<html", b"<")) else
                        "unknown")
                info["payload_kind"] = kind
                decoded_raw = raw
                if kind == "gzip_magic" or encoding == "gzip":
                    try:
                        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
                        decoded_raw = d.decompress(raw, 131073)
                        if len(decoded_raw) > 131072 or not d.eof:
                            return {"status": "compressed_payload_invalid_or_too_large", **info}
                        info["decoded_compression"] = "gzip"
                    except zlib.error:
                        return {"status": "compression_error", **info}
                elif encoding == "deflate":
                    try:
                        d = zlib.decompressobj()
                        decoded_raw = d.decompress(raw, 131073)
                        if len(decoded_raw) > 131072 or not d.eof:
                            return {"status": "compressed_payload_invalid_or_too_large", **info}
                        info["decoded_compression"] = "deflate"
                    except zlib.error:
                        return {"status": "compression_error", **info}
                # Some B08 replies look like JSON but include non-UTF8 bytes or
                # malformed JavaScript-style values. Keep all diagnostics
                # content-free: never expose body snippets, host names, MACs,
                # IP addresses, session cookies, error text, or secrets.
                parsed = None
                analysis = []
                field_marker = b'"current_static_addr_list"' in decoded_raw
                info["field_token_present"] = field_marker
                try:
                    decoded_raw.decode("utf-8-sig")
                    info["utf8_valid"] = True
                except UnicodeDecodeError as e:
                    info["utf8_valid"] = False
                    info["utf8_first_invalid_byte"] = e.start
                for charset in ("utf-8-sig", "gb18030", "iso-8859-1", "utf-8-replace"):
                    try:
                        if charset == "utf-8-replace":
                            candidate = decoded_raw.decode("utf-8-sig", errors="replace")
                        else:
                            candidate = decoded_raw.decode(charset)
                    except UnicodeDecodeError:
                        analysis.append({"charset": charset, "result": "decode_error"})
                        continue
                    try:
                        response = json.loads(candidate)
                    except json.JSONDecodeError as exc:
                        # Standard-library error messages are not forwarded:
                        # report only a fixed category and an offset.
                        msg = exc.msg
                        if "Invalid control character" in msg:
                            issue = "unescaped_control_character"
                        elif r"Invalid \escape" in msg:
                            issue = "invalid_escape"
                        elif "Unterminated string" in msg:
                            issue = "unterminated_string"
                        elif "Extra data" in msg:
                            issue = "trailing_content"
                        elif "delimiter" in msg:
                            issue = "delimiter_or_separator"
                        elif "property name" in msg:
                            issue = "invalid_property_name"
                        elif "Expecting value" in msg:
                            issue = "invalid_value"
                        else:
                            issue = "invalid_json_syntax"
                        analysis.append({"charset": charset, "result": "json_syntax_error",
                                         "issue": issue, "offset": exc.pos})
                        continue
                    if not isinstance(response, dict):
                        analysis.append({"charset": charset, "result": "non_object_root"})
                        continue
                    parsed = response
                    info["parsed_charset"] = charset
                    if charset == "utf-8-replace":
                        info["lossy_decoding"] = True
                        info["replacement_characters"] = candidate.count("\ufffd")
                    break
                if parsed is None and kind == "json_like":
                    # Some firmware replies embed unescaped control bytes in a
                    # quoted value. JSONDecoder(strict=False) tolerates these
                    # without changing bytes, and replacement decoding allows
                    # us to count records without trusting the damaged text.
                    # NEVER export recovered values: hostname/IP/MAC may be
                    # corrupted; recovery is diagnostic, not proof of a usable
                    # configuration schema or valid reservation entries.
                    for charset in ("utf-8-replace", "iso-8859-1"):
                        if charset == "utf-8-replace":
                            candidate = decoded_raw.decode("utf-8-sig", errors="replace")
                        else:
                            candidate = decoded_raw.decode(charset)
                        try:
                            response = json.loads(candidate, strict=False)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if not isinstance(response, dict):
                            continue
                        parsed = response
                        info["parsed_charset"] = charset
                        info["recovery_method"] = "tolerate_control_chars"
                        info["recovered_untrusted_values"] = True
                        if charset == "utf-8-replace":
                            info["replacement_characters"] = candidate.count("\ufffd")
                        break
                if parsed is None:
                    # Fixed-format, bounded metadata only; local read-only
                    # diagnosis, with no raw text or user-configured values.
                    info["json_analysis"] = analysis
                    return {"status": "non_json_payload", **info}
                text = parsed
                field = "current_static_addr_list"
                if field not in text or text[field] is None:
                    return {"status": "field_absent", **info,
                            "result_key_present": "result" in text,
                            "error_key_present": "error" in text}
                value = text[field]
                if isinstance(value, str) and value.strip().startswith(("[", "{")):
                    try: value = json.loads(value, strict=False)
                    except ValueError: pass
                out = {"status": "field_present_empty" if value in ("", [], {}) else "field_present_nonempty",
                       **info, "value_type": type(value).__name__}
                if isinstance(value, list):
                    out["list_length"] = len(value)
                    out["list_item_types"] = sorted({type(v).__name__ for v in value[:25]})
                    if value and isinstance(value[0], dict):
                        out["first_item_field_count"] = len(value[0])
                if isinstance(value, dict):
                    out["object_field_count"] = len(value)
                if isinstance(value, str):
                    out["value_length"] = len(value)
                    out["text_structure"] = {"comma":value.count(","),"semicolon":value.count(";"),
                                             "pipe":value.count("|"),"newline":value.count("\n")}
                return out
        except urllib.error.HTTPError as err:
            return {"status": "http_error", "http_status": err.code}
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            return {"status": "transport_error", "reason": type(err).__name__}

    def probe_reservation_transport(self):
        """Read-only transport diagnosis; never returns raw reservation records.

        Some ZTE versions return errors to GET but accept POST to the GET endpoint.
        POST to /goform/goform_get_cmd_process is a *read*, not a config write.
        """
        field = "current_static_addr_list"
        query = urllib.parse.urlencode({"isTest": "false", "cmd": field, "_": str(int(time.time()*1000))})
        attempts = [("get", "/goform/goform_get_cmd_process?" + query, None),
                    ("post_read", "/goform/goform_get_cmd_process",
                     {"isTest": "false", "cmd": field, "_": str(int(time.time()*1000))})]
        output = {}
        for label, url, form in attempts:
            try:
                reply = self._request(url, form)
                if field in reply and reply[field] is not None:
                    v = reply[field]
                    if isinstance(v, str) and v.strip().startswith(("[", "{")):
                        try: v = json.loads(v)
                        except ValueError: pass
                    status = "field_present_empty" if v == "" or v == [] or v == {} else "field_present_nonempty"
                    output[label] = {"status": status, "value_type": type(v).__name__}
                    if isinstance(v, list):
                        output[label]["list_length"] = len(v)
                else:
                    output[label] = {"status": "field_absent",
                                     "result_key_present": "result" in reply,
                                     "error_key_present": "error" in reply}
            except RouterError as exc:
                cause = getattr(exc, "__cause__", None)
                if isinstance(cause, UnicodeDecodeError):
                    output[label] = self._diagnose_reservation_body(url, form)
                    continue
                status = getattr(cause, "code", None)
                output[label] = {"status": "request_error",
                                 "reason": ("http_" + str(status)) if isinstance(status, int) else
                                 (type(cause).__name__ if cause is not None else type(exc).__name__)}
        return output

    def dhcp_inventory(self):
        """Read-only B08 reservation & client DNS API discovery.

        Missing key, a present-but-empty key, and a populated key are distinct.
        Some ZTE builds return empty values for unknown fields, so even a
        returned empty key is not proof of support. No writes are attempted.
        """
        probes = {
            "reservations": [
                "current_static_addr_list", "static_addr_list", "dhcp_reservation_list",
                "bind_static_addr_list", "bind_static_ip_list", "dhcpReservationList",
            ],
            "dhcp_client_dns": [
                "dhcp_dns1", "dhcp_dns2", "dhcpDns1", "dhcpDns2",
                "lan_dns1", "lan_dns2", "lan_dns_proxy", "dhcp_dns_mode",
                "dhcp_dns_primary", "dhcp_dns_secondary", "dhcp_option6_dns",
            ],
            "client_metadata": ["hostNameList", "mac_ip_status", "host_name_web"],
        }
        data, present, field_status, errors = {}, {}, {}, {}
        for group, names in probes.items():
            values, seen, statuses = {}, [], {}
            for name in names:
                try:
                    reply = self.get([name])
                    if name not in reply or reply[name] is None:
                        statuses[name] = "not_returned"
                        continue
                    seen.append(name)
                    raw = reply[name]
                    value = raw
                    if isinstance(raw, str):
                        trimmed = raw.strip()
                        if trimmed.startswith(("[", "{")):
                            try: value = json.loads(trimmed)
                            except ValueError: value = raw
                    if group == "reservations":
                        if isinstance(value, list):
                            clean = []
                            for entry in value[:128]:
                                if isinstance(entry, dict):
                                    clean.append({k: str(entry[k])[:100] for k in
                                        ("mac_addr", "mac", "ip_addr", "ip", "hostname", "name", "domain")
                                        if entry.get(k)})
                            values[name] = clean
                            statuses[name] = "populated" if value else "returned_empty_list"
                        elif value in ("", {}, None):
                            statuses[name] = "returned_empty"
                        else:
                            statuses[name] = "returned_unparsed_" + type(value).__name__
                    elif group == "dhcp_client_dns":
                        if isinstance(value, (str, int)):
                            if str(value) != "":
                                values[name] = str(value)[:100]
                                statuses[name] = "populated"
                            else: statuses[name] = "returned_empty"
                        else:
                            statuses[name] = "returned_unparsed_" + type(value).__name__
                    else:
                        # Do not export hosts, MAC addresses or any unknown
                        # client metadata values; expose only existence and type.
                        statuses[name] = ("returned_empty" if value in ("", [], {}) else
                                          "populated_" + type(value).__name__)
                except (RouterError, ValueError, TypeError) as exc:
                    statuses[name] = "error"
                    errors[name] = type(exc).__name__
            data[group] = values
            present[group] = seen
            field_status[group] = statuses
        transport_probe = self.probe_reservation_transport()
        return {"fields_present": present, "field_status": field_status,
                "data": data, "errors": errors, "transport_probe": transport_probe,
                "note": "Returned empty list may mean no reservations OR unsupported API. "
                        "Goform read results never establish write support on B08."}

    def _ad(self):
        fields = self.get(["wa_inner_version", "cr_version", "RD"])
        for k in ("wa_inner_version", "cr_version", "RD"):
            if not fields.get(k):
                raise RouterError("AD autentikacijski token nije dostupan; write odbijen")
        return sha(sha(str(fields["wa_inner_version"])+str(fields["cr_version"]))+str(fields["RD"]))

    def set(self, command, params):
        # Back-end allowlist, not just a UI restriction.
        allowed = {"DHCP_SETTING", "SET_WIFI_SSID1_SETTINGS", "SET_WIFI_SSID2_SETTINGS", "SET_BEARER_PREFERENCE", "SET_CONNECTION_MODE", "UPNP_SETTING", "DMZ_SETTING", "REBOOT_DEVICE", "ROUTER_DNS_SETTING", "SET_WIFI_INFO", "CONNECT_NETWORK", "DISCONNECT_NETWORK"}
        if command not in allowed:
            raise RouterError("Zabranjena ili nepoznata write naredba")
        request = {"isTest": "false", "goformId": command, **params, "AD": self._ad()}
        resp = self._request("/goform/goform_set_cmd_process", request)
        result = str(resp.get("result", "")).lower()
        if result not in ("0", "success"):
            raise RouterError("ZTE nije potvrdio spremanje (odgovor nije success/0)")
        return {"result": "accepted", "goformId": command}