const {test}=require('node:test'),assert=require('node:assert/strict');
const model=require('../zte_manager/src/static/wifi-draft.js');
const snapshot=()=>({groups:{device:{cr_version:model.expected},wifi:{wifi_chip1_ssid1_ssid:'Home',wifi_chip1_ssid1_switch_onoff:'0'}},fields:{wifi_chip1_channel:'0',wifi_chip1_bandwidth:'20'},sample_time:123});
test('missing stays unknown, zero is retained, no band association inferred',()=>{const n=model.networks(snapshot());assert.equal(n[0].values.enabled,'0');assert.equal(n[0].values.channel,'0');assert.equal(n[1].values.ssid,null);assert.equal(n[2].values.channel,null);});
test('preview does not mutate snapshot and never yields executable request',()=>{const s=snapshot(),before=JSON.stringify(s),p=model.plan(s,'1:1',{ssid:'New'});assert.equal(JSON.stringify(s),before);assert.equal(p.command,null);assert.equal(p.sendable,false);assert.equal(p.changes[0].before,'Home');assert.equal(p.sample_time,123);assert.ok(p.blockers.length);});
test('firmware mismatch, missing data, unsupported fields, control chars and UTF8 length fail closed',()=>{const s=snapshot();for(const values of [{ssid:'č'.repeat(17)},{ssid:'a\nb'},{ssid:' '},{security:'WPA3'},{channel:'-1'},{width:'banana'}])assert.throws(()=>model.plan(s,'1:1',values));assert.throws(()=>model.plan(s,'2:1',{ssid:'Test'}));s.groups.device.cr_version='unknown';assert.throws(()=>model.plan(s,'1:1',{ssid:'Test'}));});
test('unchanged and unknown target fail; channel range is explicitly not evidence',()=>{const s=snapshot();assert.throws(()=>model.plan(s,'1:1',{ssid:'Home'}));assert.throws(()=>model.plan(s,'bad',{ssid:'New'}));const p=model.plan(s,'1:1',{channel:'999'});assert.equal(p.sendable,false);assert.ok(p.blockers.some(x=>x.includes('kanali')));});
test('SSID on/off uses only the exact read 0/1 values and never sends',()=>{
 const s=snapshot(),original=JSON.stringify(s),p=model.plan(s,'1:1',{enabled:'1'});
 assert.deepEqual(p.changes,[{field:'enabled',read_key:'wifi_chip1_ssid1_switch_onoff',before:'0',after:'1'}]);
 assert.equal(p.command,null);assert.equal(p.sendable,false);assert.equal(JSON.stringify(s),original);
 for(const value of ['ON','true','2','',null])assert.throws(()=>model.plan(s,'1:1',{enabled:value}));
 assert.throws(()=>model.plan(s,'1:1',{enabled:'0'}));
 s.groups.wifi.wifi_chip1_ssid1_switch_onoff='unavailable';
 assert.throws(()=>model.plan(s,'1:1',{enabled:'1'}));
});
test('security labels are exact-code-only and do not infer unknown or guest modes',()=>{
 assert.match(model.securityLabel('WPA2PSK'),/WPA2-PSK/);
 assert.match(model.securityLabel('WPAPSKWPA2PSK'),/miješani/);
 assert.match(model.securityLabel('WPA3PSK'),/WPA3-PSK/);
 assert.match(model.securityLabel('toString'),/nije mapiran/);
 assert.match(model.securityLabel(null),/Nije očitano/);
 assert.match(model.securityLabel('private-unknown'),/nije mapiran/);
});
