'use strict';
const $=id=>document.getElementById(id);
const escapeHTML=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={cr_version:'Firmware',wa_inner_version:'Interna verzija',hardware_version:'Hardver',web_version:'WebUI',Language:'Jezik',modem_main_state:'Modem',ppp_status:'Internet',network_type:'Mobilna mreža',network_provider:'Operater',wan_ipaddr:'WAN IP',pin_status:'SIM',wan_apn:'APN',pdp_type:'PDP',apn_interface_version:'APN API',opms_wan_mode:'WAN način',BearerPreference:'Mrežni način',dial_mode:'Dial mode',simcard_roam:'Roaming',lte_rsrp:'RSRP',lte_rsrq:'RSRQ',lte_rssi:'RSSI',lte_snr:'SINR',Z_SINR:'ZTE SINR',wan_active_band:'LTE band',wan_active_channel:'Kanal',wan_lte_ca:'LTE agregacija',lte_ca_pcell_band:'P-Cell band',lte_ca_scell_band:'S-Cell band',cell_id:'Cell ID',lan_ipaddr:'LAN IP',lan_netmask:'Maska',router_mode_gateway:'Gateway',LocalDomain:'Lokalna domena',mac_address:'LAN MAC',dhcpEnabled:'DHCP status',dhcp_enable:'DHCP alt.',dhcpStart:'Početak poola',dhcpEnd:'Kraj poola',dhcpLease_hour:'Lease (sati)',dhcpLeaseTime:'Lease',dhcp_lease:'Lease (alt.)',dhcpLease:'DHCP lease',dns_mode:'WAN DNS način',prefer_dns_manual:'WAN primarni DNS',standby_dns_manual:'WAN sekundarni DNS',dns_primary_dns:'Primarni DNS',dns_secondary_dns:'Sekundarni DNS',wifi_onoff_state:'Wi-Fi stanje',wifi_chip1_ssid1_ssid:'SSID 2,4 GHz',wifi_chip2_ssid1_ssid:'SSID 5 GHz',wifi_chip1_ssid1_auth_mode:'2,4 GHz zaštita',wifi_chip2_ssid1_auth_mode:'5 GHz zaštita',wifi_chip1_ssid1_switch_onoff:'2,4 GHz uključen',wifi_chip2_ssid1_switch_onoff:'5 GHz uključen',wifi_chip1_ssid2_ssid:'Guest 2,4 GHz',wifi_chip2_ssid2_ssid:'Guest 5 GHz',wifi_chip1_ssid2_switch_onoff:'Guest 2,4 GHz aktivan',wifi_chip2_ssid2_switch_onoff:'Guest 5 GHz aktivan',guest_switch:'Gostujući Wi-Fi',wifi_chip1_ssid1_access_sta_num:'Klijenti 2,4 GHz',wifi_chip2_ssid1_access_sta_num:'Klijenti 5 GHz',realtime_rx_thrpt:'Download (API units)',realtime_tx_thrpt:'Upload (API units)',realtime_rx_thrp:'Download (stari API naziv)',realtime_tx_thrp:'Upload (stari API naziv)',realtime_rx_bytes:'RX bajtovi',realtime_tx_bytes:'TX bajtovi',monthly_rx_bytes:'Mjesečni RX',monthly_tx_bytes:'Mjesečni TX',total_rx_bytes:'Ukupni RX',total_tx_bytes:'Ukupni TX',monthly_time:'Mjesečno vrijeme',upnp_enable:'UPnP',upnp_status:'UPnP status',dmz_switch:'DMZ aktivan',dmz_ip_address:'DMZ IP',nat_type:'NAT tip',port_mapping_enable:'Port forwarding',ipv6_enable:'IPv6',ipv6_wan_status:'IPv6 WAN',rj45_state:'LAN port',uptime:'Uptime',sys_uptime:'Sistem uptime',system_uptime:'Uptime',router_uptime:'Uptime',sntp_timezone:'Vremenska zona',sms_data_total:'SMS broj'};
Object.assign(labels,{
  wifi_lbd_enable:'Band steering (API)',wifi_dfs_status:'DFS stanje (API)',
  wifi_eacs_enable:'Automatski odabir kanala (API)',wifi_enable:'Wi-Fi radio (API)',
  wifi_5g_enable:'5 GHz radio (API)',wifi_chip1_channel:'2,4 GHz kanal (kandidat)',
  wifi_chip2_channel:'5 GHz kanal (kandidat)',wifi_chip1_bandwidth:'2,4 GHz širina kanala (API)',
  wifi_chip2_bandwidth:'5 GHz širina kanala (API)',
  wifi_chip1_ssid2_access_sta_num:'Guest 2,4 GHz klijenti',
  wifi_chip2_ssid2_access_sta_num:'Guest 5 GHz klijenti'
});
let state=null,meta=null,plan=null,clientList=[],wiredList=[],activeHours=24,lastError=null;
function notice(s,bad=false){$('message').textContent=s;$('message').classList.toggle('warning',bad)}
async function req(path,data){const headers=data?{'Content-Type':'application/json','X-ZTE-Action':'yes','X-ZTE-CSRF':meta?.csrf||''}:{Accept:'application/json'};const r=await fetch('api/'+path,{method:data?'POST':'GET',cache:'no-store',credentials:'same-origin',headers,body:data?JSON.stringify(data):undefined});let x;try{x=await r.json()}catch{throw Error('ZTE Manager nije vratio JSON')};if(!r.ok)throw Error(x.error||'HTTP '+r.status);return x}
function tiles(id,obj){if(!$(id))return;let entries=Object.entries(obj||{}).filter(([,v])=>v!==''&&v!==null&&v!==undefined);$(id).innerHTML=entries.length?entries.map(([k,v])=>`<article class="tile"><div class="key">${escapeHTML(labels[k]||k)}</div><div class="value">${escapeHTML(typeof v==='object'?JSON.stringify(v):v)}</div></article>`).join(''):'<p class="hint">Ova polja firmware nije vratio. Ne znači nužno da funkcija ne postoji.</p>'}
function hero(k,v,caption=''){return `<article class="hero"><small>${escapeHTML(k)}</small><strong>${escapeHTML(v||'—')}</strong>${caption?`<em>${escapeHTML(caption)}</em>`:''}</article>`}
function renderHero(g){const w=g.internet||{},s=g.signal||{},d=g.dhcp||{},wf=g.wifi||{};$('heroCards').innerHTML=hero('WAN',w.ppp_status||'—',w.network_provider||'')+hero('RSRP',s.lte_rsrp?`${s.lte_rsrp} dBm`:'—',s.wan_active_band||'')+hero('Wi-Fi',wf.wifi_onoff_state??'—',wf.wifi_chip1_ssid1_ssid||'')+hero('DHCP',String(d.dhcpEnabled)==='1'?'ON':String(d.dhcpEnabled)==='0'?'OFF':'Nepoznato',d.dhcpStart&&d.dhcpEnd?`${d.dhcpStart} – ${d.dhcpEnd}`:'')}
function caps(c){const names={status:'Status', '4g':'Mobilna veza',signal:'LTE signal',lan:'LAN',dhcp:'DHCP',dns:'DNS',wifi:'Wi-Fi',wifi_extra:'Wi-Fi Advanced',traffic:'Promet',nat:'NAT / IPv6',system:'Sustav'};$('caps').innerHTML=Object.entries(c||{}).map(([k,v])=>`<div class="cap ${v.status==='available'?'available':v.status==='partial'?'partial':'missing'}"><strong>${escapeHTML(names[k]||k)}</strong><br><i>${v.status==='available'?'Read dostupno':v.status==='partial'?'Djelomično dostupno':'Nema podatka'}</i><small>${escapeHTML((v.detail? v.detail+' · ':'')+((v.fields||[]).join(', ')||'Nije potvrđeno'))}</small></div>`).join('')}
async function refresh(){notice('Očitavam status i konfiguraciju…');try{meta=await req('meta');const result=await req('state');state=result.groups;const g=state;tiles('overview',{...g.device,...g.internet});tiles('signal',g.signal);tiles('internetinfo',g.internet);tiles('radioinfo',g.signal);tiles('trafficinfo',g.traffic);tiles('dhcpinfo',{...g.lan,...g.dhcp});tiles('dnsinfo',g.dns);tiles('wifiinfo',g.wifi);tiles('wifiExtra',g.wifi_extra);tiles('firewallinfo',{...g.network_extra});tiles('systeminfo',g.device);tiles('systemextra',g.system_extra);renderHero(g);caps(result.capabilities||{});
renderWriteMode();
$('wanMode').value=['auto_dial','manual_dial'].includes(g.internet?.ConnectionMode) ? g.internet.ConnectionMode : 'auto_dial';
$('upnpEnable').checked = String(g.network_extra?.upnp_enable || g.network_extra?.upnp_setting_option)==='1';
$('dmzEnable').checked = String(g.network_extra?.DMZEnable || g.network_extra?.dmz_switch)==='1';
$('dmzAddress').value = g.network_extra?.DMZIPAddress || g.network_extra?.dmz_ip_address || '';
$('badge').textContent=Object.keys(result.errors||{}).length?'Djelomično':'Povezano';$('badge').className='pill ok';$('lastUpdated').textContent=new Date().toLocaleTimeString('hr-HR');$('poolStart').value=g.dhcp?.dhcpStart||'';$('poolEnd').value=g.dhcp?.dhcpEnd||'';$('lease').value=g.dhcp?.dhcpLease_hour||24;$('dhcpEnable').checked=String(g.dhcp?.dhcpEnabled)==='1';$('dnsMode').value=g.dns?.dns_mode==='manual'?'manual':'auto';$('dnsPrimary').value=g.dns?.prefer_dns_manual||'';$('dnsSecondary').value=g.dns?.standby_dns_manual||'';$('wifiPower').checked=String(g.wifi?.wifi_onoff_state)==='1'||String(g.wifi?.wifi_onoff_state).toLowerCase()==='on';$('ssid').value=g.wifi?.wifi_chip1_ssid1_ssid||'';if(['NETWORK_auto','Only_LTE'].includes(g.internet?.BearerPreference))$('bearer').value=g.internet.BearerPreference;
notice(`ZTE ${meta.router_ip} · firmware ${g.device?.cr_version||'nije očitan'} · ${meta.write_enabled&&meta.experimental_writes?'Write omogućava pripremu, promjene nisu potvrđene':'Write zaključan'}${Object.keys(result.errors||{}).length?' · API greške: '+Object.keys(result.errors).join(', '):''}`);await history(activeHours)}catch(e){$('badge').textContent='Nije dostupno';$('badge').className='pill err';notice(e.message,true)}}
function chart(series,key,unit){if(!series.length||!series.some(x=>Number.isFinite(x[key])))return '<p class="hint">Nema uzoraka. Uključi periodični monitoring u postavkama App-a ili ručno osvježavaj.</p>';let pts=series.filter(x=>Number.isFinite(x[key]));let low=Math.min(...pts.map(x=>x[key])),hi=Math.max(...pts.map(x=>x[key]));if(hi===low)hi=low+1;const W=800,H=180,L=36,T=12,R=12,B=25;let first=pts[0].ts,last=pts[pts.length-1].ts;if(last===first)last=first+1;let coords=pts.map(v=>[(L+(v.ts-first)/(last-first)*(W-L-R)),(T+(hi-v[key])/(hi-low)*(H-T-B))]);let line=coords.map((v,i)=>(i?'L':'M')+v[0].toFixed(1)+','+v[1].toFixed(1)).join(' ');return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Graf povijesti"><line x1="${L}" y1="${T}" x2="${W-R}" y2="${T}" stroke="#37536e" stroke-dasharray="3 5"/><line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="#37536e"/><path d="${line}" fill="none" stroke="#83c6ff" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/></svg><div class="chart-meta"><span>${escapeHTML(low.toFixed(1)+' '+unit)}</span><span>${pts.length} uzoraka</span><span>${escapeHTML(hi.toFixed(1)+' '+unit)}</span></div>`}
async function history(hours){try{const r=await req('history?hours='+hours);$('chartBox').innerHTML=chart(r.samples,'rsrp','dBm');$('speedChart').innerHTML=chart(r.samples,'down','API units');if(!r.enabled){const m='<p class="hint">Kontinuirani monitoring je isključen u postavkama. Graf će se puniti tek nakon uključivanja.</p>';$('chartBox').insertAdjacentHTML('beforeend',m)}}catch(e){$('chartBox').textContent=e.message;$('speedChart').textContent=e.message}}
function prepareStatic(action,values){
  notice('Provjeravam rezervaciju '+action+'…');
  req('static_prepare',{action,values}).then(p=>{
    plan={...p,kind:'static'};$('planText').textContent=p.summary;
    $('confirmPhrase').textContent=p.confirm;$('confirmInput').value='';
    $('confirmDialog').classList.remove('hidden');$('confirmInput').focus();
    notice('Nije ništa zapisano; potvrdi odabranu MAC-IP promjenu.');
  }).catch(e=>notice(e.message,true));
}
$('reservationAddForm').onsubmit=e=>{
  e.preventDefault();
  prepareStatic('add',{hostname:$('staticName').value,mac:$('staticMac').value,
    ip:$('staticIp').value,domain:$('staticDomain').value});
};
function prepare(op,values){notice('Pripremam promjenu '+op+'…');req('prepare',{operation:op,values}).then(p=>{plan=p;$('planText').textContent=p.summary;$('confirmPhrase').textContent=p.confirm;$('confirmInput').value='';$('confirmDialog').classList.remove('hidden');$('confirmInput').focus();notice('Zahtjev nije poslan routeru: potrebno je potvrditi operaciju.')}).catch(e=>notice(e.message,true))}
$('dhcpForm').onsubmit=e=>{e.preventDefault();prepare('dhcp',{enabled:$('dhcpEnable').checked,start:$('poolStart').value,end:$('poolEnd').value,lease_hours:Number($('lease').value),recovery_ready:$('dhcpRecovery').checked})};$('dnsForm').onsubmit=e=>{e.preventDefault();prepare('dns',{mode:$('dnsMode').value,primary:$('dnsPrimary').value,secondary:$('dnsSecondary').value})};$('wifiPowerForm').onsubmit=e=>{e.preventDefault();prepare('wifi_power',{enabled:$('wifiPower').checked,recovery_ready:$('wifiRecovery').checked})};$('wanLinkForm').onsubmit=e=>{e.preventDefault();prepare('wan_link',{connected:$('wanLink').value==='connect',recovery_ready:$('wanRecovery').checked})};$('wifiForm').onsubmit=e=>{e.preventDefault();prepare('wifi_primary',{ssid:$('ssid').value,wifi_password:$('wifiPass').value});$('wifiPass').value=''};$('bearerForm').onsubmit=e=>{e.preventDefault();prepare('bearer',{mode:$('bearer').value})};$('cancel').onclick=()=>{plan=null;$('confirmDialog').classList.add('hidden')};$('commit').onclick=async()=>{if(!plan)return;$('commit').disabled=true;try{const isStatic=plan.kind==='static';const p=await req(isStatic?'static_apply':'apply',{plan_id:plan.plan_id,confirmation:$('confirmInput').value});$('confirmDialog').classList.add('hidden');plan=null;if(isStatic){notice(p.status==='verified'?'Rezervacija verificirana u ZTE listi.':'Status promjene nije potvrđen: '+p.note,p.status!=='verified');dhcpInventory()}else{notice('Zahtjev prihvaćen, stvarno stanje treba ponovno očitati: '+p.note);setTimeout(refresh,4000)}}catch(e){notice('Primjena nije potvrđena: '+e.message,true);$('confirmDialog').classList.add('hidden');plan=null}finally{$('commit').disabled=false}};
function wifiClientRow(c){
  const metrics=['rssi','signal','signal_strength','rx_rate','tx_rate']
    .filter(k=>c[k]!==undefined&&c[k]!==null&&c[k]!=='')
    .map(k=>`${k}: ${c[k]}`).join(' · ');
  return `<div class="client"><div><b>${escapeHTML(c.hostname||'Nepoznati uređaj')}</b><small>${escapeHTML(c.mac_addr||'—')} · SSID indeks ${escapeHTML(c.ssid_index??'—')}${metrics?' · '+escapeHTML(metrics):''}</small></div><span class="ip">${escapeHTML(c.ip_addr||'—')}</span></div>`;
}
function renderClients(){
  let q=$('clientSearch').value.trim().toLowerCase(),filtered=clientList.filter(x=>Object.values(x).some(v=>String(v).toLowerCase().includes(q)));
  $('clientCount').textContent=`${filtered.length} prikazano · ${clientList.length} ukupno (API povezanih klijenata, ne svi DHCP leaseovi)`;
  $('clientsbox').innerHTML=filtered.length?filtered.map(wifiClientRow).join(''):'<p class="hint">Nema rezultata. Prazan API odgovor ne dokazuje da uređaji nisu spojeni.</p>';
}
let wifiSnapshot=null, previousWifiFields=null, wifiBusy=false;
function wifiSelection(){
  return WifiView.select(wifiSnapshot?.clients||[], $('wifiSearch').value, $('wifiIndex').value, $('wifiSort').value);
}
function renderWifiClients(){
  if(!wifiSnapshot)return;
  const clients=wifiSelection(), all=wifiSnapshot.clients||[];
  const counts=new Map();all.forEach(c=>{const i=String(c.ssid_index??'nepoznat');counts.set(i,(counts.get(i)||0)+1)});
  const breakdown=[...counts].map(([i,n])=>`indeks ${i}: ${n}`).join(' · ');
  $('wifiClientCount').textContent=wifiSnapshot.errors?.clients
    ? 'ZTE nije vratio station_list; broj klijenata nije poznat.'
    : `${clients.length} prikazano / ${all.length} prijavljeno${breakdown?' · '+breakdown:''} · očitano ${new Date(wifiSnapshot.read_at).toLocaleString('hr-HR')}`;
  $('wifiClientList').innerHTML=clients.length?clients.map(wifiClientRow).join(''):'<p class="hint">Nema rezultata za ovaj filtar ili ZTE nije vratio klijente. To ne potvrđuje odspajanje uređaja.</p>';
}
async function wifiDiagnostics(){
  if(wifiBusy)return;
  wifiBusy=true;
  const button=$('wifiDiagRefresh');button.disabled=true;$('wifiExport').disabled=true;
  $('wifiRadioStatus').textContent='Očitavam dostupne radio parametre…';
  $('wifiClientCount').textContent='Očitavam spojene Wi-Fi klijente…';
  try{
    const result=await req('wifi_details');
    const fields=result.fields||{}, returned=Object.keys(fields);
    wifiSnapshot={...result,clients:Array.isArray(result.clients)?result.clients:[],read_at:new Date().toISOString()};
    tiles('wifiRadio',fields);
    $('wifiRadioStatus').textContent=`Očitano ${new Date(wifiSnapshot.read_at).toLocaleString('hr-HR')} · ${returned.length} vraćenih polja · ${Object.keys(result.errors||{}).length?'dio API upita nije uspio':'samo čitanje'}`;
    tiles('wifiSupport',Object.fromEntries(Object.entries(result.field_status||{}).map(([key,value])=>[key,value==='returned'?'Vrijednost vraćena':'Nije vraćeno · podrška nije potvrđena'])));
    const changes=WifiView.changes(previousWifiFields,fields);
    $('wifiChanges').textContent=previousWifiFields===null?'Prvo očitanje u ovoj sesiji; za usporedbu ponovno pritisni Očitaj.':changes.length?'Promjene od prethodnog očitanja: '+changes.map(c=>`${labels[c.key]||c.key}: ${c.before} → ${c.after}`).join(' · '):'Nema promjena među poljima dostupnima u oba očitanja. Izostala polja ne smatramo promjenom konfiguracije.';
    previousWifiFields={...fields};
    const selected=$('wifiIndex').value;
    const indices=[...new Set(wifiSnapshot.clients.map(c=>String(c.ssid_index??'')))].sort();
    $('wifiIndex').innerHTML='<option value="">Svi indeksi</option>'+indices.filter(Boolean).map(i=>`<option value="${escapeHTML(i)}">Indeks ${escapeHTML(i)}</option>`).join('');
    $('wifiIndex').value=indices.includes(selected)?selected:'';
    renderWifiClients();$('wifiExport').disabled=Boolean(result.errors?.clients);
  }catch(e){
    wifiSnapshot=null;previousWifiFields=null;
    $('wifiRadioStatus').textContent='Wi-Fi dijagnostika nije dostupna: '+e.message;
    for(const id of ['wifiRadio','wifiSupport','wifiClientList','wifiChanges'])$(id).textContent='Nema svježeg očitanja.';
    $('wifiClientCount').textContent='Nije moguće potvrditi klijente.';
  }finally{button.disabled=false;wifiBusy=false}
}
$('wifiSearch').oninput=renderWifiClients;
$('wifiIndex').onchange=renderWifiClients;
$('wifiSort').onchange=renderWifiClients;
$('wifiExport').onclick=()=>{
  if(!wifiSnapshot||wifiBusy||wifiSnapshot.errors?.clients)return;
  const payload={read_at:wifiSnapshot.read_at,source:'station_list',ssid_index:$('wifiIndex').value||null,query:$('wifiSearch').value,clients:wifiSelection()};
  const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='zte-wifi-clients.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
function renderWired(){
  $('wiredCount').textContent=`${wiredList.length} uređaja iz lan_station_list (ne moraju biti svi DHCP leaseovi)`;
  $('wiredbox').innerHTML=wiredList.length?wiredList.map(c=>`<div class="client"><div><b>${escapeHTML(c.hostname||'Nepoznati uređaj')}</b><small>${escapeHTML(c.mac_addr||'—')}</small></div><span class="ip">${escapeHTML(c.ip_addr||'—')}</span></div>`).join(''):'<p class="hint">ZTE nije vratio LAN klijente. To ne dokazuje da nisu spojeni.</p>';
}
async function clients(){try{const r=await req('clients');clientList=r.clients||[];renderClients();wiredList=r.wired||[];renderWired()}catch(e){$('clientsbox').textContent=e.message}}async function diagnostics(){try{const [d,a]=await Promise.all([req('diagnostics'),req('audit')]);$('diag').textContent=JSON.stringify(d,null,2);$('audit').textContent=a.events.length?JSON.stringify(a.events,null,2):'Još nije izvedena nijedna konfiguracijska promjena.';caps(d.capabilities)}catch(e){$('diag').textContent=e.message}}
$('wanModeForm').onsubmit=e=>{e.preventDefault();prepare('wan_connection',{mode:$('wanMode').value})};
$('upnpForm').onsubmit=e=>{e.preventDefault();prepare('upnp',{enabled:$('upnpEnable').checked})};
$('dmzForm').onsubmit=e=>{e.preventDefault();prepare('dmz',{enabled:$('dmzEnable').checked,address:$('dmzAddress').value})};
$('rebootForm').onsubmit=e=>{e.preventDefault();prepare('reboot',{})};
async function dhcpInventory(){
  $('reservationsBox').textContent='Čitam…';$('dhcpDnsBox').textContent='Čitam…';
  try {
    const data=await req('dhcp_details');
    const res=data.data?.reservations||{}, dns=data.data?.dhcp_client_dns||{};
    const dStatuses=data.field_status?.dhcp_client_dns||{};
    const rows=res.current_static_addr_list;
    $('staticCapacity').textContent='Kapacitet nije moguće potvrditi.';
    if(Array.isArray(rows)&&rows.every(row=>row&&typeof row==='object'&&!Array.isArray(row))){
      const columns=[['hostname','Naziv uređaja'],['ip','IP adresa'],['mac','MAC adresa'],['domain','Domena']];
      const head=columns.map(([,label])=>`<th>${label}</th>`).join('');
      const body=rows.map((row,i)=>`<tr><td>${i+1}</td>${columns.map(([key])=>`<td>${escapeHTML(String(row[key]??''))}</td>`).join('')}<td><button type="button" class="danger" data-delete-static="${escapeHTML(row.mac||'')}" aria-label="Obriši rezervaciju ${escapeHTML(row.mac||'')}">Obriši</button></td></tr>`).join('');
      $('reservationsBox').innerHTML=rows.length?`<div class="reservation-wide reservation-scroll"><table class="reservation-table"><thead><tr><th>#</th>${head}<th>Radnja</th></tr></thead><tbody>${body}</tbody></table></div>`:'<p class="hint">Router je vratio praznu listu rezervacija.</p>';
      $('reservationsBox').querySelectorAll('[data-delete-static]').forEach(btn=>btn.onclick=()=>prepareStatic('delete',{mac:btn.dataset.deleteStatic}));
      $('staticCapacity').textContent=`Zauzeto ${rows.length} od 10 rezervacija · ${Math.max(0,10-rows.length)} slobodnih mjesta.`;
    }else{
      $('reservationsBox').textContent='Rezervacije nije moguće očitati. Pokušaj ponovno.';
    }
    tiles('dhcpDnsBox',dns);
    if(!Object.keys(dns).length) $('dhcpDnsBox').textContent='DHCP DNS opcija 6 nije potvrđena. WAN DNS nije isto.';
    const dnsdiag=document.createElement('pre');dnsdiag.className='hint';dnsdiag.textContent=JSON.stringify(dStatuses,null,2);$('dhcpDnsBox').appendChild(dnsdiag);
  } catch(e){$('staticCapacity').textContent='Kapacitet nije moguće potvrditi.';$('reservationsBox').textContent='Očitavanje rezervacija nije uspjelo. Pokušaj ponovno.';$('dhcpDnsBox').textContent=e.message;}
}
$('reservationsRefresh').onclick=dhcpInventory;
$('dhcpDnsRefresh').onclick=dhcpInventory;
$('clientSearch').oninput=renderClients;$('clientsRefresh').onclick=clients;$('wifiDiagRefresh').onclick=wifiDiagnostics;$('diagRefresh').onclick=diagnostics;$('diagCopy').onclick=()=>navigator.clipboard.writeText($('diag').textContent).then(()=>notice('Anonimizirana dijagnostika kopirana.')).catch(()=>notice('Kopiranje nije dostupno.',true));$('reload').onclick=refresh;document.querySelectorAll('[data-hours]').forEach(b=>b.onclick=()=>{activeHours=Number(b.dataset.hours);document.querySelectorAll('[data-hours]').forEach(x=>x.classList.toggle('active',Number(x.dataset.hours)===activeHours));history(activeHours)});const tabGroups={pregled:'overview',internet:'internet',traffic:'internet',dhcp:'local',dns:'local',wifi:'local',clients:'local',firewall:'local',system:'system',diagnostics:'system'};
const lastTabs={overview:'pregled',internet:'internet',local:'dhcp',system:'system'};
function openTab(tab){
  const group=tabGroups[tab];if(!group)return;
  lastTabs[group]=tab;
  document.querySelectorAll('[data-group]').forEach(b=>{const active=b.dataset.group===group;b.classList.toggle('active',active);b.setAttribute('aria-expanded',String(active))});
  document.querySelectorAll('.subnav').forEach(n=>n.classList.toggle('hidden',group==='overview'||n.id!=='sub-'+group));
  document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);if(b.dataset.tab===tab)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('hidden',p.id!==tab));
  if(tab==='clients')clients();if(tab==='wifi')wifiDiagnostics();if(tab==='diagnostics')diagnostics();if(tab==='traffic')history(activeHours);
}
document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>openTab(lastTabs[b.dataset.group]));
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>openTab(b.dataset.tab));
function renderWriteMode(){
  const enabled=Boolean(meta?.write_enabled&&meta?.experimental_writes);
  $('writeStatus').textContent=enabled
    ? 'Write mode uključen · svaka promjena traži zasebnu potvrdu'
    : 'Read-only · klikom uključi write mode za pripremu promjena';
  if(meta?.write_mode_source==='session')$('writeStatus').textContent+=' · do restarta App-a';
  $('writeStatus').classList.toggle('enabled',enabled);
  $('writeModeToggle').textContent=enabled?'Isključi write mode':'Uključi write mode';
  $('writeModeToggle').setAttribute('aria-pressed',String(enabled));
  $('writeModeToggle').disabled=!meta;
}
$('writeModeToggle').onclick=async()=>{
  if(!meta)return;
  const button=$('writeModeToggle');button.disabled=true;
  try{
    const result=await req('write_mode',{enabled:!(meta.write_enabled&&meta.experimental_writes)});
    Object.assign(meta,result);plan=null;$('confirmDialog').classList.add('hidden');
    notice(result.write_enabled?'Write mode uključen. Router nije promijenjen; svaku radnju potvrđuješ zasebno.':'Write mode isključen. Pripremljene radnje su poništene.');
  }catch(e){notice('Promjena write moda nije potvrđena: '+e.message,true)}
  finally{renderWriteMode()}
};
refresh();
