const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const base=path.join(__dirname,'../zte_manager/src/static');
function setup(){
 const dom=new JSDOM(fs.readFileSync(path.join(base,'preview.html'),'utf8'),{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window,d=w.document,calls=[];
 w.TextEncoder=TextEncoder;w.AbortController=AbortController;
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
 let fail=false,httpError=false,invalid=false,name='Actual home',now=Date.now();w.Date.now=()=>now;
 const snap=()=>({version:'0.7.0',groups:{device:{cr_version:'CR_A1HRMF297DV1.0.0B08'},wifi:{wifi_chip1_ssid1_ssid:name,guest_switch:'0'},wifi_extra:{wifi_chip1_ssid2_ssid:'Guest private',wifi_chip1_ssid2_switch_onoff:'1'},signal:{lte_rsrp:'-90',Z_SINR:'0'}},fields:{wifi_chip1_ssid2_max_access_num:'8',m_HideSSID:'0'},clients:[],sources:{wifi:{status:'ok',rows:[{hostname:'Phone',mac_addr:'02:00:00:00:00:01',ip_addr:'192.168.1.2'}]},lan:{status:'unavailable',rows:[]}},sample_time:Math.floor(now/1000),errors:{}});
 w.fetch=async(url,options)=>{calls.push({url,method:options.method});if(fail)throw Error('offline');return {ok:!httpError,status:httpError?403:200,json:async()=>invalid?{}:url==='api/wifi_original_radio_read'?{status:'read_only',radio_status:'observed',switch_status:'observed_raw_code',radios:[{position:0,fields:{ChipIndex:'0',Channel:'11',BandWidth:'0',WirelessMode:'4',CountryCode:'HR',SSID:'HIDDEN_SECRET'}},{position:1,fields:{ChipIndex:'1',Channel:'0',BandWidth:'6',WirelessMode:'8',CountryCode:'HR'}}],module:{WiFiModuleSwitch:'1'},write_available:false}:url==='api/webui_wifi_modules'?{scan_scope:'wifi_modules',files:[{path:'/js/wifi/basic.js',sha256:'b'.repeat(64),wifi_literal_modules:['wifi/advance'],parameter_references:['wifi_chip1_channel']}],issues:[],write_verified:false}:url==='api/webui_evidence'?{files:[{path:'/index.html',sha256:'a'.repeat(64),command_references:[]}],issues:[],write_verified:false}:url==='api/preview_reservations'?{status:'empty_or_unsupported',rows:[]}:snap()};};
 const defaultFetch=w.fetch;
 w.fetch=(url,options)=>url==='api/wifi_original_ap_read'?(async()=>{
  calls.push({url,method:options.method});if(fail)throw Error('offline');
  return {ok:!httpError,status:httpError?403:200,json:async()=>invalid?{}:{
   status:'read_only',ap_status:'observed',write_available:false,
   access_points:[
    {chip_index:'0',ap_index:'0',fields:{AccessPointSwitchStatus:'1',ApBroadcastDisabled:'0',ApIsolate:'0',ApMaxStationNumber:'32',AuthMode:'WPA2PSK',SSID:'HIDDEN_SSID',Password:'HIDDEN_PASS'}},
    {chip_index:'1',ap_index:'1',fields:{AccessPointSwitchStatus:'0',ApIsolate:'1'}}
   ]
  }};
 })():defaultFetch(url,options);
 w.XMLHttpRequest=function(){throw Error('XHR forbidden')};w.WebSocket=function(){throw Error('WS forbidden')};
 w.eval(['network-insights.js','wifi-draft.js','wifi-control.js','preview.js'].map(f=>fs.readFileSync(path.join(base,f),'utf8')).join('\n'));
 return {w,d,calls,close:()=>w.close(),fail:()=>{fail=true},deny:()=>{httpError=true},invalid:()=>{invalid=true},rename:()=>{name='Changed home'},expire:()=>{now+=301000},click:s=>d.querySelector(s).click(),submit:()=>d.querySelector('#editForm').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true})),flush:()=>new Promise(r=>setTimeout(r,0))};
}
test('actual data draft escapes HTML and makes no write request',async()=>{const u=setup();try{await u.flush();u.click('[data-page="wifi"]');u.click('[data-edit="1:1"]');assert.equal(u.d.querySelector('[name="channel"]').disabled,true);u.d.querySelector('[name="ssid"]').value='<img src=x onerror=alert(1)>';u.submit();assert.equal(u.d.querySelector('#review img'),null);assert.match(u.d.querySelector('#review').textContent,/slanje blokirano/);assert.equal(u.calls.length,1);assert.match(u.d.querySelector('#content').textContent,/Actual home/);u.expire();u.submit();assert.match(u.d.querySelector('#formError').textContent,/Ponovno/);}finally{u.close()}});
test('evidence-backed guest panel shows raw flags without an extra router request',async()=>{
 const u=setup();try{await u.flush();u.click('[data-page="wifi"]');const output=u.d.querySelector('#content').textContent;
  assert.match(output,/Gostujuće mreže/);assert.match(output,/Guest private/);
  assert.match(output,/Globalni gostujući prekidač/);assert.match(output,/Radio 1 · gost maksimalno klijenata/);
  assert.match(output,/nisu ekvivalentni/);assert.deepEqual(u.calls,[{url:'api/preview_snapshot',method:'GET'}]);
 }finally{u.close()}
});
test('original B08 radio read only runs on click and renders safe exact radio codes',async()=>{
 const u=setup();try{await u.flush();u.click('[data-page="wifi"]');
  assert.equal(u.calls.length,1);assert.match(u.d.querySelector('#content').textContent,/Izvorni B08 radio podaci/);
  u.click('#readOriginalRadio');await u.flush();
  assert.deepEqual(u.calls.at(-1),{url:'api/wifi_original_radio_read',method:'GET'});
  const output=u.d.querySelector('#content').textContent;
  assert.match(output,/2,4 GHz · radio 0/);assert.match(output,/5 GHz · radio 1/);
  assert.match(output,/Wi-Fi modul \(izvorni kod\)/);assert.match(output,/Širina \(izvorni kod\)/);
  assert.ok(!output.includes('HIDDEN_SECRET'));
 }finally{u.close()}
});
test('original B08 access points are only read on click, no secret rendered or POST made',async()=>{
 const u=setup();try{await u.flush();u.click('[data-page="wifi"]');
  assert.equal(u.calls.length,1);assert.match(u.d.querySelector('#content').textContent,/Izvorne B08 pristupne točke/);
  u.click('#readOriginalAp');await u.flush();
  assert.deepEqual(u.calls.at(-1),{url:'api/wifi_original_ap_read',method:'GET'});
  const output=u.d.querySelector('#content').textContent;
  assert.match(output,/Glavna · 2,4 GHz/);assert.match(output,/Gostujuća · 5 GHz/);
  assert.match(output,/SSID prekidač \(kod\)/);assert.match(output,/Zaštita \(poznati kod\)/);
  assert.ok(!output.includes('HIDDEN_SSID'));assert.ok(!output.includes('HIDDEN_PASS'));
  assert.ok(u.calls.every(x=>x.method==='GET'));
  u.click('#refresh');await u.flush();
  assert.match(u.d.querySelector('#content').textContent,/Još nije očitano/);
 }finally{u.close()}
});
test('local SSID on/off draft never issues a router write',async()=>{
 const u=setup();try{
  await u.flush();u.click('[data-page="wifi"]');u.click('[data-edit="1:2"]');
  const select=u.d.querySelector('[name="enabled"]');assert.equal(select.disabled,false);
  assert.equal(select.value,'1');select.value='0';select.dispatchEvent(new u.w.Event('change',{bubbles:true}));
  u.submit();assert.match(u.d.querySelector('#review').textContent,/SSID prekidač/);
  assert.match(u.d.querySelector('#review').textContent,/slanje blokirano/);
  assert.deepEqual(u.calls,[{url:'api/preview_snapshot',method:'GET'}]);
 }finally{u.close()}
});
test('failed refresh locks drafts, keeps visible old data, sends only allowlisted reads',async()=>{const u=setup();try{await u.flush();u.click('[data-page="wifi"]');u.fail();u.click('#refresh');await u.flush();assert.match(u.d.querySelector('#notice').textContent,/stari podaci/);assert.equal(u.d.querySelector('[data-edit="1:1"]').disabled,true);assert.ok(u.calls.every(c=>c.method==='GET'&&c.url==='api/preview_snapshot'));}finally{u.close()}});
test('device search, source failures, comparisons and reservation uncertainty',async()=>{const u=setup();try{await u.flush();u.click('[data-page="devices"]');assert.match(u.d.querySelector('#content').textContent,/LAN popis nije dostupan/);const input=u.d.querySelector('#deviceQuery');input.value='missing';input.dispatchEvent(new u.w.Event('input',{bubbles:true}));assert.match(u.d.querySelector('#deviceTable').textContent,/Nema zapisa/);u.rename();u.click('#refresh');await u.flush();u.click('[data-page="changes"]');assert.match(u.d.querySelector('#content').textContent,/Changed home/);u.click('[data-page="reservations"]');u.click('#readReservations');await u.flush();assert.match(u.d.querySelector('#content').textContent,/stanje nije potvrđeno/);assert.ok(u.calls.every(c=>c.method==='GET'));}finally{u.close()}});

test('local device names persist only in browser with no network write',async()=>{const u=setup();try{await u.flush();u.click('[data-page="devices"]');u.click('#editNames');const input=u.d.querySelector('[data-alias]');input.value='Moj telefon';input.dispatchEvent(new u.w.Event('change',{bubbles:true}));assert.match(u.w.localStorage.getItem('zte-manager-device-names-v1'),/Moj telefon/);assert.equal(u.calls.length,1);assert.match(u.d.querySelector('#deviceTable').textContent,/Moj telefon/);}finally{u.close()}});

test('web UI evidence scan is explicit, GET-only and makes no support claim',async()=>{const u=setup();try{await u.flush();assert.equal(u.calls.length,1);u.click('[data-page="system"]');u.click('#inspectWebui');await u.flush();assert.match(u.d.querySelector('#content').textContent,/index.html/);assert.match(u.d.querySelector('#content').textContent,/Zapisivanje i dalje nije potvrđeno/);assert.deepEqual(u.calls.at(-1),{url:'api/webui_evidence',method:'GET'});}finally{u.close()}});

test('focused Wi-Fi module scan only performs allowlisted GET and shows static references',async()=>{
 const u=setup();try{
  await u.flush();u.click('[data-page="system"]');u.click('#inspectWifiModules');await u.flush();
  assert.match(u.d.querySelector('#content').textContent,/wifi\/advance/);
  assert.match(u.d.querySelector('#content').textContent,/wifi_chip1_channel/);
  assert.match(u.d.querySelector('#content').textContent,/Nije dokazano/);
  assert.deepEqual(u.calls,[{url:'api/preview_snapshot',method:'GET'},{url:'api/webui_wifi_modules',method:'GET'}]);
 }finally{u.close()}
});

test('iPhone-safe Wi-Fi summary copies only redacted local data without router requests',async()=>{
 const u=setup();try{
  await u.flush();const copied=[];
  Object.defineProperty(u.w.navigator,'clipboard',{value:{writeText:async value=>{copied.push(value)}}});
  u.click('[data-page="wifi"]');u.click('#copyWifiReport');await u.flush();
  assert.equal(copied.length,1);
  assert.equal(JSON.parse(copied[0]).kind,'wifi_read_compatibility');
  for(const value of ['Actual home','192.168.1.2','02:00:00:00:00:01'])assert.ok(!copied[0].includes(value));
  assert.match(u.d.querySelector('#notice').textContent,/kopiran/);
  assert.deepEqual(u.calls,[{url:'api/preview_snapshot',method:'GET'}]);
 }finally{u.close()}
});

test('Wi-Fi summary supports manual selection when iOS clipboard is unavailable',async()=>{
 const u=setup();try{
  await u.flush();u.click('[data-page="wifi"]');u.click('#copyWifiReport');await u.flush();
  const textarea=u.d.querySelector('#wifiReportText');
  assert.equal(textarea.hidden,false);
  assert.equal(JSON.parse(textarea.value).values_included,false);
  assert.match(u.d.querySelector('#notice').textContent,/ručno kopirati/);
  assert.equal(u.calls.length,1);
 }finally{u.close()}
});

for(const fault of ['deny','invalid'])test(`refresh ${fault} blocks old draft submission`,async()=>{const u=setup();try{await u.flush();u.click('[data-page="wifi"]');u.click('[data-edit="1:1"]');u.d.querySelector('[name="ssid"]').value='Offline test';u[fault]();u.click('#refresh');await u.flush();u.submit();assert.match(u.d.querySelector('#formError').textContent,/Ponovno/);assert.equal(u.d.querySelector('[data-edit="1:1"]').disabled,true);assert.ok(u.calls.every(c=>c.method==='GET'&&c.url==='api/preview_snapshot'));}finally{u.close()}});

test('Wi-Fi Control Center shows four exact mapped cards and groups diagnostics on iPhone',async()=>{
 const u=setup();try{await u.flush();u.click('[data-page="wifi"]');
  assert.equal(u.d.querySelectorAll('.wifi-network').length,4);
  assert.match(u.d.querySelector('.wifi-center').textContent,/Glavna · 2,4 GHz/);
  assert.match(u.d.querySelector('.wifi-center').textContent,/Gostujuća · 5 GHz/);
  assert.equal(u.d.querySelector('.wifi-advanced').open,false);
  assert.equal(u.d.querySelector('[data-editap="1:1"]').disabled,true);
  assert.deepEqual(u.calls,[{url:'api/preview_snapshot',method:'GET'}]);
 }finally{u.close()}
});

test('unified Wi-Fi details are explicit two GETs, sanitized, and AP changes remain a local-only draft',async()=>{
 const u=setup();try{await u.flush();u.click('[data-page="wifi"]');u.click('#readWifiCenter');await u.flush();await u.flush();
  assert.deepEqual(u.calls,[{url:'api/preview_snapshot',method:'GET'},{url:'api/wifi_original_radio_read',method:'GET'},{url:'api/wifi_original_ap_read',method:'GET'}]);
  const text=u.d.querySelector('.wifi-center').textContent;
  assert.match(text,/2,4 GHz/);assert.match(text,/Maksimalno klijenata/);
  assert.ok(!text.includes('HIDDEN_PASS'));assert.ok(!text.includes('HIDDEN_SSID'));assert.ok(!text.includes('HIDDEN_SECRET'));
  assert.equal(u.d.querySelector('[data-editap="1:1"]').disabled,false);
  u.click('[data-editap="1:1"]');
  const select=u.d.querySelector('[name="ApIsolate"]');select.value='1';select.dispatchEvent(new u.w.Event('change',{bubbles:true}));
  u.submit();assert.match(u.d.querySelector('#review').textContent,/ApIsolate/);
  assert.match(u.d.querySelector('#review').textContent,/slanje blokirano/);
  assert.equal(u.calls.length,3);assert.ok(u.calls.every(c=>c.method==='GET'));
  u.expire();u.submit();assert.match(u.d.querySelector('#formError').textContent,/Ponovno/);
 }finally{u.close()}
});

test('refresh invalidates AP evidence and disables any previously available local AP editor',async()=>{
 const u=setup();try{await u.flush();u.click('[data-page="wifi"]');u.click('#readWifiCenter');await u.flush();await u.flush();
  u.click('[data-editap="1:1"]');u.click('#refresh');await u.flush();
  assert.equal(u.d.querySelector('[data-editap="1:1"]').disabled,true);
  u.submit();assert.match(u.d.querySelector('#formError').textContent,/Ponovno/);
  assert.ok(u.calls.every(c=>c.method==='GET'));
 }finally{u.close()}
});
