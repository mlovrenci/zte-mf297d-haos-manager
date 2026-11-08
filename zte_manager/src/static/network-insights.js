'use strict';
const NetworkInsights = (() => {
 const text=v=>typeof v==='string'||typeof v==='number'?String(v):'';
 const number=v=>v!==null&&v!==undefined&&typeof v!=='boolean'&&String(v).trim()!==''&&Number.isFinite(Number(v))?Number(v):null;
 const mac=v=>/^([0-9a-f]{2}:){5}[0-9a-f]{2}$/i.test(text(v))?text(v).toLowerCase():null;
 function devices(snapshot){
  const sources=snapshot.sources||{wifi:{status:snapshot.clients_error?'unavailable':'ok',rows:snapshot.clients||[]}};
  return Object.entries(sources).flatMap(([source,data])=>(data.status==='ok'?data.rows:[]).map((d,i)=>({source,id:source+':'+(mac(d.mac_addr)||'unknown-'+i),name:text(d.hostname),ip:text(d.ip_addr),mac:mac(d.mac_addr)||text(d.mac_addr),index:text(d.ssid_index),rssi:number(d.rssi)})));
 }
 function select(rows,query='',source='',sort='name'){
  const q=query.toLowerCase().trim();
  return rows.filter(r=>(!source||r.source===source)&&[r.name,r.ip,r.mac,r.index].some(v=>v.toLowerCase().includes(q))).slice().sort((a,b)=>sort==='rssi'?(a.rssi===b.rssi?0:a.rssi===null?1:b.rssi===null?-1:b.rssi-a.rssi):text(a[sort]).localeCompare(text(b[sort]),'hr',{numeric:true}));
 }
 function warnings(snapshot){
  const rows=devices(snapshot),result=[],ips=new Map();
  for(const row of rows){if(!row.ip||!mac(row.mac))continue;const owners=ips.get(row.ip)||new Set();owners.add(row.mac);ips.set(row.ip,owners);}
  for(const [ip,owners] of ips)if(owners.size>1)result.push({code:'duplicate_ip',message:`Adresa ${ip} pojavljuje se uz ${owners.size} različita MAC-a. Provjeri zapise; to samo po sebi ne dokazuje aktivan konflikt.`});
  for(const [source,data] of Object.entries(snapshot.sources||{}))if(data.status!=='ok')result.push({code:'source_unavailable',message:`${source.toUpperCase()} popis nije dostupan; broj uređaja nije potpun.`});
  if(Object.keys(snapshot.errors||{}).length)result.push({code:'partial_read',message:'Dio grupa postavki nije očitan.'});
  return result;
 }
 function changes(before,after){
  if(!before)return [];
  const out=[];
  for(const group of ['wifi','wifi_extra','lan','dhcp','dns']){
   if(before.errors?.[group]||after.errors?.[group])continue;
   for(const [key,value] of Object.entries(after.groups?.[group]||{})){
    const old=before.groups?.[group]?.[key];
    if(old!==undefined&&old!==''&&value!==''&&text(old)!==text(value))out.push({kind:'setting',label:key,before:text(old),after:text(value)});
   }
  }
  for(const key of Object.keys(after.fields||{}))if(before.fields?.[key]!==undefined&&text(before.fields[key])!==text(after.fields[key]))out.push({kind:'setting',label:key,before:text(before.fields[key]),after:text(after.fields[key])});
  for(const source of ['wifi','lan']){
   if(before.sources?.[source]?.status!=='ok'||after.sources?.[source]?.status!=='ok')continue;
   const a=devices(before).filter(r=>r.source===source&&mac(r.mac)),b=devices(after).filter(r=>r.source===source&&mac(r.mac));
   for(const r of b)if(!a.some(x=>x.mac===r.mac))out.push({kind:'seen',label:r.name||r.mac,before:'Nije u prethodnom popisu',after:'Pojavio se u '+source.toUpperCase()+' popisu'});
   for(const r of a)if(!b.some(x=>x.mac===r.mac))out.push({kind:'missing',label:r.name||r.mac,before:'U prethodnom popisu',after:'Nije u novom '+source.toUpperCase()+' popisu (ne dokazuje offline stanje)'});
  }
  return out;
 }
 function diagnostic(snapshot){
  // Deliberate allowlist: no SSIDs, hostnames, addresses, arbitrary field values or errors.
  return {schema:1,version:/^\d+\.\d+\.\d+$/.test(snapshot.version)?snapshot.version:'unknown',sample_time:number(snapshot.sample_time),firmware_matches_b08:snapshot.groups?.device?.cr_version==='CR_A1HRMF297DV1.0.0B08',write_available:false,
   groups:Object.fromEntries(['device','internet','signal','wifi','wifi_extra','lan','dhcp','dns'].map(k=>[k,{fields_returned:Object.values(snapshot.groups?.[k]||{}).filter(v=>v!==''&&v!==null).length,read_failed:!!snapshot.errors?.[k]}])),
   sources:Object.fromEntries(['wifi','lan'].map(k=>[k,{status:snapshot.sources?.[k]?.status==='ok'?'ok':'unavailable',count:snapshot.sources?.[k]?.status==='ok'?devices(snapshot).filter(r=>r.source===k).length:null}])),
   warnings:[...new Set(warnings(snapshot).map(w=>w.code))]};
 }
 function wifiCompatibility(snapshot){
  // Export only fixed field *names* and presence flags. Never export returned
  // values, SSIDs, credentials, addresses, hostnames or raw error strings.
  const groups=snapshot?.groups||{},sources=[groups.wifi||{},groups.wifi_extra||{},snapshot?.fields||{}];
  const present=key=>sources.some(source=>Object.prototype.hasOwnProperty.call(source,key)&&source[key]!==null&&source[key]!==undefined&&source[key]!=='');
  const presence=keys=>Object.fromEntries(keys.map(key=>[key,present(key)?'returned':'not_returned']));
  const networks=Object.fromEntries([1,2].flatMap(chip=>[1,2].map(ssid=>{
   const prefix=`wifi_chip${chip}_ssid${ssid}_`;
   return [`radio${chip}_ssid${ssid}`,presence([prefix+'ssid',prefix+'switch_onoff',prefix+'auth_mode'])];
  })));
  return {schema:1,kind:'wifi_read_compatibility',firmware_matches_b08:groups.device?.cr_version==='CR_A1HRMF297DV1.0.0B08',
   wifi_group_read_failed:!!snapshot?.errors?.wifi,wifi_extra_group_read_failed:!!snapshot?.errors?.wifi_extra,
   advanced_read_failed:!!snapshot?.errors?.b08_advanced||!!snapshot?.errors?.b08_advanced_secondary,
   guest_read_failed:!!snapshot?.errors?.b08_guest,
   networks,advanced:presence(['WirelessMode','m_WirelessMode','CountryCode','m_CountryCode','Channel','m_Channel','HT_MCS','wifi_band','m_wifi_band','wifi_11n_cap','m_wifi_11n_cap','m_band_enable','wifi_lbd_enable','wifi_dfs_status','wifi_eacs_enable','wifi_enable','wifi_5g_enable']),
   guest:presence(['guest_switch','m_ssid_enable','m_HideSSID','wifi_chip1_ssid2_max_access_num','wifi_chip2_ssid2_max_access_num']),
   values_included:false,write_verified:false};
 }
 const signal=s=>({time:s.sample_time,rsrp:number(s.groups?.signal?.lte_rsrp),sinr:number(s.groups?.signal?.Z_SINR)});
 return {devices,select,warnings,changes,diagnostic,wifiCompatibility,signal};
})();
if(typeof module!=='undefined')module.exports=NetworkInsights;
