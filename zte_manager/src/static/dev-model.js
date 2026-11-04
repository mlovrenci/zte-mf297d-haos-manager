'use strict';
// Deliberately independent of RouterClient, fetch, storage and MQTT.
const ZteDemo = (() => {
  const clone=x=>JSON.parse(JSON.stringify(x));
  const seed={
    wifi:[{id:'radio24',name:'Glavna · 2,4 GHz',ssid:'Demo Home',enabled:true,channel:'auto',width:'20',security:'WPA2',hidden:false},{id:'radio5',name:'Glavna · 5 GHz',ssid:'Demo Home 5G',enabled:true,channel:'36',width:'80',security:'WPA2',hidden:false},{id:'guest',name:'Gosti · 2,4 GHz',ssid:'Demo Guests',enabled:false,channel:'auto',width:'20',security:'WPA2',hidden:false,isolation:true}],
    steering:{enabled:false},
    lan:{gateway:'192.168.50.1',mask:'255.255.255.0',dhcp:true,start:'192.168.50.100',end:'192.168.50.200',lease:24},
    dns:{mode:'auto',primary:'',secondary:''},
    devices:[{id:'tablet',name:'Demo tablet',ip:'192.168.50.101',mac:'02:00:00:00:00:01',band:'2,4 GHz',rssi:-58},{id:'phone',name:'Demo telefon',ip:'192.168.50.102',mac:'02:00:00:00:00:02',band:'5 GHz',rssi:-46},{id:'tv',name:'Demo TV',ip:'192.168.50.103',mac:'02:00:00:00:00:03',band:'5 GHz',rssi:-67},{id:'hub',name:'Demo hub',ip:'192.168.50.104',mac:'02:00:00:00:00:04',band:'LAN',rssi:null}],
    reservations:[{id:'hub',name:'Demo hub',ip:'192.168.50.104',mac:'02:00:00:00:00:04'}],audit:[]
  };
  const ip=x=>{const p=String(x).split('.');return p.length===4&&p.every(v=>/^\d{1,3}$/.test(v)&&Number(v)<=255)&&p.every(v=>v==='0'||!v.startsWith('0'));};
  const num=x=>String(x).split('.').reduce((a,v)=>a*256+Number(v),0);
  function validate(s){
    for(const w of s.wifi){
      if(!w.ssid.trim()||new TextEncoder().encode(w.ssid).length>32)throw Error('SSID mora imati 1–32 bajta.');
      const channels=w.id==='radio5'?['auto','36','40','44','48']:['auto',...Array.from({length:13},(_,i)=>String(i+1))];
      if(!channels.includes(w.channel))throw Error('Odaberi kanal iz ponuđenog popisa.');
      if(!(w.id==='radio5'?['20','40','80']:['20','40']).includes(w.width))throw Error('Neispravna širina kanala.');
      if(!['WPA2','WPA2/WPA3'].includes(w.security))throw Error('Neispravna zaštita mreže.');
    }
    const l=s.lan;
    if(![l.gateway,l.start,l.end].every(ip)||l.mask!=='255.255.255.0')throw Error('Simulator podržava valjane IPv4 adrese u /24 mreži.');
    const prefix=l.gateway.split('.').slice(0,3).join('.')+'.';
    if(!l.start.startsWith(prefix)||!l.end.startsWith(prefix)||num(l.start)>num(l.end)||[l.start,l.end,l.gateway].some(x=>['0','255'].includes(x.split('.').pop())))throw Error('DHCP raspon mora biti u istoj /24 mreži, bez mrežne i broadcast adrese.');
    if(num(l.gateway)>=num(l.start)&&num(l.gateway)<=num(l.end))throw Error('Gateway ne smije biti u DHCP rasponu.');
    if(!Number.isInteger(l.lease)||l.lease<1||l.lease>168)throw Error('Lease mora biti 1–168 sati.');
    if(s.dns.mode==='manual'&&(!ip(s.dns.primary)||(s.dns.secondary&&!ip(s.dns.secondary))))throw Error('Upiši valjanu DNS adresu.');
    if(s.reservations.length>10)throw Error('Najviše 10 rezervacija.');
    const ips=new Set(),macs=new Set();
    for(const r of s.reservations){
      if(!r.name.trim()||r.name.length>32)throw Error('Naziv mora imati 1–32 znaka.');
      if(!ip(r.ip)||!r.ip.startsWith(prefix)||r.ip===l.gateway||['0','255'].includes(r.ip.split('.').pop()))throw Error('Rezervacija mora biti adresa uređaja u istoj /24 mreži.');
      if(ips.has(r.ip)||macs.has(r.mac.toLowerCase()))throw Error('IP ili MAC već je rezerviran.');
      if(s.devices.some(d=>d.ip===r.ip&&d.mac.toLowerCase()!==r.mac.toLowerCase()))throw Error('IP već koristi drugi demo uređaj.');
      ips.add(r.ip);macs.add(r.mac.toLowerCase());
    }
    return s;
  }
  function create(){
    let state=clone(seed),revision=0;
    return {
      read:()=>clone(state),
      plan(kind,id,values){
        const next=clone(state);let before;
        if(kind==='wifi'){const i=next.wifi.findIndex(x=>x.id===id);if(i<0)throw Error('Mreža nije pronađena.');before=clone(next.wifi[i]);Object.assign(next.wifi[i],values);}
        else if(['lan','dns','steering'].includes(kind)){before=clone(next[kind]);Object.assign(next[kind],values);}
        else if(kind==='device'){const d=next.devices.find(x=>x.id===id);if(!d)throw Error('Uređaj nije pronađen.');before={name:d.name};if(!String(values.name||'').trim()||values.name.length>32)throw Error('Naziv mora imati 1–32 znaka.');d.name=values.name;}
        else if(kind==='reservation'){const d=next.devices.find(x=>x.id===id);if(!d)throw Error('Uređaj nije pronađen.');before=clone(next.reservations.find(x=>x.id===id)||{});next.reservations=next.reservations.filter(x=>x.id!==id);if(values.enabled)next.reservations.push({id,mac:d.mac,name:values.name,ip:values.ip});}
        else throw Error('Nepoznata radnja.');
        validate(next);
        return {kind,id,values:clone(values),before,next,revision};
      },
      apply(plan,scenario='normal'){
        if(plan.revision!==revision)throw Error('Podaci su se promijenili. Ponovno pripremi promjenu.');
        if(scenario==='timeout')throw Error('Simulacija: router nije odgovorio. Nema potvrde primjene.');
        if(scenario==='reject')throw Error('Simulacija: firmware je odbio spremanje.');
        // Rebuild and validate rather than trust a modified client-side plan.
        const fresh=this.plan(plan.kind,plan.id,plan.values);
        state=fresh.next;revision++;
        state.audit.unshift({time:new Date().toISOString(),action:plan.kind,target:plan.id||plan.kind});state.audit=state.audit.slice(0,40);
        return this.read();
      },
      reset(){state=clone(seed);revision++;return this.read();}
    };
  }
  return {create,validate};
})();
if(typeof module!=='undefined')module.exports=ZteDemo;
