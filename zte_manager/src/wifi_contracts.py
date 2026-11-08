"""Reviewed static service-function contracts, not live write implementations."""
from copy import deepcopy
from webui_evidence import SERVICE_SHA256

_BASE = {
    'SET_WIFI_SSID1_SETTINGS': {
        'fields': {'ssid':'SSID', 'broadcastSsidEnabled':'broadcast', 'MAX_Access_num':'station',
                   'security_mode':'AuthMode', 'cipher':'cipher', 'NoForwarding':'NoForwarding'},
        'protected_modes':['WPAPSKWPA2PSK','WPA2PSK'],
        'conditional_fields':{'security_shared_mode':'cipher when protected; otherwise NONE',
                              'passphrase':'passPhrase; base64 only if config.PASSWORD_ENCODE is true'},
        'source_function':'u',
    },
    'SET_WIFI_SSID2_SETTINGS': {
        'fields': {'m_SSID':'m_SSID','m_HideSSID':'m_broadcast','m_MAX_Access_num':'m_station',
                   'm_AuthMode':'m_AuthMode','cipher':'m_cipher','m_NoForwarding':'m_NoForwarding'},
        'protected_modes':['WPAPSKWPA2PSK','WPA2PSK'],
        'conditional_fields':{'m_EncrypType':'m_cipher when protected; otherwise NONE',
                              'm_WPAPSK1':'m_passPhrase; base64 only if config.PASSWORD_ENCODE is true'},
        'source_function':'c',
    },
    'SET_WIFI_INFO': {
        'fields':{},
        'variants':[
            {'source_function':'f','behavior':'wifiEnabled == 0 discards all other input properties; otherwise passes the caller object through'},
            {'source_function':'mt','fields':{'wifiMode':'mode','countryCode':'countryCode','MAX_Access_num':'station','m_MAX_Access_num':'m_station','selectedChannel':'channel'},
             'conditional_fields':{'wifi_band':'wifiBand if WIFI_BAND_SUPPORT','abg_rate':'rate unless WIFI_BAND_SUPPORT and wifiBand == a','wifi_11n_cap':'bandwidth if WIFI_BANDWIDTH_SUPPORT'}},
        ],
    },
    'WIFI_ADVANCE_SET': {
        'source_function':'ft',
        'fields':{'wifiMode':'mode','countryCode':'countryCode',
                  'm_WirelessMode':'m_WirelessMode','m_CountryCode':'m_CountryCode',
                  'selectedChannel':'channel','m_Channel':'m_Channel'},
        'conditional_fields':{
            'wifi_band':'wifiBand if WIFI_BAND_SUPPORT',
            'm_wifi_band':'m_wifi_band if WIFI_BAND_SUPPORT',
            'abg_rate':'rate unless WIFI_BAND_SUPPORT and wifiBand == a',
            'wifi_11n_cap':'bandwidth if WIFI_BANDWIDTH_SUPPORT',
            'm_wifi_11n_cap':'m_wifi_11n_cap if WIFI_BANDWIDTH_SUPPORT'},
    },
    'SET_M_WIFI_INFO': {
        'source_function':'l',
        'fields':{'m_WirelessMode':'m_WirelessMode','m_CountryCode':'m_CountryCode',
                  'm_Channel':'m_Channel'},
        'conditional_fields':{'m_wifi_band':'m_wifi_band if WIFI_BAND_SUPPORT',
                              'm_wifi_11n_cap':'m_wifi_11n_cap if WIFI_BANDWIDTH_SUPPORT'},
    },
}


def catalogue():
    return {'source_sha256':SERVICE_SHA256,'source_path':'/js/service.js',
            'evidence':'service_function_review','write_verified':False,'sendable':False,
            'contracts':deepcopy(_BASE),
            'read_mappings':{
                'source_function':'gt',
                'main_ssid':{'radio1':'wifi_chip1_ssid1_ssid',
                             'radio2':'wifi_chip2_ssid1_ssid'},
                'guest_ssid':{'radio1':'wifi_chip1_ssid2_ssid',
                              'radio2':'wifi_chip2_ssid2_ssid'},
                'global_guest_switch':'guest_switch',
                'per_guest_switches':['wifi_chip1_ssid2_switch_onoff',
                                      'wifi_chip2_ssid2_switch_onoff'],
                'note':'Stock status getter labels SSID2 as guest; this does not map a guest SSID to any write command.',
            },
            'unresolved':['UI caller to radio/SSID mapping','Meaning of coded channel/width/security values',
                          'Required unchanged values and config flags','Shared transport/authentication wrapper Je',
                          'Whether the setter-only aliases are supported by the read API',
                          'Controlled live write followed by independent readback']}
