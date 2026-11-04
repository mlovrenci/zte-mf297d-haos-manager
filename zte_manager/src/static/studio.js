'use strict';
(() => {
  const model=ZteDemo.create(), $=id=>document.getElementById(id);
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const titles={overview:'Pregled',wifi:'Wi-Fi mreže',devices:'Uređaji',lan:'Lokalna mreža',advanced:'Napredno'};
  const labels={ssid:'Naziv mreže (SSID)',enabled:'Uključeno',channel:'Kanal',width:'Širina kanala (MHz)',security:'Zaštita',hidden:'Skrivena mreža',isolation:'Izolacija gostiju',gateway:'Gateway',mask:'Maska',dhcp:'DHCP uključen',start:'Početak DHCP raspona',end:'Kraj DHCP raspona',lease:'Trajanje najma (sati)',mode:'DNS način',primary:'Primarni DNS',secondary:'Sekundarni DNS',name:'Naziv uređaja',ip:'Rezervirana IP adresa'};
  let page='overview', editing=null, pending=null, timer;
  const button=(kind,id,text='Uredi')=>`<button data-edit="${kind}" data-id="${esc(id||'')}">${text}</button>`;
  const fact=(label,value)=>`<div><small>${label}</small><strong>${esc(value)}</strong></div>`;
  function render(){
    const s=model.read(), empty=$('scenario').value==='empty', devices=empty?[]:s.devices;
    $('title').textContent=titles[page];
    document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
    if(page==='overview') $('content').innerHTML=`<div class="stats">${[['Wi-Fi mreže',s.wifi.filter(w=>w.enabled).length+' / 3'],['Uređaji',devices.length],['Rezervacije',s.reservations.length],['Veza','Demo online']].map(([k,v])=>`<div class="stat"><small>${k}</small><strong>${v}</strong></div>`).join('')}</div><div class="columns"><section class="card"><h2>Mreža na jednom mjestu</h2><p>Uredi naziv mreže, kanal, širinu i gostujuću mrežu. Svaka promjena ima pregled prije primjene.</p><button data-page="wifi">Uredi Wi-Fi</button></section><section class="card"><h2>Uređaji i adrese</h2><p>Preimenuj uređaj, dodaj rezervaciju i isprobaj provjeru IP konflikata.</p><button data-page="devices">Otvori uređaje</button></section></div><section class="card wide"><h2>Zadnje demo promjene</h2>${audit(s)}</section>`;
    if(page==='wifi') $('content').innerHTML=`<div class="cards">${s.wifi.map(w=>`<section class="card"><div class="card-head"><h3>${esc(w.name)}</h3><span class="status ${w.enabled?'':'off'}">${w.enabled?'Uključena':'Isključena'}</span></div><div class="ssid">${esc(w.ssid)}</div><div class="facts">${fact('Kanal',w.channel)}${fact('Širina',w.width+' MHz')}${fact('Zaštita',w.security)}${fact('Vidljivost',w.hidden?'Skrivena':'Vidljiva')}</div>${button('wifi',w.id,'Uredi mrežu')}</section>`).join('')}</div><section class="card wide"><h3>Band steering</h3><p>Simuliraj zajedničko upravljanje frekvencijama. Trenutno: ${s.steering.enabled?'uključeno':'isključeno'}.</p>${button('steering','','Uredi steering')}<p class="note">Dostupni kanali i WPA3 ovdje su demo mogućnosti. Podršku na A1 B08 treba zasebno potvrditi.</p></section>`;
    if(page==='devices') $('content').innerHTML=`<section class="card"><div class="card-head"><h2>Uređaji <small>(${devices.length})</small></h2><label class="search">Traži naziv, IP ili MAC<input id="search" type="search" placeholder="Pronađi uređaj"></label></div><div class="table-scroll"><table><thead><tr><th>Uređaj</th><th>Adresa</th><th>Veza</th><th>Radnje</th></tr></thead><tbody>${devices.map(d=>`<tr data-search="${esc((d.name+' '+d.ip+' '+d.mac).toLowerCase())}"><td>${esc(d.name)}<small>${esc(d.mac)}</small></td><td>${esc(d.ip)}<small>${s.reservations.some(r=>r.id===d.id)?'Rezervacija aktivna':'Dinamička adresa'}</small></td><td>${esc(d.band)}<small>${d.rssi===null?'Žična veza':d.rssi+' dBm'}</small></td><td>${button('device',d.id,'Naziv')} ${button('reservation',d.id,'Rezervacija')}</td></tr>`).join('')}</tbody></table></div><p id="emptyDevices" class="empty" ${devices.length?'hidden':''}>Nema uređaja za prikaz.</p></section>`;
    if(page==='lan') $('content').innerHTML=`<div class="columns"><section class="card"><h2>LAN i DHCP</h2><div class="facts">${fact('Gateway',s.lan.gateway)}${fact('DHCP',s.lan.dhcp?'Uključen':'Isključen')}${fact('Od',s.lan.start)}${fact('Do',s.lan.end)}</div>${button('lan','','Uredi LAN / DHCP')}<p>Simulator koristi /24 mrežu. Promjena podmreže mora biti usklađena s rezervacijama.</p></section><section class="card"><h2>DNS</h2><div class="facts">${fact('Način',s.dns.mode==='auto'?'Automatski':'Ručni')}${fact('Primarni',s.dns.primary||'Automatski')}</div>${button('dns','','Uredi DNS')}</section></div><section class="card wide"><h2>Rezervacije</h2><p>${s.reservations.map(r=>esc(r.name)+' · '+esc(r.ip)).join('<br>')||'Nema rezervacija.'}</p><button data-page="devices">Upravljaj kroz uređaje</button></section>`;
    if(page==='advanced') $('content').innerHTML=`<section class="card"><h2>Dnevnik simulacije</h2><p>Podaci traju samo dok je ova stranica otvorena. Nema zapisivanja na router ni trajnog spremanja.</p>${audit(s)}</section>`;
  }
  function audit(s){return s.audit.length?s.audit.map(a=>`<div class="audit">${esc(a.action)} · ${esc(a.target)}<small>${esc(new Date(a.time).toLocaleTimeString('hr-HR'))}</small></div>`).join(''):'<p>Još nema promjena. Otvori Wi-Fi ili uređaje i isprobaj uređivanje.</p>';}
  function field(k,v,options){const label=labels[k]||k;if(typeof v==='boolean')return `<label><input name="${k}" type="checkbox" ${v?'checked':''}>${label}</label>`;if(options)return `<label>${label}<select name="${k}">${options.map(o=>`<option value="${esc(o)}" ${String(v)===String(o)?'selected':''}>${esc(o)}</option>`).join('')}</select></label>`;return `<label>${label}<input name="${k}" type="${typeof v==='number'?'number':'text'}" value="${esc(v)}"></label>`;}
  function open(kind,id){
    const s=model.read(); let data;
    if(kind==='wifi'){const w=s.wifi.find(x=>x.id===id);data={ssid:w.ssid,enabled:w.enabled,channel:w.channel,width:w.width,security:w.security,hidden:w.hidden};if(id==='guest')data.isolation=w.isolation;}
    else if(kind==='device')data={name:s.devices.find(d=>d.id===id).name};
    else if(kind==='reservation'){const d=s.devices.find(x=>x.id===id),r=s.reservations.find(x=>x.id===id);data={enabled:!!r,name:r?.name||d.name,ip:r?.ip||d.ip};}
    else data=s[kind];
    editing={kind,id,data};pending=null;
    $('editorTitle').textContent={wifi:'Uredi Wi-Fi mrežu',lan:'LAN i DHCP',dns:'DNS postavke',device:'Naziv uređaja',reservation:'Rezervacija adrese',steering:'Band steering'}[kind];
    $('fields').innerHTML=Object.entries(data).map(([k,v])=>field(k,v,k==='channel'?(id==='radio5'?['auto','36','40','44','48']:['auto',...Array.from({length:13},(_,i)=>String(i+1))]):k==='width'?(id==='radio5'?['20','40','80']:['20','40']):k==='security'?['WPA2','WPA2/WPA3']:k==='mode'?['auto','manual']:null)).join('');
    back();$('editor').showModal();
  }
  function back(){pending=null;$('fields').hidden=false;$('review').hidden=true;$('back').hidden=true;$('submit').textContent='Pregled promjene';$('formError').textContent='';}
  document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.page){page=b.dataset.page;render();}if(b.dataset.edit)open(b.dataset.edit,b.dataset.id);});
  $('editForm').addEventListener('submit',e=>{
    e.preventDefault();$('formError').textContent='';
    try{if(pending){model.apply(pending,$('scenario').value);$('editor').close();$('notice').textContent='Promjena je spremljena samo u simulatoru.';render();return;}
      const values={};for(const [k,v] of Object.entries(editing.data)){const input=$('editForm').elements.namedItem(k);values[k]=typeof v==='boolean'?input.checked:typeof v==='number'?Number(input.value):input.value;}
      pending=model.plan(editing.kind,editing.id,values);
      const rows=Object.entries(values).filter(([k,v])=>v!==pending.before[k]);
      if(!rows.length){pending=null;throw Error('Nema promjena za spremanje.');}
      const display=v=>typeof v==='boolean'?(v?'Da':'Ne'):v??'—';
      $('review').innerHTML='<table><thead><tr><th>Postavka</th><th>Prije</th><th>Poslije</th></tr></thead><tbody>'+rows.map(([k,v])=>`<tr><td>${labels[k]||k}</td><td>${esc(display(pending.before[k]))}</td><td>${esc(display(v))}</td></tr>`).join('')+'</tbody></table><p>Primjena mijenja isključivo demo podatke.</p>';
      $('fields').hidden=true;$('review').hidden=false;$('back').hidden=false;$('submit').textContent='Primijeni u simulatoru';
    }catch(err){$('formError').textContent=err.message;}
  });
  $('close').onclick=()=>$('editor').close();$('back').onclick=back;
  $('reset').onclick=()=>{clearTimeout(timer);model.reset();$('scenario').value='normal';$('notice').textContent='Vraćeni su početni demo podaci.';render();};
  $('scenario').onchange=()=>{clearTimeout(timer);$('notice').textContent='';render();if($('scenario').value==='reconnect'){$('notice').textContent='Simulacija: veza je prekinuta…';timer=setTimeout(()=>{$('notice').textContent='Simulacija: veza je ponovno uspostavljena.';},1500);}};
  document.addEventListener('input',e=>{if(e.target.id!=='search')return;let count=0;document.querySelectorAll('[data-search]').forEach(r=>{r.hidden=!r.dataset.search.includes(e.target.value.toLowerCase());if(!r.hidden)count++;});$('emptyDevices').hidden=count>0;});
  render();
})();
