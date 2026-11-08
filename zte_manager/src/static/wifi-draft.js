'use strict';
// Read-backed local drafts only. No executable Goform commands or storage.
const WifiDraft = (() => {
  const expected='CR_A1HRMF297DV1.0.0B08';
  const scalar=v=>(typeof v==='string'||typeof v==='number')&&String(v).trim()!==''?String(v):null;
  const securityNames=Object.freeze({
    WPA2PSK:'WPA2-PSK (izvorni kod)',
    WPAPSKWPA2PSK:'WPA/WPA2 miješani način (izvorni kod)',
    WPA3PSK:'WPA3-PSK (izvorni kod)',
    WPA2PSKWPA3PSK:'WPA2/WPA3 miješani način (izvorni kod)',
    WPAPSK:'WPA-PSK (izvorni kod)',
    OPEN:'Otvoreno, prema izvornom kodu',
    NONE:'Bez zaštite, prema izvornom kodu'
  });
  const securityLabel=code=>code===null||code===undefined||code===''?'Nije očitano':Object.hasOwn(securityNames,String(code))?securityNames[String(code)]:'Kod nije mapiran; provjeri izvornu vrijednost';
  const editableEnabled=code=>code==='0'||code==='1';
  function networks(snapshot){
    const g=snapshot.groups||{},f={...g.wifi,...g.wifi_extra,...snapshot.fields};
    return [1,2].flatMap(chip=>[1,2].map(ssid=>{
      const prefix=`wifi_chip${chip}_ssid${ssid}_`;
      return {id:`${chip}:${ssid}`,title:`${ssid===1?'Glavna':'Gostujuća'} · radio ${chip}`,bandNote:chip===1?'Uobičajeno 2,4 GHz; mapiranje treba potvrditi':'Uobičajeno 5 GHz; mapiranje treba potvrditi',
        values:{ssid:scalar(f[prefix+'ssid']),enabled:scalar(f[prefix+'switch_onoff']),security:scalar(f[prefix+'auth_mode']),channel:scalar(f[`wifi_chip${chip}_channel`]),width:scalar(f[`wifi_chip${chip}_bandwidth`])},
        keys:{ssid:prefix+'ssid',enabled:prefix+'switch_onoff',security:prefix+'auth_mode',channel:`wifi_chip${chip}_channel`,width:`wifi_chip${chip}_bandwidth`}};
    }));
  }
  function plan(snapshot,id,values){
    if(snapshot.groups?.device?.cr_version!==expected)throw Error('Firmware nije potvrđen kao A1 B08. Nacrt je blokiran.');
    const n=networks(snapshot).find(n=>n.id===id);if(!n)throw Error('Nepoznata mreža.');
    const changes=[];
    for(const [key,raw] of Object.entries(values)){
      if(!['ssid','enabled','channel','width'].includes(key))throw Error('Ova postavka još nema editor.');
      const value=String(raw);
      if(n.values[key]===null)throw Error('Trenutna vrijednost nije očitana; promjena je blokirana.');
      if(key==='enabled'&&(!editableEnabled(n.values.enabled)||!editableEnabled(value)))throw Error('Prekidač podržava samo potvrđene kodove 0 i 1; promjena je blokirana.');
      if(value===n.values[key])continue;
      if(key==='ssid'&&(!value.trim()||new TextEncoder().encode(value).length>32||/[\x00-\x1f\x7f]/.test(value)))throw Error('SSID mora imati 1–32 bajta, bez kontrolnih znakova.');
      // Syntax validation only: no regional/channel support inferred from this range.
      if(key==='channel'&&!/^(auto|0|[1-9][0-9]{0,2})$/.test(value))throw Error('Kanal: auto ili cijeli broj do tri znamenke. Podrška kanala nije potvrđena.');
      if(key==='width'&&!['20','40','80','160','auto'].includes(value))throw Error('Upiši 20, 40, 80, 160 ili auto. Podrška širine nije potvrđena.');
      changes.push({field:key,read_key:n.keys[key],before:n.values[key],after:value});
    }
    if(!changes.length)throw Error('Nema promjena za pregled.');
    return {mode:'local_draft_only',firmware:expected,network:id,sample_time:snapshot.sample_time,changes,sendable:false,command:null,
      blockers:['Struktura servisnih naredbi je pregledana; povezivanje UI pozivatelja s ovim radiom/SSID-om još nije potvrđeno.','Nisu potvrđeni dopušteni kanali/širine, obavezna polja ni utjecaj na ostale mreže.','Per-SSID prekidač i globalni guest status možda nisu ekvivalentni; ovaj nacrt ne uključuje ni jednu stvarnu promjenu.','Nema odobrenog live testa ni potvrde ponovnim očitanjem.']};
  }
  return {networks,plan,expected,securityLabel,editableEnabled};
})();
if(typeof module!=='undefined')module.exports=WifiDraft;
