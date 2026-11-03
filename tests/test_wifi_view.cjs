const test=require('node:test');
const assert=require('node:assert/strict');
const view=require('../zte_manager/src/static/wifi-view.js');
test('filters SSID 0 and searches without changing original order',()=>{
  const rows=[{hostname:'Yuka',ssid_index:0,ip_addr:'192.168.1.20'},{hostname:'TV',ssid_index:1,ip_addr:'192.168.1.9'}];
  assert.deepEqual(view.select(rows,'YUK','0'),[rows[0]]);
  assert.deepEqual(view.select(rows,'','', 'ip'),[rows[1],rows[0]]);
  assert.equal(rows[0].hostname,'Yuka');
});
test('RSSI sorting preserves zero and puts unknown/boolean/blank values last',()=>{
  const rows=[{rssi:null},{rssi:'-80'},{rssi:''},{rssi:0},{rssi:-50},{rssi:true},{rssi:'unknown'}];
  assert.deepEqual(view.select(rows,'','','rssi').slice(0,3).map(c=>c.rssi),['-80',-50,0]);
});
test('missing fields and numeric representations are not configuration changes',()=>{
  assert.deepEqual(view.changes(null,{channel:1}),[]);
  assert.deepEqual(view.changes({channel:1,width:20},{channel:'1'}),[]);
  assert.deepEqual(view.changes({channel:1},{channel:6}),[{key:'channel',before:1,after:6}]);
  assert.deepEqual(view.changes({}, {constructor:'untrusted'}),[]);
});
