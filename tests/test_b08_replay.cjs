const {test}=require('node:test'),assert=require('node:assert/strict');
const model=require('../zte_manager/src/static/wifi-draft.js');
const captured=require('./fixtures/b08-read-redacted.json');
test('redacted actual B08 snapshot supports SSID review without inferred radio parameters',()=>{
 const s=structuredClone(captured),before=JSON.stringify(s);
 const networks=model.networks(s);assert.equal(networks.length,4);
 for(const n of networks){
  assert.equal(n.values.channel,null);assert.equal(n.values.width,null);
  if(n.values.ssid!==null){const p=model.plan(s,n.id,{ssid:'Offline test'});
   assert.equal(p.sendable,false);assert.equal(p.command,null);
   assert.equal(p.changes[0].before,n.values.ssid);assert.equal(p.changes[0].after,'Offline test');}
  for(const change of [{channel:'6'},{width:'40'}])assert.throws(()=>model.plan(s,n.id,change));
 }
 assert.equal(JSON.stringify(s),before);
});
test('actual snapshot replay rejects invalid SSIDs and unverified security edits',()=>{
 for(const change of [{ssid:''},{ssid:'x'.repeat(33)},{ssid:'č'.repeat(17)},{ssid:'a\u0000b'},{security:'WPA3'}])
  assert.throws(()=>model.plan(captured,'1:1',change));
});
