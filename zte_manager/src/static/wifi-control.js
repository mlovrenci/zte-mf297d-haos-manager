'use strict';
// Exact, independently sourced B08 read projections. Local plans are NEVER sendable.
const WifiControl = (() => {
  const apFields=Object.freeze(['AccessPointSwitchStatus','ApBroadcastDisabled','ApIsolate','ApMaxStationNumber']);
  const flagFields=new Set(apFields.slice(0,3));
  const authCodes=new Set(['WPA2PSK','WPAPSKWPA2PSK','WPA3PSK','WPA2PSKWPA3PSK','WPAPSK','OPEN','NONE']);
  const pairs=Object.freeze({'1:1':['0','0'],'1:2':['0','1'],'2:1':['1','0'],'2:2':['1','1']});
  const scalar=(value)=>typeof value==='string'||typeof value==='number'?String(value):null;
  const flag=value=>{const v=scalar(value);return v==='0'||v==='1'?v:null;};
  const maxClients=value=>{const v=scalar(value);return v!==null&&/^(0|[1-9][0-9]{0,3})$/.test(v)&&Number(v)<=1024?v:null;};
  const validFirmware=s=>s?.groups?.device?.cr_version===WifiDraft.expected;
  function apRows(data){
    if(data?.status!=='read_only'||data.ap_status!=='observed'||data.write_available!==false||!Array.isArray(data.access_points)||data.access_points.length>4)return new Map();
    const rows=new Map(),duplicates=new Set();
    for(const row of data.access_points){
      const key=String(row?.chip_index)+':'+String(row?.ap_index);
      if(!Object.values(pairs).some(([chip,ap])=>key===chip+':'+ap))continue;
      if(duplicates.has(key))continue;
      if(rows.has(key)){rows.delete(key);duplicates.add(key);continue;}
      const f=row?.fields||{};
      rows.set(key,{AccessPointSwitchStatus:flag(f.AccessPointSwitchStatus),ApBroadcastDisabled:flag(f.ApBroadcastDisabled),
        ApIsolate:flag(f.ApIsolate),ApMaxStationNumber:maxClients(f.ApMaxStationNumber),
        AuthMode:typeof f.AuthMode==='string'&&authCodes.has(f.AuthMode)?f.AuthMode:null});
    }
    for(const key of duplicates)rows.delete(key);
    return rows;
  }
  function radios(data){
    if(data?.status!=='read_only'||data.radio_status!=='observed'||data.write_available!==false||!Array.isArray(data.radios)||data.radios.length>4)return new Map();
    const rows=new Map(),duplicates=new Set();
    for(const row of data.radios){
      const key=scalar(row?.fields?.ChipIndex);
      if(key!=='0'&&key!=='1')continue;
      if(duplicates.has(key))continue;
      if(rows.has(key)){rows.delete(key);duplicates.add(key);continue;}
      const f=row.fields;
      const raw=v=>{const s=scalar(v);return s!==null&&s.length<=16&&/^[a-zA-Z0-9_-]+$/.test(s)?s:null;};
      rows.set(key,{channel:raw(f.Channel),width:raw(f.BandWidth)});
    }
    for(const key of duplicates)rows.delete(key);
    return rows;
  }
  function cards(snapshot,apData,radioData){
    const ap=validFirmware(snapshot)?apRows(apData):new Map(),radio=validFirmware(snapshot)?radios(radioData):new Map();
    return WifiDraft.networks(snapshot).map(n=>{
      const [chip,point]=pairs[n.id],settings=ap.get(chip+':'+point)||{},r=radio.get(chip)||{};
      return {id:n.id,title:(point==='0'?'Glavna':'Gostujuća')+' · '+(chip==='0'?'2,4':'5')+' GHz',ssid:n.values.ssid,
        ap:{AccessPointSwitchStatus:settings.AccessPointSwitchStatus??null,ApBroadcastDisabled:settings.ApBroadcastDisabled??null,
          ApIsolate:settings.ApIsolate??null,ApMaxStationNumber:settings.ApMaxStationNumber??null,AuthMode:settings.AuthMode??null},
        radio:{channel:r.channel??null,width:r.width??null},hasAp:ap.has(chip+':'+point),hasRadio:radio.has(chip)};
    });
  }
  function planAp(snapshot,apData,id,proposed){
    if(!validFirmware(snapshot))throw Error('Firmware nije potvrđen kao A1 B08. Nacrt je blokiran.');
    if(!Object.hasOwn(pairs,id))throw Error('Nepoznata mreža.');
    if(!proposed||typeof proposed!=='object'||Array.isArray(proposed))throw Error('Nevaljani podaci za nacrt.');
    const [chip,point]=pairs[id],key=chip+':'+point,rows=apRows(apData);
    if(!rows.has(key))throw Error('Nema jednoznačnog izvornog B08 očitanja za mrežu.');
    const original=rows.get(key),changes=[];
    for(const [field,input] of Object.entries(proposed)){
      if(!apFields.includes(field))throw Error('Postavka nije dopuštena za lokalni nacrt.');
      const next=flagFields.has(field)?flag(input):maxClients(input);
      if(next===null)throw Error('Vrijednost nije dopušteni izvorni kod.');
      if(original[field]===null)throw Error('Trenutna vrijednost nije očitana.');
      if(next!==original[field])changes.push({field,read_key:field,before:original[field],after:next});
    }
    if(!changes.length)throw Error('Nema promjena za pregled.');
    return {mode:'local_draft_only',firmware:WifiDraft.expected,network:id,sample_time:snapshot.sample_time,
      changes,sendable:false,command:null,blockers:['Izvorni kodovi potvrđuju samo čitanje, ne mogućnost zapisivanja.',
        'Nisu verificirani servisni parametri, međusobne ovisnosti ni povratna provjera na B08.',
        'Nema odobrenog live testa; globalni Wi-Fi i guest prekidači mogu biti zasebni.']};
  }
  return {cards,planAp};
})();
if(typeof module!=='undefined')module.exports=WifiControl;
