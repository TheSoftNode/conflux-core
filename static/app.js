/* CONFLUX CORE — cinematic presentation / server-authoritative multiplayer.
   The hero environment is pre-rendered reference art. Native 3D is selectable.
   Both views use the same WebSocket game state and controls. */
'use strict';
const $=id=>document.getElementById(id);
let socket=null,state=null,roomCode='',playerName='',retry=0,reconnectTimer=null,toastTimer=null,lastRevision=-1,selectedDial=-1,leaving=false,unread=0;
let demoMode=false,demoClock=null,nativeView=false;
const safe=x=>String(x??'').replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
const invite=code=>`${location.origin}${location.pathname}?room=${encodeURIComponent(code)}`;
const online=()=>state?.players.filter(p=>p.online).length??0;
const ownerName=id=>state?.players.find(p=>p.id===id)?.name??'OPEN';
const colors=['#4ff4f0','#ffad37','#ec66fb','#6197ff'];
const names=['AETHER','EMBER','PRISM','PULSE'];
const symbols=['✦','◆','⬢','✳','◈','●'];
function toast(msg){$('toast').textContent=msg;$('toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),3300)}
function send(packet){if(demoMode){handleDemo(packet);return;}if(socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify(packet));else toast('Reconnecting to your crew...')}
function readName(){let n=$('player-name').value.trim().slice(0,18);if(!n){toast('Enter your callsign first.');$('player-name').focus();return null}try{localStorage.setItem('conflux-name',n)}catch{}return n}
function showGame(){ $('landing').classList.add('hidden');$('game').classList.remove('hidden');$('code-label').textContent=roomCode;document.body.classList.add('in-game');positionHotspots();}
function leave(){leaving=true;clearTimeout(reconnectTimer);clearInterval(demoClock);demoClock=null;const old=socket;socket=null;if(old){old.onclose=null;old.close()}roomCode='';state=null;lastRevision=-1;selectedDial=-1;demoMode=false;$('game').classList.add('hidden');$('landing').classList.remove('hidden');$('demo-ribbon').classList.add('hidden');document.body.classList.remove('in-game');document.body.classList.remove('native-mode');nativeView=false;history.replaceState({},'',location.pathname);leaving=false;}
function connect(code,name){roomCode=code.toUpperCase().trim();playerName=name;showGame();history.replaceState({},'',invite(roomCode));clearTimeout(reconnectTimer);if(socket){socket.onclose=null;socket.close()}
 const scheme=location.protocol==='https:'?'wss':'ws';const ws=new WebSocket(`${scheme}://${location.host}/ws/${encodeURIComponent(roomCode)}`);socket=ws;
 ws.onopen=()=>{retry=0;let token='';try{token=sessionStorage.getItem(`conflux-token-${roomCode}`)||''}catch{}send({type:'join',name:playerName,token})};
 ws.onmessage=ev=>{let m;try{m=JSON.parse(ev.data)}catch{return}if(m.type==='error'){toast(m.message);if(!state)setTimeout(()=>{if(socket===ws)leave()},1900);return}if(m.type==='state'){state=m;try{if(m.session)sessionStorage.setItem(`conflux-token-${roomCode}`,m.session)}catch{}window.ConfluxScene?.setState(m);render()}};
 ws.onclose=ev=>{if(leaving||ws!==socket||!roomCode)return;if(ev.code===1008||ev.code===4001){toast('This chamber is no longer available.');return}retry++;if(retry<=12)reconnectTimer=setTimeout(()=>connect(roomCode,playerName),Math.min(650*retry,5500));else toast('Connection lost. Refresh to reconnect.')};ws.onerror=()=>{};
}
$('create-room').addEventListener('click',async()=>{let name=readName();if(!name)return;if(location.protocol==='file:'){toast('Multiplayer needs the Python server. Open the standalone practice demo instead.');return;}let button=$('create-room');button.disabled=true;try{let r=await fetch('/api/rooms',{method:'POST'});if(!r.ok)throw Error('Room server unavailable. Launch the Python server or use the offline practice demo.');const {code}=await r.json();connect(code,name)}catch(e){toast(e.message==='Failed to fetch'?'Cannot reach multiplayer server. Run the Python server or use offline practice.':e.message)}finally{button.disabled=false}});
function join(){let name=readName();if(!name)return;const code=$('room-code-input').value.replace(/[^A-Z0-9]/gi,'').toUpperCase();if(code.length!==5){toast('Enter the five-character room code.');return}connect(code,name)}
$('join-room').addEventListener('click',join);$('room-code-input').addEventListener('keydown',e=>{if(e.key==='Enter')join()});
$('copy-link').addEventListener('click',async()=>{const url=invite(roomCode);try{await navigator.clipboard.writeText(url);toast('Room invitation copied.')}catch{window.prompt('Copy the room invitation:',url)}});
$('leave-room').addEventListener('click',leave);
$('reset-camera').addEventListener('click',()=>{window.ConfluxScene?.resetCamera();toast(nativeView?'Camera reset.':'Switch to 3D to orbit the camera.')});
$('toggle-view').addEventListener('click',()=>{nativeView=!nativeView;document.body.classList.toggle('native-mode',nativeView);$('toggle-view').textContent=nativeView?'ART':'3D';$('toggle-view').classList.toggle('active',nativeView);$('toggle-view').title=nativeView?'Show cinematic artwork':'Show native 3D geometry';toast(nativeView?'Native interactive 3D view':'Cinematic arena view');});
function toggleChat(force){const pane=$('comms');let open=typeof force==='boolean'?force:pane.classList.contains('collapsed');pane.classList.toggle('collapsed',!open);$('toggle-comms').setAttribute('aria-expanded',String(open));if(open){unread=0;$('unread-dot').classList.remove('on')}}
$('toggle-comms').addEventListener('click',()=>toggleChat());$('close-comms').addEventListener('click',()=>toggleChat(false));
$('lobby-action').addEventListener('click',e=>{if(e.target.closest('#start-button'))send({type:'start'})});
$('chat-form').addEventListener('submit',e=>{e.preventDefault();const field=$('chat-input');let message=field.value.trim();if(!message)return;send({type:'chat',message});field.value=''});
$('rotate-left').addEventListener('click',()=>move(-1));$('rotate-right').addEventListener('click',()=>move(1));
$('cycle-station').addEventListener('click',()=>{if(!state)return;const options=names.map((_,i)=>i).filter(i=>state.owners[i]===state.you);if(!options.length)return;let current=options.indexOf(selectedDial);selectDial(options[(current+1)%options.length]);});
function move(direction){if(!state||selectedDial<0)return;if(state.phase!=='playing'||state.paused||state.owners[selectedDial]!==state.you){toast('This station is not available to you.');return}send({type:'move',dial:selectedDial,direction});pulseHotspot(selectedDial);}
document.addEventListener('keydown',e=>{if($('game').classList.contains('hidden'))return;if(['INPUT','TEXTAREA'].includes(document.activeElement.tagName))return;if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();move(e.key==='ArrowLeft'?-1:1)}if(e.key.toLowerCase()==='c')toggleChat();});
$('arena-hotspots').addEventListener('click',e=>{const hotspot=e.target.closest('.ring-hotspot');if(hotspot)selectDial(Number(hotspot.dataset.dial))});
window.addEventListener('conflux-select',e=>selectDial(e.detail.dial));
function selectDial(i){selectedDial=i;window.ConfluxScene?.select(i);renderStation();renderHotspots();}
const stationCoords=[[273,181],[856,182],[229,521],[850,519]];
function positionHotspots(){const im=$('arena-art'),parent=$('cinematic-view'),width=parent.clientWidth,height=parent.clientHeight;if(!width||!height)return;const mobile=window.matchMedia('(max-width:800px)').matches,iw=mobile?941:1125,ih=mobile?1700:721,s=Math.max(width/iw,height/ih),ox=(width-iw*s)/2,oy=(height-ih*s)/2;for(const [i,el] of Array.from($('arena-hotspots').querySelectorAll('.ring-hotspot')).entries()){const[x,y]=mobile?[[232,533],[720,532],[226,988],[715,987]][i]:stationCoords[i];el.style.left=`${ox+x*s}px`;el.style.top=`${oy+y*s}px`;el.style.setProperty('--hot-size',`${Math.max(56,Math.min(410,(mobile?222:270)*s))}px`)}}
window.addEventListener('resize',positionHotspots);
function pulseHotspot(i){const el=$('arena-hotspots').querySelector(`[data-dial="${i}"]`);if(el){el.classList.remove('pulse');void el.offsetWidth;el.classList.add('pulse');setTimeout(()=>el.classList.remove('pulse'),600)}}
function renderHotspots(){const root=$('arena-hotspots');if(root.querySelectorAll('.ring-hotspot').length!==4){root.innerHTML=names.map((name,i)=>`<button class="ring-hotspot" data-dial="${i}" title="Select ${name} reactor" aria-label="Select ${name} station" style="--ring-color:${colors[i]}"><span class="orbit-outline"></span><span class="rotor-indicator"></span><span class="ring-label"></span></button>`).join('')+'<div class="core-surge"></div>';}for(const el of root.querySelectorAll('.ring-hotspot')){const i=Number(el.dataset.dial);const matched=!!state?.positions&&state.positions[i]===state.target[i];el.classList.toggle('selected',selectedDial===i);el.classList.toggle('match',matched);el.querySelector('.ring-label').textContent=names[i]+(matched?' · ALIGNED':'');el.querySelector('.rotor-indicator').style.transform=`rotate(${(state?.positions?.[i]??0)*60}deg)`;}positionHotspots()}
function render(){if(!state)return;const count=online();$('crew-count').textContent=`${count} / 4`;$('stage-label').textContent=`${String(state.stage).padStart(2,'0')} / ${String(state.stages).padStart(2,'0')}`;$('score-label').textContent=state.score.toLocaleString();const seconds=Math.max(0,Math.ceil(state.seconds));$('timer-label').textContent=['playing','intermission'].includes(state.phase)?`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`:'--:--';$('timer-label').style.color=state.phase==='playing'&&seconds<=15?'#ff858e':'';
 $('sync-label').textContent=state.phase==='lobby'?'AWAITING CREW':state.phase==='playing'?(state.paused?'CREW DISCONNECTED':'CORE ONLINE'):state.phase==='intermission'?'RECALIBRATING':'RUN COMPLETE';
 const owned=names.map((_,i)=>i).filter(i=>state.owners[i]===state.you);if((selectedDial<0||!owned.includes(selectedDial))&&owned.length)selectedDial=owned[0];
 if(lastRevision!==state.revision){renderCrew();renderChat();renderAction();lastRevision=state.revision}renderStation();renderHotspots();renderMessage();}
function renderStation(){if(!state)return;const i=selectedDial<0?0:selectedDial;const playing=state.phase==='playing'&&!state.paused;const mine=state.owners[i]===state.you;$('station-name').textContent=names[i];$('station-current').textContent=state.positions?symbols[state.positions[i]]:'◇';$('station-target').textContent=state.target?symbols[state.target[i]]:'✳';$('station-owner').textContent=mine?'YOUR CONTROL':safe(ownerName(state.owners[i]));$('station-hud').style.setProperty('--own-color',colors[i]);$('rotate-left').disabled=$('rotate-right').disabled=!(playing&&mine);$('control-tip').textContent=mine?'Your rotation also moves the next station backward.':'Select a station assigned to you to rotate it.';$('cycle-station').style.visibility=state.owners.filter(o=>o===state.you).length>1?'visible':'hidden';$('board-subtitle').textContent=state.phase==='playing'?'LIVE / LINKED':'STANDBY';}
function renderCrew(){const el=$('crew-list');el.innerHTML=state.players.map((p,i)=>`<div class="crew-person" style="--member-color:${colors[i%4]}"><span class="crew-avatar">${safe(p.name.slice(0,1).toUpperCase())}</span><span class="crew-person-name">${safe(p.name)}${p.id===state.you?' (YOU)':''}</span><small class="${p.online?'':'offline'}">${p.online?(p.is_host?'HOST':'ONLINE'):'OFFLINE'}</small></div>`).join('')}
function renderChat(){const el=$('chat-log'),bottom=el.scrollTop+el.clientHeight>=el.scrollHeight-35;const oldCount=Number(el.dataset.messageCount||0);el.innerHTML=state.chat.map(m=>`<div class="message ${m.name==='SYSTEM'?'system':''}"><strong>${safe(m.name)}:</strong> ${safe(m.message)}</div>`).join('');if(bottom)el.scrollTop=el.scrollHeight;if(state.chat.length>oldCount&&$('comms').classList.contains('collapsed')&&oldCount){$('unread-dot').classList.add('on')}el.dataset.messageCount=state.chat.length;}
function renderAction(){const el=$('lobby-action');if(state.phase==='lobby'){if(state.host===state.you){const enough=online()>=2;el.innerHTML=`<button class="primary-btn start-button" id="start-button" ${enough?'':'disabled'}>START REACTOR ↗</button>${enough?'':'<p class="lobby-tip">Invite at least one teammate to start.</p>'}`}else el.innerHTML='<p class="lobby-tip">Waiting for host to activate the core.</p>'}else if(state.phase==='finished'&&state.host===state.you){el.innerHTML='<button class="primary-btn start-button" id="start-button">PLAY AGAIN ↗</button>'}else el.innerHTML=''}
function renderMessage(){let p=state.phase,msg='',detail='COORDINATE YOUR MOVES TO STABILIZE THE CORE',matched=0;if(state.positions&&state.target)matched=state.positions.filter((x,i)=>x===state.target[i]).length;
 if(p==='lobby'){msg='AWAITING CREW · SHARE YOUR ROOM CODE';detail='TWO OR MORE OPERATORS REQUIRED'}else if(p==='playing'){if(state.paused){msg='SIGNAL PAUSED · WAITING FOR A TEAMMATE';detail='THE CLOCK RESUMES WHEN TWO PLAYERS ARE ONLINE'}else {msg=`${matched} / 4 RINGS ALIGNED`;detail='COORDINATE YOUR MOVES TO STABILIZE THE CORE';}}else if(p==='intermission'){msg=state.result==='solved'?`CORE STABILIZED · +${state.last_score} POINTS`:'REACTOR OVERLOADED · TRY AGAIN';detail=`NEXT ROUND IN ${Math.ceil(state.seconds)} SECONDS`;}else {msg=`MISSION COMPLETE · ${state.score.toLocaleString()} POINTS`;detail='THANK YOU, CREW — RUN ANOTHER SIMULATION'}$('round-message').textContent=msg;$('message-subtitle').textContent=detail;[...$('progress-bars').children].forEach((el,i)=>el.classList.toggle('done',i<matched));}
// Offline practice runs the same three stages and scoring scheme as the server.
// This is still a local simulation; real multiplayer remains server-authoritative.
const demoStageSeconds=[90,80,70];
let demoIntermission=0;
function demoMove(positions,i,direction){const next=positions.slice();next[i]=(next[i]+direction+6)%6;next[(i+1)%4]=(next[(i+1)%4]-direction+6)%6;return next}
function demoStage(stage){
 const target=[(stage+1)%6,(stage*2+1)%6,(stage+3)%6,(stage*3+2)%6];
 let positions=target.slice();
 const moves=[[0,1],[2,-1],[1,1],[3,-1],[0,1],[2,1],[3,1],[1,-1],[0,-1],[2,1],[1,1],[3,-1]];
 for(const [i,d] of moves.slice(0,5+stage*2))positions=demoMove(positions,i,d);
 if(positions.every((n,i)=>n===target[i]))positions=demoMove(positions,0,1);
 Object.assign(state,{phase:'playing',stage,seconds:demoStageSeconds[stage-1],target,positions,moves:0,last_score:0,result:'',paused:false});
 demoIntermission=0;state.revision++;state.chat.push({name:'SYSTEM',message:`Round ${stage} started. Stabilize all four stations!`});
 window.ConfluxScene?.setState(state);render();
}
function demoFinish(won){
 const bonus=won?150+Math.floor(state.seconds)*12+Math.max(0,40-state.moves)*3:0;
 state.last_score=bonus;state.score+=bonus;state.result=won?'solved':'expired';
 state.chat.push({name:'SYSTEM',message:won?`Core stabilized! +${bonus} points.`:'Time expired. The core lost coherence.'});
 if(state.stage>=state.stages){state.phase='finished';state.seconds=0}else{state.phase='intermission';state.seconds=5;demoIntermission=5}
 state.revision++;window.ConfluxScene?.setState(state);render();
}
function startDemo(){
 demoMode=true;roomCode='DEMO1';playerName='YOU';const own='demo-user';
 state={type:'state',code:roomCode,you:own,session:'demo',host:own,revision:0,
 players:[{id:own,name:'YOU',online:true,is_host:true}],owners:[own,own,own,own],
 target:null,positions:null,stage:1,stages:3,seconds:0,paused:false,phase:'lobby',
 score:0,last_score:0,moves:0,result:'',chat:[{name:'SYSTEM',message:'Offline solo practice. Multiplayer requires the Python server.'}]};
 $('demo-ribbon').classList.remove('hidden');showGame();demoStage(1);
 clearInterval(demoClock);
 demoClock=setInterval(()=>{
  if(!demoMode||!state)return;
  if(state.phase==='playing'){state.seconds=Math.max(0,state.seconds-1);if(state.seconds===0){demoFinish(false);return}}
  else if(state.phase==='intermission'){demoIntermission--;state.seconds=demoIntermission;if(demoIntermission<=0){demoStage(state.stage+1);return}}
  render();
 },1000);
 toast('Solo practice: three rounds. All four stations are yours.');
}
function handleDemo(packet){
 if(!state)return;
 if(packet.type==='move'&&state.phase==='playing'){
  if(!Number.isInteger(packet.dial)||packet.dial<0||packet.dial>=4||![-1,1].includes(packet.direction))return;
  state.positions=demoMove(state.positions,packet.dial,packet.direction);
  state.moves++;state.revision++;
  if(state.positions.every((x,j)=>x===state.target[j])){demoFinish(true);return}
  window.ConfluxScene?.setState(state);render();
 }else if(packet.type==='chat'){
  state.chat.push({name:playerName,message:packet.message});state.revision++;render();
 }else if(packet.type==='start'&&state.phase==='finished'){
  state.score=0;state.chat=[];demoStage(1);
 }
}
(function boot(){try{$('player-name').value=localStorage.getItem('conflux-name')||''}catch{}if(new URLSearchParams(location.search).get('demo')==='1'){startDemo();return}let code=new URLSearchParams(location.search).get('room');if(code&&/^[a-z0-9]{5}$/i.test(code)){$('room-code-input').value=code.toUpperCase();toast('Invitation loaded. Enter your name to join.')}})();
