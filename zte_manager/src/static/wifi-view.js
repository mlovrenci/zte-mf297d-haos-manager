'use strict';
// Pure view helpers: no router requests, persistence or inferred band mapping.
const WifiView = (() => {
  const numeric = value => typeof value !== 'boolean' && value !== null && value !== undefined && String(value).trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
  function select(clients, query='', index='', sort='name') {
    const q=query.trim().toLowerCase();
    return clients.filter(c => (!index || String(c.ssid_index??'')===index) &&
      ['hostname','ip_addr','mac_addr'].some(k=>String(c[k]??'').toLowerCase().includes(q)))
      .slice().sort((a,b)=>{
        if(sort==='rssi') {
          const x=numeric(a.rssi), y=numeric(b.rssi);
          if(x!==y)return x===null?1:y===null?-1:x-y;
        }
        const key=sort==='ip'?'ip_addr':'hostname';
        return String(a[key]??'').localeCompare(String(b[key]??''), 'hr', {numeric:true});
      });
  }
  function changes(before, after) {
    if(!before)return [];
    return Object.keys(after).filter(k=>Object.prototype.hasOwnProperty.call(before,k) && String(before[k])!==String(after[k]))
      .map(key=>({key,before:before[key],after:after[key]}));
  }
  return {select,changes};
})();
if(typeof module!=='undefined')module.exports=WifiView;
