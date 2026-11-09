const {test}=require('node:test'),assert=require('node:assert/strict');
global.WifiDraft=require('../zte_manager/src/static/wifi-draft.js');
const {cards,planAp}=require('../zte_manager/src/static/wifi-control.js');
const snapshot=()=>({groups:{device:{cr_version:WifiDraft.expected},wifi:{wifi_chip1_ssid1_ssid:'Private home'}},sample_time:456});
const ap=()=>({status:'read_only',ap_status:'observed',write_available:false,access_points:[
 {chip_index:'0',ap_index:'0',fields:{AccessPointSwitchStatus:'1',ApBroadcastDisabled:'0',ApIsolate:'0',ApMaxStationNumber:'64',AuthMode:'WPA2PSK',SSID:'NEVER_SHOW',Password:'NEVER_SHOW_PASS'}},
 {chip_index:'1',ap_index:'1',fields:{AccessPointSwitchStatus:'0',ApBroadcastDisabled:'1',ApIsolate:'1',ApMaxStationNumber:'8'}}
]});
const radio=()=>({status:'read_only',radio_status:'observed',write_available:false,radios:[{fields:{ChipIndex:'0',Channel:'11',BandWidth:'0'}},{fields:{ChipIndex:'1',Channel:'0',BandWidth:'6'}}]});
test('maps four exact firmware main/guest pairs without merging bands',()=>{
 const c=cards(snapshot(),ap(),radio());assert.deepEqual(c.map(r=>r.title),['Glavna · 2,4 GHz','Gostujuća · 2,4 GHz','Glavna · 5 GHz','Gostujuća · 5 GHz']);
 assert.equal(c[0].ap.AccessPointSwitchStatus,'1');assert.equal(c[0].radio.channel,'11');
 assert.equal(c[1].ap.AccessPointSwitchStatus,null);assert.equal(c[2].ap.ApIsolate,null);
 assert.equal(c[3].ap.ApBroadcastDisabled,'1');assert.equal(c[3].radio.channel,'0');
 assert.ok(!JSON.stringify(c).includes('NEVER_SHOW'));assert.ok(!JSON.stringify(c).includes('NEVER_SHOW_PASS'));
});
test('local AP before-to-after plan has no command or send capability',()=>{
 const s=snapshot(),a=ap(),before=JSON.stringify([s,a]);
 const p=planAp(s,a,'1:1',{AccessPointSwitchStatus:'0',ApMaxStationNumber:'32'});
 assert.deepEqual(p.changes,[{field:'AccessPointSwitchStatus',read_key:'AccessPointSwitchStatus',before:'1',after:'0'},
 {field:'ApMaxStationNumber',read_key:'ApMaxStationNumber',before:'64',after:'32'}]);
 assert.equal(p.command,null);assert.equal(p.sendable,false);assert.equal(p.mode,'local_draft_only');assert.equal(p.sample_time,456);
 assert.equal(JSON.stringify([s,a]),before);
});
test('unknowns, duplicate pairs and invalid read shape do not infer status',()=>{
 const a=ap();a.access_points.push({...a.access_points[0]});
 assert.equal(cards(snapshot(),a,radio())[0].hasAp,false);
 assert.throws(()=>planAp(snapshot(),a,'1:1',{ApIsolate:'1'}));
 a.write_available=true;assert.equal(cards(snapshot(),a,radio())[3].hasAp,false);
 assert.throws(()=>planAp(snapshot(),a,'2:2',{ApIsolate:'0'}));
 const s=snapshot();s.groups.device.cr_version='OTHER';assert.equal(cards(s,ap(),radio())[0].hasAp,false);
 assert.throws(()=>planAp(s,ap(),'1:1',{ApIsolate:'1'}));
});
test('invalid, unknown, and suspicious AP values are rejected',()=>{
 for(const [key,value] of [['Password','new'],['ApIsolate','ON'],['ApBroadcastDisabled','2'],['ApMaxStationNumber','1025'],['ApMaxStationNumber','1e3'],['ApMaxStationNumber','-1']])
  assert.throws(()=>planAp(snapshot(),ap(),'1:1',{[key]:value}));
 assert.throws(()=>planAp(snapshot(),ap(),'bad',{ApIsolate:'1'}));
 assert.throws(()=>planAp(snapshot(),ap(),'1:1',{ApIsolate:'0'}));
 const a=ap();a.access_points[0].fields.ApIsolate='unknown';assert.throws(()=>planAp(snapshot(),a,'1:1',{ApIsolate:'1'}));
 const r=radio();r.radios[0].fields.Channel='<img src=x>';assert.equal(cards(snapshot(),ap(),r)[0].radio.channel,null);
});
