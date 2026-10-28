/* CONFLUX CORE — browser client.
   The server is authoritative: this file sends requests and renders snapshots.
   Offline practice (window.CONFLUX_OFFLINE or ?demo=1) runs the same rules locally via logic.js. */
'use strict';
const $ = id => document.getElementById(id);
const L = window.ConfluxLogic;
const COLORS = ['#4ff4f0', '#ffad37', '#6197ff', '#ec66fb'];
let NAMES = L.STATIONS.slice();
let SYMBOLS = L.SYMBOLS.slice();
const FATAL_CLOSE = { 1008: 'Connection refused by the server.', 4000: 'You left the room.', 4001: 'This crew seat was opened in another tab.', 4004: 'This room no longer exists.' };
const app = {
  socket: null, state: null, roomCode: '', playerName: '', retry: 0, reconnectTimer: null, pingTimer: null,
  selected: -1, manualSelect: false, unread: 0, leaving: false, demo: null, nativeView: false,
  lastRevision: -1, lastActionKey: '', deadline: 0, quickPlay: false, resultHiddenFor: '', lastTick: -1,
};
window.ConfluxDebug = { get state() { return app.state; }, get selected() { return app.selected; } };

const safe = x => String(x ?? '').replace(/[&<>"']/g, s => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[s]));
const invite = code => `${location.origin}${location.pathname}?room=${encodeURIComponent(code)}`;
const store = {
  get(area, key) { try { return window[area].getItem(key); } catch { return null; } },
  set(area, key, value) { try { window[area].setItem(key, value); } catch { /* storage blocked */ } },
};
const S = () => app.state;
const me = () => S()?.players.find(p => p.id === S().you);
const playerById = id => S()?.players.find(p => p.id === id);
const ownerName = id => playerById(id)?.name ?? 'OPEN';
const ownedDials = () => (S()?.owners || []).map((o, i) => o === S().you ? i : -1).filter(i => i >= 0);
const isHost = () => !!S() && S().host === S().you;
const playing = () => S()?.phase === 'playing' && !S().paused;
const humansOnline = () => S()?.players.filter(p => p.online && !p.bot).length ?? 0;
const fmtTime = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

/* ---------- feedback ---------- */
let toastTimer = null;
function toast(msg, ms = 3200) {
  const el = $('toast'); el.textContent = msg; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}
const Sound = (() => {
  let ctx = null, on = store.get('localStorage', 'conflux-sound') !== 'off';
  function tone(freq, dur = .12, type = 'sine', gain = .05, when = 0, slide = 0) {
    if (!on) return;
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === 'suspended') ctx.resume();
      const t = ctx.currentTime + when, o = ctx.createOscillator(), g = ctx.createGain();
      o.type = type; o.frequency.setValueAtTime(freq, t);
      if (slide) o.frequency.exponentialRampToValueAtTime(freq * slide, t + dur);
      g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(gain, t + .012); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
      o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + dur + .03);
    } catch { /* audio unavailable */ }
  }
  return {
    get on() { return on; },
    toggle() { on = !on; store.set('localStorage', 'conflux-sound', on ? 'on' : 'off'); if (on) tone(660, .08); return on; },
    move(d, mine) { tone(d > 0 ? 540 : 420, .08, 'triangle', mine ? .05 : .03); },
    align() { tone(660, .09, 'sine', .05); tone(990, .14, 'sine', .04, .07); },
    solve() { [523, 659, 784, 1046].forEach((f, i) => tone(f, .28, 'sine', .06, i * .09)); },
    fail() { tone(240, .6, 'sawtooth', .035, 0, .45); },
    tick() { tone(1000, .04, 'square', .018); },
    join() { tone(440, .08, 'sine', .04); tone(660, .1, 'sine', .04, .07); },
    error() { tone(170, .14, 'square', .025); },
  };
})();

/* ---------- landing / session ---------- */
function readName() {
  const n = $('player-name').value.trim().slice(0, 18);
  if (!n) { toast('Enter your callsign first.'); $('player-name').focus(); return null; }
  store.set('localStorage', 'conflux-name', n);
  return n;
}
function showGame() {
  $('landing').classList.add('hidden'); $('game').classList.remove('hidden');
  $('code-label').textContent = app.roomCode; document.body.classList.add('in-game');
  if (store.get('localStorage', 'conflux-help-seen') !== '1') openHelp();
  requestAnimationFrame(positionHotspots);
}
function resetSession() {
  clearTimeout(app.reconnectTimer); clearInterval(app.pingTimer);
  if (app.demo) { clearInterval(app.demo.clock); app.demo = null; }
  const old = app.socket; app.socket = null;
  if (old) { old.onclose = null; old.onmessage = null; try { old.close(1000); } catch { /* already closed */ } }
  Object.assign(app, { state: null, roomCode: '', lastRevision: -1, selected: -1, manualSelect: false, lastActionKey: '', quickPlay: false, retry: 0, unread: 0, resultHiddenFor: '' });
}
function leave(message) {
  app.leaving = true;
  if (app.socket?.readyState === WebSocket.OPEN && !message) { try { app.socket.send(JSON.stringify({ type: 'leave' })); } catch { /* closing anyway */ } }
  try { sessionStorage.removeItem(`conflux-token-${app.roomCode}`); } catch { /* storage blocked */ }
  resetSession();
  $('game').classList.add('hidden'); $('landing').classList.remove('hidden');
  ['demo-ribbon', 'lobby-panel', 'result-panel', 'net-status'].forEach(id => $(id).classList.add('hidden'));
  document.body.classList.remove('in-game', 'native-mode'); document.body.removeAttribute('data-phase');
  app.nativeView = false; $('toggle-view').textContent = '3D';
  history.replaceState({}, '', location.pathname);
  app.leaving = false;
  if (message) toast(message, 4500);
}
async function createRoom(quick) {
  const name = readName(); if (!name) return;
  if (location.protocol === 'file:') { toast('Online rooms need the game server. Starting offline practice instead.'); startDemo(); return; }
  const buttons = [$('create-room'), $('quick-play')]; buttons.forEach(b => b.disabled = true);
  try {
    const r = await fetch('/api/rooms', { method: 'POST' });
    if (!r.ok) {
      let detail = ''; try { detail = (await r.json()).detail; } catch { /* not JSON */ }
      throw Error(detail || 'Room server unavailable. Try again in a moment.');
    }
    const { code } = await r.json();
    connect(code, name);
    app.quickPlay = !!quick;
  } catch (e) {
    toast(e instanceof TypeError ? 'Cannot reach the game server. Check your connection and try again.' : e.message);
  } finally { buttons.forEach(b => b.disabled = false); }
}
function joinFromInput() {
  const name = readName(); if (!name) return;
  const code = $('room-code-input').value.replace(/[^A-Z0-9]/gi, '').toUpperCase();
  if (code.length !== 5) { toast('Enter the five-character room code.'); $('room-code-input').focus(); return; }
  connect(code, name);
}
function connect(code, name) {
  resetSession();
  app.roomCode = code.toUpperCase().trim(); app.playerName = name;
  showGame(); history.replaceState({}, '', invite(app.roomCode));
  setNet('CONNECTING…');
  openSocket();
}
function openSocket() {
  clearTimeout(app.reconnectTimer);
  if (app.socket) { app.socket.onclose = null; try { app.socket.close(); } catch { /* ignore */ } }
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${scheme}://${location.host}/ws/${encodeURIComponent(app.roomCode)}`);
  app.socket = ws;
  ws.onopen = () => {
    const token = store.get('sessionStorage', `conflux-token-${app.roomCode}`) || '';
    ws.send(JSON.stringify({ type: 'join', name: app.playerName, token }));
    clearInterval(app.pingTimer);
    app.pingTimer = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send('{"type":"ping"}'); }, 20000);
  };
  ws.onmessage = ev => {
    if (ws !== app.socket) return;
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (m.type === 'pong') return;
    if (m.type === 'error') {
      Sound.error();
      if (m.fatal) { leave(m.message); return; }
      toast(m.message); return;
    }
    if (m.type === 'state') { app.retry = 0; setNet(null); applyState(m); }
  };
  ws.onclose = ev => {
    if (ws !== app.socket || app.leaving || !app.roomCode) return;
    clearInterval(app.pingTimer);
    if (FATAL_CLOSE[ev.code]) { leave(FATAL_CLOSE[ev.code]); return; }
    scheduleReconnect();
  };
  ws.onerror = () => { /* onclose follows */ };
}
function scheduleReconnect() {
  app.retry++;
  if (app.retry > 40) { setNet('CONNECTION LOST', true); return; }
  setNet(app.retry > 3 ? `RECONNECTING… (attempt ${app.retry})` : 'RECONNECTING…');
  app.reconnectTimer = setTimeout(openSocket, Math.min(400 * app.retry, 5000));
}
function reconnectNow() {
  if (!app.roomCode || app.demo) return;
  const s = app.socket?.readyState;
  if (s === WebSocket.OPEN || s === WebSocket.CONNECTING) return;
  app.retry = 0; openSocket();
}
function setNet(text, showRetry = false) {
  const el = $('net-status');
  if (!text) { el.classList.add('hidden'); return; }
  el.classList.remove('hidden'); $('net-text').textContent = text;
  $('net-retry').classList.toggle('hidden', !showRetry);
  el.classList.toggle('lost', showRetry);
}
function send(packet) {
  if (app.demo) { demoHandle(packet); return; }
  if (app.socket?.readyState === WebSocket.OPEN) app.socket.send(JSON.stringify(packet));
  else toast('Reconnecting to your crew…');
}

/* ---------- state handling ---------- */
function applyState(m) {
  const prev = app.state;
  app.state = m;
  if (m.session && !app.demo) store.set('sessionStorage', `conflux-token-${app.roomCode}`, m.session);
  if (Array.isArray(m.stations) && m.stations.length === 4) NAMES = m.stations.slice();
  if (Array.isArray(m.symbols) && m.symbols.length === 6) SYMBOLS = m.symbols.slice();
  app.deadline = performance.now() + (m.seconds || 0) * 1000;
  window.ConfluxScene?.setState(m);
  react(prev, m);
  if (app.quickPlay && m.phase === 'lobby' && m.host === m.you) {
    if (m.players.some(p => p.bot)) { app.quickPlay = false; send({ type: 'start' }); }
    else if (app.quickPlay === true) { app.quickPlay = 'adding'; send({ type: 'add_bot' }); }
  }
  render();
}
function react(prev, m) {
  const action = m.last_action;
  const key = action ? `${m.stage}:${action.revision}` : '';
  if (action && key !== app.lastActionKey) {
    app.lastActionKey = key;
    const mine = action.by === m.you;
    pulseHotspot(action.dial); pulseHotspot((action.dial + 1) % 4, true);
    if (!mine && m.phase === 'playing') floatNote(action.dial, `${ownerName(action.by)} · ${NAMES[action.dial]} ${action.direction > 0 ? '+' : '−'}`);
    Sound.move(action.direction, mine);
  }
  if (!prev) return;
  if (prev.phase === 'playing' && m.phase === 'playing' && prev.stage === m.stage && prev.positions && m.positions) {
    const before = prev.positions.filter((x, i) => x === prev.target[i]).length;
    const after = m.positions.filter((x, i) => x === m.target[i]).length;
    if (after > before) Sound.align();
  }
  if (prev.phase === 'playing' && m.phase !== 'playing' && m.result) (m.result === 'solved' ? Sound.solve : Sound.fail)();
  if (m.phase === 'playing' && (prev.phase !== 'playing' || prev.stage !== m.stage)) {
    app.manualSelect = false; app.selected = -1;
    toast(`Round ${m.stage} of ${m.stages} · par ${m.par} moves`);
  }
  const prevHumans = prev.players.filter(p => p.online).length, nowHumans = m.players.filter(p => p.online).length;
  if (nowHumans > prevHumans) Sound.join();
}
function render() {
  const s = S(); if (!s) return;
  document.body.dataset.phase = s.phase;
  $('code-label').textContent = s.code;
  $('crew-count').textContent = `${s.players.filter(p => p.online).length} / ${s.max_players || 4}`;
  $('stage-label').textContent = s.stage ? `${String(s.stage).padStart(2, '0')} / ${String(s.stages).padStart(2, '0')}` : `— / ${String(s.stages).padStart(2, '0')}`;
  $('score-label').textContent = s.score.toLocaleString();
  const owned = ownedDials();
  if (!app.manualSelect || app.selected < 0) { if (!owned.includes(app.selected)) app.selected = owned.length ? owned[0] : 0; }
  window.ConfluxScene?.select(app.selected);
  if (app.lastRevision !== s.revision) { renderCrew(); renderChat(); renderLobby(); renderResult(); app.lastRevision = s.revision; }
  renderStation(); renderHotspots(); renderChips(); renderMessage(); renderTimer();
}
function renderTimer() {
  const s = S(); if (!s) return;
  const timed = ['playing', 'intermission'].includes(s.phase);
  const secs = timed ? Math.max(0, Math.ceil(s.paused ? s.seconds : (app.deadline - performance.now()) / 1000)) : 0;
  $('timer-label').textContent = timed ? fmtTime(secs) : '--:--';
  const urgent = s.phase === 'playing' && !s.paused && secs <= 10;
  $('timer-label').classList.toggle('urgent', urgent);
  const bar = $('timer-bar');
  bar.style.transform = `scaleX(${s.phase === 'playing' && s.duration ? Math.min(1, secs / s.duration) : 0})`;
  bar.classList.toggle('urgent', urgent);
  if (urgent && secs !== app.lastTick && secs > 0) { app.lastTick = secs; Sound.tick(); }
  if (s.phase === 'intermission') { const el = $('result-next'); if (el) el.textContent = `Next round in ${secs}s`; $('message-subtitle').textContent = `NEXT ROUND IN ${secs} SECONDS`; }
}
setInterval(renderTimer, 200);

function renderStation() {
  const s = S(), i = app.selected < 0 ? 0 : app.selected;
  const mine = s.owners[i] === s.you, next = (i + 1) % 4;
  $('station-name').textContent = NAMES[i];
  $('station-kicker').textContent = mine ? 'YOUR STATION' : 'INSPECTING';
  $('station-current').textContent = s.positions ? SYMBOLS[s.positions[i]] : '◇';
  $('station-target').textContent = s.target ? SYMBOLS[s.target[i]] : '◇';
  $('station-hud').classList.toggle('aligned', !!s.positions && s.positions[i] === s.target[i]);
  const owner = s.owners[i] ? ownerName(s.owners[i]) : 'OPEN';
  $('station-owner').textContent = mine ? 'YOUR CONTROL' : `CREW: ${owner.toUpperCase()}`;
  $('station-hud').style.setProperty('--own-color', COLORS[i]);
  $('rotate-left').disabled = $('rotate-right').disabled = !(playing() && mine);
  $('control-tip').innerHTML = mine
    ? `<b>+</b> here turns <b style="color:${COLORS[next]}">${NAMES[next]}</b> <b>−</b> (and vice versa).`
    : `${safe(owner)} controls ${NAMES[i]}. Coordinate in chat.`;
  $('cycle-station').style.visibility = ownedDials().length > 1 ? 'visible' : 'hidden';
  $('moves-label').textContent = s.moves ?? 0;
  $('par-label').textContent = s.par || '–';
  $('hint-button').disabled = !playing();
  $('hint-button').textContent = `HINT −${s.hint_penalty ?? 75}`;
}
function renderCrew() {
  const s = S();
  $('crew-list').innerHTML = s.players.map(p => {
    const dots = s.owners.map((o, i) => o === p.id ? `<i style="background:${COLORS[i]}" title="${NAMES[i]}"></i>` : '').join('');
    const status = !p.online ? 'OFFLINE' : p.bot ? 'AI CREW' : p.is_host ? 'HOST' : 'ONLINE';
    return `<div class="crew-person ${p.online ? '' : 'is-offline'}"><span class="crew-avatar">${p.bot ? '◆' : safe(p.name.slice(0, 1).toUpperCase())}</span><span class="crew-person-name">${safe(p.name)}${p.id === s.you ? ' (YOU)' : ''}<span class="crew-dots">${dots}</span></span><small class="${p.online ? '' : 'offline'}">${status}</small></div>`;
  }).join('');
}
function renderChat() {
  const s = S(), el = $('chat-log'), bottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 35;
  const lastId = s.chat.length ? s.chat[s.chat.length - 1].id : '';
  el.innerHTML = s.chat.map(m => `<div class="message ${safe(m.kind || (m.name === 'SYSTEM' ? 'system' : 'player'))}"><strong>${safe(m.name)}:</strong> ${safe(m.message)}</div>`).join('');
  if (bottom) el.scrollTop = el.scrollHeight;
  if (el.dataset.lastId && lastId !== el.dataset.lastId && $('comms').classList.contains('collapsed')) {
    const latest = s.chat[s.chat.length - 1];
    if (latest && latest.kind !== 'system') { $('unread-dot').classList.add('on'); if (latest.kind === 'hint' || latest.kind === 'player' || latest.kind === 'bot') toast(`${latest.name}: ${latest.message}`, 4200); }
  }
  el.dataset.lastId = lastId;
}
function renderLobby() {
  const s = S(), panel = $('lobby-panel');
  panel.classList.toggle('hidden', s.phase !== 'lobby');
  if (s.phase !== 'lobby') return;
  $('lobby-code').textContent = s.code;
  const seats = s.max_players || 4;
  const rows = s.players.map(p => {
    const dots = s.owners.map((o, i) => o === p.id ? `<i style="background:${COLORS[i]}" title="${NAMES[i]}"></i>` : '').join('');
    const tag = p.bot ? 'AI' : p.is_host ? 'HOST' : p.online ? 'READY' : 'OFFLINE';
    const remove = p.bot && isHost() ? `<button class="seat-remove" data-remove="${safe(p.id)}" type="button" aria-label="Remove ${safe(p.name)}">×</button>` : '';
    return `<div class="seat ${p.online ? '' : 'is-offline'}"><span class="seat-name">${p.bot ? '◆ ' : ''}${safe(p.name)}${p.id === s.you ? ' (you)' : ''}</span><span class="crew-dots">${dots}</span><small>${tag}</small>${remove}</div>`;
  });
  for (let i = s.players.length; i < seats; i++) rows.push('<div class="seat open"><span class="seat-name">Open seat</span><small>INVITE</small></div>');
  $('lobby-crew').innerHTML = rows.join('');
  const crew = s.players.filter(p => p.online).length;
  if (isHost()) {
    const canAdd = s.players.length < seats;
    $('lobby-actions').innerHTML = `<button class="primary-btn" id="start-button" type="button">${crew > 1 ? `START REACTOR · ${crew} CREW` : 'START SOLO'} <span>▶</span></button>${canAdd ? '<button class="secondary-btn" id="add-bot" type="button">+ ADD AI CREWMATE</button>' : ''}`;
    $('lobby-note').textContent = crew > 1
      ? 'Stations are split between the crew (colored dots). Each turn also moves the next station clockwise.'
      : 'Playing alone? You control all four stations — or add an AI crewmate to share the load.';
  } else {
    $('lobby-actions').innerHTML = '';
    const host = s.players.find(p => p.is_host);
    $('lobby-note').textContent = `Waiting for ${host ? host.name : 'the host'} to start the reactor…`;
  }
}
function renderResult() {
  const s = S(), panel = $('result-panel');
  const show = (s.phase === 'intermission' || s.phase === 'finished') && app.resultHiddenFor !== `${s.phase}:${s.stage}`;
  panel.classList.toggle('hidden', !show);
  if (!show) return;
  const last = s.history[s.history.length - 1];
  if (s.phase === 'intermission' && last) {
    $('result-kicker').textContent = `ROUND ${last.stage} OF ${s.stages}`;
    $('result-title').textContent = last.result === 'solved' ? 'CORE STABILIZED' : 'REACTOR OVERLOAD';
    panel.classList.toggle('failed', last.result !== 'solved');
    $('result-body').innerHTML = last.result === 'solved'
      ? `<div class="big-points">+${last.points.toLocaleString()}</div><div class="result-stats"><span>MOVES <b>${last.moves}</b> / PAR ${last.par}</span><span>TIME LEFT <b>${last.seconds_left}s</b></span><span>HINTS <b>${last.hints}</b></span></div>${last.moves === last.par && !last.hints ? '<div class="perfect">★ PERFECT ROUTE</div>' : ''}<p id="result-next" class="result-next"></p>`
      : `<div class="big-points">+0</div><p class="result-sub">Time ran out. The next round starts anyway — regroup in chat.</p><p id="result-next" class="result-next"></p>`;
    $('result-actions').innerHTML = '<button class="ghost-btn" data-close-result type="button">VIEW ARENA</button>';
  } else if (s.phase === 'finished') {
    const solved = s.history.filter(h => h.result === 'solved').length;
    const perfect = s.history.filter(h => h.result === 'solved' && h.moves === h.par && !h.hints).length;
    const rank = solved === 3 ? (perfect === 3 ? 'S · FLAWLESS SYNC' : perfect ? 'A · ELITE CREW' : 'B · STABLE CREW') : solved ? 'C · PARTIAL CONTAINMENT' : 'D · MELTDOWN';
    $('result-kicker').textContent = 'RUN COMPLETE';
    $('result-title').textContent = `${s.score.toLocaleString()} POINTS`;
    panel.classList.toggle('failed', solved === 0);
    $('result-body').innerHTML = `<div class="rank">RANK ${rank}</div><table class="history"><thead><tr><th>ROUND</th><th>RESULT</th><th>MOVES/PAR</th><th>POINTS</th></tr></thead><tbody>${s.history.map(h => `<tr class="${h.result}"><td>${h.stage}</td><td>${h.result === 'solved' ? '✓ STABLE' : '✕ EXPIRED'}</td><td>${h.result === 'solved' ? `${h.moves}/${h.par}` : '—'}</td><td>${h.points.toLocaleString()}</td></tr>`).join('')}</tbody></table>`;
    const host = s.players.find(p => p.is_host);
    $('result-actions').innerHTML = (isHost() ? '<button class="primary-btn" id="again-button" type="button">PLAY AGAIN <span>↻</span></button>' : `<p class="result-sub">Waiting for ${safe(host ? host.name : 'the host')} to start another run.</p>`)
      + '<div class="result-row"><button class="ghost-btn" id="share-result" type="button">COPY RESULT</button><button class="ghost-btn" data-close-result type="button">VIEW ARENA</button></div>';
  }
}
function renderMessage() {
  const s = S(), p = s.phase;
  const matched = s.positions && s.target ? s.positions.filter((x, i) => x === s.target[i]).length : 0;
  let msg = '', detail = '';
  if (p === 'lobby') { msg = 'AWAITING CREW · SHARE YOUR ROOM CODE'; detail = isHost() ? 'START SOLO OR WITH YOUR CREW' : 'THE HOST WILL START THE REACTOR'; }
  else if (p === 'playing') {
    if (s.paused) { msg = 'SIGNAL PAUSED · WAITING FOR CREW'; detail = 'THE CLOCK RESUMES WHEN A PLAYER RECONNECTS'; }
    else { msg = `${matched} / 4 RINGS ALIGNED`; detail = `MOVES ${s.moves} · PAR ${s.par} · EACH TURN SHIFTS THE NEXT STATION`; }
  } else if (p === 'intermission') { msg = s.result === 'solved' ? `CORE STABILIZED · +${s.last_score} POINTS` : 'REACTOR OVERLOADED · 0 POINTS'; detail = ''; }
  else { msg = `RUN COMPLETE · ${s.score.toLocaleString()} POINTS`; detail = isHost() ? 'PRESS PLAY AGAIN FOR ANOTHER RUN' : 'WAITING FOR THE HOST'; }
  $('round-message').textContent = msg;
  if (detail || p !== 'intermission') $('message-subtitle').textContent = detail;
}
function renderChips() {
  const s = S(), root = $('ring-chips');
  if (root.children.length !== 4) root.innerHTML = [0, 1, 2, 3].map(i => `<button class="ring-chip" type="button" data-dial="${i}" style="--ring-color:${COLORS[i]}"></button>`).join('');
  [...root.children].forEach((el, i) => {
    const has = !!s.positions, match = has && s.positions[i] === s.target[i], mine = s.owners[i] === s.you;
    el.classList.toggle('match', match); el.classList.toggle('selected', app.selected === i); el.classList.toggle('mine', mine);
    const owner = s.owners[i] ? ownerName(s.owners[i]) : '';
    el.innerHTML = `<small>${NAMES[i]}</small><span>${has ? SYMBOLS[s.positions[i]] : '·'}<em>→</em>${has ? SYMBOLS[s.target[i]] : '·'}</span><i>${match ? '✓' : mine ? 'YOU' : safe(owner.slice(0, 6).toUpperCase())}</i>`;
    el.setAttribute('aria-label', `${NAMES[i]}: ${has ? `current ${SYMBOLS[s.positions[i]]}, target ${SYMBOLS[s.target[i]]}${match ? ', aligned' : ''}` : 'idle'}; ${mine ? 'your station' : `controlled by ${owner || 'nobody'}`}`);
  });
}

/* ---------- arena overlays ---------- */
// Ring centres in artwork pixels, clockwise from top-left (matches station order).
const ART = {
  desktop: { w: 1125, h: 721, size: 270, rings: [[273, 181], [856, 182], [850, 519], [229, 521]] },
  mobile: { w: 941, h: 1700, size: 222, rings: [[232, 533], [720, 532], [715, 987], [226, 988]] },
};
function positionHotspots() {
  const parent = $('cinematic-view'), width = parent.clientWidth, height = parent.clientHeight;
  if (!width || !height) return;
  const art = window.matchMedia('(max-width:800px)').matches ? ART.mobile : ART.desktop;
  const s = Math.max(width / art.w, height / art.h), ox = (width - art.w * s) / 2, oy = (height - art.h * s) / 2;
  $('arena-hotspots').querySelectorAll('.ring-hotspot').forEach((el, i) => {
    const [x, y] = art.rings[i];
    el.style.left = `${ox + x * s}px`; el.style.top = `${oy + y * s}px`;
    el.style.setProperty('--hot-size', `${Math.max(64, Math.min(410, art.size * s))}px`);
  });
}
window.addEventListener('resize', positionHotspots);
function pulseHotspot(i, linked = false) {
  const el = $('arena-hotspots').querySelector(`[data-dial="${i}"]`); if (!el) return;
  const cls = linked ? 'pulse-linked' : 'pulse';
  el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls);
  setTimeout(() => el.classList.remove(cls), 700);
}
function floatNote(i, text) {
  const host = $('arena-hotspots').querySelector(`[data-dial="${i}"]`); if (!host) return;
  const note = document.createElement('span'); note.className = 'float-note'; note.textContent = text;
  host.appendChild(note); setTimeout(() => note.remove(), 1600);
}
function renderHotspots() {
  const s = S(), root = $('arena-hotspots');
  if (root.querySelectorAll('.ring-hotspot').length !== 4) {
    root.innerHTML = NAMES.map((name, i) => `<button class="ring-hotspot" type="button" data-dial="${i}" style="--ring-color:${COLORS[i]}"><span class="orbit-outline"></span><span class="rotor-indicator"></span><span class="ring-face"><b class="ring-current"></b><span class="ring-target"></span></span><span class="ring-label"></span></button>`).join('')
      + '<div class="core-surge"></div>';
    positionHotspots();
  }
  const linked = app.selected >= 0 ? (app.selected + 1) % 4 : -1;
  root.querySelectorAll('.ring-hotspot').forEach(el => {
    const i = Number(el.dataset.dial), has = !!s.positions;
    const matched = has && s.positions[i] === s.target[i], mine = s.owners[i] === s.you;
    el.classList.toggle('selected', app.selected === i); el.classList.toggle('match', matched);
    el.classList.toggle('linked', linked === i && s.phase === 'playing'); el.classList.toggle('mine', mine);
    el.classList.toggle('idle', !has);
    el.querySelector('.ring-current').textContent = has ? SYMBOLS[s.positions[i]] : '';
    el.querySelector('.ring-target').textContent = has ? (matched ? '✓ ALIGNED' : `TARGET ${SYMBOLS[s.target[i]]}`) : '';
    const owner = s.owners[i] ? ownerName(s.owners[i]) : '';
    el.querySelector('.ring-label').textContent = `${NAMES[i]}${linked === i && s.phase === 'playing' ? ' · LINKED' : mine ? ' · YOU' : owner ? ` · ${owner.toUpperCase()}` : ''}`;
    el.querySelector('.rotor-indicator').style.transform = `rotate(${(has ? s.positions[i] : 0) * 60}deg)`;
    el.setAttribute('aria-label', `Select ${NAMES[i]}${has ? `: current ${SYMBOLS[s.positions[i]]}, target ${SYMBOLS[s.target[i]]}` : ''}${mine ? ', your station' : ''}`);
  });
}

/* ---------- input ---------- */
function selectDial(i, manual = true) {
  if (!S() || !(i >= 0 && i < 4)) return;
  app.selected = i; app.manualSelect = manual;
  window.ConfluxScene?.select(i);
  renderStation(); renderHotspots(); renderChips();
}
function cycleOwned(step = 1) {
  const options = ownedDials(); if (!options.length) return;
  const current = options.indexOf(app.selected);
  selectDial(options[(current + step + options.length) % options.length]);
}
function move(direction) {
  const s = S(); if (!s || app.selected < 0) return;
  if (s.phase !== 'playing') { toast(s.phase === 'lobby' ? 'Start the reactor first.' : 'Wait for the next round.'); return; }
  if (s.paused) { toast('Clock paused — waiting for crew.'); return; }
  if (s.owners[app.selected] !== s.you) {
    const own = ownedDials();
    toast(`${NAMES[app.selected]} belongs to ${ownerName(s.owners[app.selected])}. ${own.length ? `Yours: ${own.map(i => NAMES[i]).join(', ')}.` : ''}`);
    return;
  }
  send({ type: 'move', dial: app.selected, direction });
}
function toggleChat(force) {
  const pane = $('comms'), open = typeof force === 'boolean' ? force : pane.classList.contains('collapsed');
  pane.classList.toggle('collapsed', !open); $('toggle-comms').setAttribute('aria-expanded', String(open));
  if (open) { $('unread-dot').classList.remove('on'); setTimeout(() => $('chat-input').focus(), 50); }
}
function openHelp() { $('help-panel').classList.remove('hidden'); setTimeout(() => $('help-ok').focus(), 30); }
function closeHelp() { $('help-panel').classList.add('hidden'); store.set('localStorage', 'conflux-help-seen', '1'); }
async function copyInvite() {
  const url = invite(app.state?.code || app.roomCode);
  try { await navigator.clipboard.writeText(url); toast('Invite link copied — send it to your crew.'); }
  catch { window.prompt('Copy the room invitation:', url); }
}
async function shareResult() {
  const s = S(); if (!s) return;
  const lines = s.history.map(h => `R${h.stage} ${h.result === 'solved' ? `✓ ${h.moves}/${h.par} moves` : '✕'} +${h.points}`);
  const text = `CONFLUX CORE — our crew scored ${s.score.toLocaleString()} points!\n${lines.join('\n')}\nPlay with us: ${app.demo ? location.href : location.origin}`;
  try { await navigator.clipboard.writeText(text); toast('Result copied to clipboard.'); } catch { window.prompt('Copy your result:', text); }
}

$('create-room').addEventListener('click', () => createRoom(false));
$('quick-play').addEventListener('click', () => createRoom(true));
$('join-room').addEventListener('click', joinFromInput);
$('room-code-input').addEventListener('keydown', e => { if (e.key === 'Enter') joinFromInput(); });
$('room-code-input').addEventListener('input', e => { e.target.value = e.target.value.replace(/[^A-Z0-9]/gi, '').toUpperCase(); });
$('player-name').addEventListener('keydown', e => { if (e.key === 'Enter') ($('room-code-input').value.trim().length === 5 ? joinFromInput() : createRoom(false)); });
$('open-help-landing').addEventListener('click', openHelp);
$('open-help').addEventListener('click', openHelp);
$('close-help').addEventListener('click', closeHelp);
$('help-ok').addEventListener('click', closeHelp);
$('help-panel').addEventListener('click', e => { if (e.target === $('help-panel')) closeHelp(); });
$('copy-link').addEventListener('click', copyInvite);
$('lobby-copy').addEventListener('click', copyInvite);
if (navigator.share) {
  $('lobby-share').classList.remove('hidden');
  $('lobby-share').addEventListener('click', () => navigator.share({ title: 'CONFLUX CORE', text: `Join my reactor crew — room ${app.state?.code}`, url: invite(app.state?.code || app.roomCode) }).catch(() => {}));
}
$('leave-room').addEventListener('click', () => { if (!S() || S().phase === 'lobby' || S().phase === 'finished' || window.confirm('Leave this run? Your stations will pass to your crew.')) leave(); });
$('net-retry').addEventListener('click', () => { app.retry = 0; setNet('RECONNECTING…'); openSocket(); });
$('toggle-sound').addEventListener('click', () => { const on = Sound.toggle(); $('toggle-sound').classList.toggle('muted', !on); $('toggle-sound').setAttribute('aria-pressed', String(on)); toast(on ? 'Sound on' : 'Sound off', 1200); });
$('toggle-sound').classList.toggle('muted', !Sound.on);
$('reset-camera').addEventListener('click', () => { window.ConfluxScene?.resetCamera(); toast('Camera reset.', 1200); });
$('toggle-view').addEventListener('click', () => {
  app.nativeView = !app.nativeView;
  document.body.classList.toggle('native-mode', app.nativeView);
  $('toggle-view').textContent = app.nativeView ? 'ART' : '3D';
  $('toggle-view').classList.toggle('active', app.nativeView);
  $('toggle-view').title = app.nativeView ? 'Show cinematic artwork' : 'Show native 3D geometry';
  toast(app.nativeView ? 'Native 3D view — drag to orbit' : 'Cinematic arena view', 1800);
});
$('toggle-comms').addEventListener('click', () => toggleChat());
$('close-comms').addEventListener('click', () => toggleChat(false));
$('chat-form').addEventListener('submit', e => { e.preventDefault(); const field = $('chat-input'), message = field.value.trim(); if (!message) return; send({ type: 'chat', message }); field.value = ''; });
$('rotate-left').addEventListener('click', () => move(-1));
$('rotate-right').addEventListener('click', () => move(1));
$('cycle-station').addEventListener('click', () => cycleOwned(1));
$('hint-button').addEventListener('click', () => { send({ type: 'hint' }); });
$('arena-hotspots').addEventListener('click', e => { const h = e.target.closest('.ring-hotspot'); if (h) selectDial(Number(h.dataset.dial)); });
$('ring-chips').addEventListener('click', e => { const c = e.target.closest('.ring-chip'); if (c) selectDial(Number(c.dataset.dial)); });
$('lobby-actions').addEventListener('click', e => {
  if (e.target.closest('#start-button')) send({ type: 'start' });
  if (e.target.closest('#add-bot')) send({ type: 'add_bot' });
});
$('lobby-crew').addEventListener('click', e => { const b = e.target.closest('[data-remove]'); if (b) send({ type: 'remove_bot', id: b.dataset.remove }); });
$('result-actions').addEventListener('click', e => {
  if (e.target.closest('#again-button')) send({ type: 'start' });
  if (e.target.closest('#share-result')) shareResult();
  if (e.target.closest('[data-close-result]')) { app.resultHiddenFor = `${S().phase}:${S().stage}`; renderResult(); }
});
window.addEventListener('conflux-select', e => selectDial(e.detail.dial));
window.addEventListener('online', reconnectNow);
document.addEventListener('visibilitychange', () => { if (!document.hidden) reconnectNow(); });
document.addEventListener('keydown', e => {
  if (!$('help-panel').classList.contains('hidden')) { if (e.key === 'Escape') closeHelp(); return; }
  if ($('game').classList.contains('hidden') || e.metaKey || e.ctrlKey || e.altKey) return;
  const tag = document.activeElement?.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') { if (e.key === 'Escape') { document.activeElement.blur(); toggleChat(false); } return; }
  const k = e.key.toLowerCase();
  if (e.key === 'ArrowLeft' || k === 'a') { e.preventDefault(); move(-1); }
  else if (e.key === 'ArrowRight' || k === 'd') { e.preventDefault(); move(1); }
  else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); cycleOwned(e.key === 'ArrowUp' ? -1 : 1); }
  else if (['1', '2', '3', '4'].includes(e.key)) selectDial(Number(e.key) - 1);
  else if (k === 'c') { e.preventDefault(); toggleChat(); }
  else if (k === 'h') send({ type: 'hint' });
  else if (k === 'm') $('toggle-sound').click();
  else if (e.key === '?' || e.key === '/') openHelp();
  else if (e.key === 'Escape') toggleChat(false);
});

/* ---------- offline practice (no server) ---------- */
function demoSnapshot() { return JSON.parse(JSON.stringify(app.demo.state)); }
function demoPush() { app.demo.state.revision++; app.demo.state.seconds = demoSeconds(); applyState(demoSnapshot()); }
function demoSeconds() {
  const d = app.demo, s = d.state;
  if (s.phase === 'playing') return Math.max(0, (d.endAt - performance.now()) / 1000);
  if (s.phase === 'intermission') return Math.max(0, (d.nextAt - performance.now()) / 1000);
  return 0;
}
function demoLog(message, name = 'SYSTEM', kind = 'system') { const c = app.demo.state.chat; c.push({ id: Math.random().toString(16).slice(2), name, message, kind }); c.splice(0, Math.max(0, c.length - 40)); }
function demoStage(stage) {
  const d = app.demo, s = d.state, p = L.newPuzzle(stage);
  Object.assign(s, { phase: 'playing', stage, target: p.target, positions: p.positions, par: p.par, moves: 0, hints: 0, result: '', last_score: 0, last_action: null, duration: L.STAGE_SECONDS[stage - 1], paused: false });
  d.endAt = performance.now() + s.duration * 1000;
  demoLog(`Round ${stage} is live — par ${p.par} moves. Stabilize the core!`);
  demoPush();
}
function demoFinish(won) {
  const s = app.demo.state, left = demoSeconds();
  s.last_score = L.roundPoints(won, left, s.moves, s.par, s.hints); s.score += s.last_score; s.result = won ? 'solved' : 'expired';
  s.history.push({ stage: s.stage, result: s.result, points: s.last_score, moves: s.moves, par: s.par, hints: s.hints, seconds_left: won ? Math.floor(left) : 0 });
  demoLog(won ? `Core stabilized! +${s.last_score} points.` : 'Time expired. The core lost coherence.');
  if (s.stage >= s.stages) { s.phase = 'finished'; demoLog(`Run complete. Final score ${s.score}.`); }
  else { s.phase = 'intermission'; app.demo.nextAt = performance.now() + 6000; }
  demoPush();
}
function startDemo() {
  resetSession();
  const you = 'practice-you';
  app.demo = { clock: null, endAt: 0, nextAt: 0, lastHint: 0, state: {
    type: 'state', protocol: 2, code: 'SOLO', phase: 'lobby', you, session: null, host: you, revision: 0,
    players: [{ id: you, name: (store.get('localStorage', 'conflux-name') || 'YOU').slice(0, 18), online: true, bot: false, is_host: true }],
    max_players: 1, owners: [you, you, you, you], stations: L.STATIONS, symbols: L.SYMBOLS, target: null, positions: null,
    stage: 0, stages: 3, seconds: 0, duration: 0, paused: false, score: 0, last_score: 0, moves: 0, par: 0, hints: 0,
    hint_penalty: L.HINT_PENALTY, result: '', history: [], last_action: null,
    chat: [{ id: 'intro', name: 'SYSTEM', message: 'Offline practice: you control all four stations. Online rooms need the game server.', kind: 'system' }],
  } };
  app.roomCode = 'SOLO';
  $('demo-ribbon').classList.remove('hidden'); showGame();
  demoStage(1);
  app.demo.clock = setInterval(() => {
    const d = app.demo; if (!d) return; const s = d.state;
    if (s.phase === 'playing' && performance.now() >= d.endAt) demoFinish(false);
    else if (s.phase === 'intermission' && performance.now() >= d.nextAt) demoStage(s.stage + 1);
  }, 200);
}
function demoHandle(packet) {
  const d = app.demo, s = d.state;
  if (packet.type === 'move' && s.phase === 'playing') {
    s.last_action = { by: s.you, dial: packet.dial, direction: packet.direction, revision: s.revision + 1 };
    s.positions = L.rotate(s.positions, packet.dial, packet.direction); s.moves++;
    if (s.positions.every((x, i) => x === s.target[i])) { s.revision++; demoFinish(true); return; }
    demoPush();
  } else if (packet.type === 'hint' && s.phase === 'playing') {
    if (performance.now() - d.lastHint < 4000) { toast('Hint systems recharging…'); return; }
    d.lastHint = performance.now();
    const plan = L.solve(s.positions, s.target), [dial, dir] = plan[0];
    s.hints++; demoLog(`HINT (−${L.HINT_PENALTY}): ${L.STATIONS[dial]} ${dir > 0 ? '+' : '−'}. ${plan.length} move${plan.length === 1 ? '' : 's'} from stable.`, 'SYSTEM', 'hint');
    demoPush();
  } else if (packet.type === 'chat') {
    demoLog(String(packet.message).slice(0, 180), s.players[0].name, 'player'); demoPush();
  } else if (packet.type === 'start' && (s.phase === 'finished' || s.phase === 'lobby')) {
    Object.assign(s, { score: 0, last_score: 0, history: [], chat: [] }); demoStage(1);
  } else if (packet.type === 'add_bot') {
    toast('AI crewmates need the online server.');
  }
}

(function boot() {
  $('player-name').value = store.get('localStorage', 'conflux-name') || '';
  const params = new URLSearchParams(location.search);
  if (window.CONFLUX_OFFLINE === true || params.get('demo') === '1') { startDemo(); return; }
  const code = params.get('room');
  if (code && /^[a-z0-9]{5}$/i.test(code)) {
    const name = $('player-name').value.trim();
    if (name && store.get('sessionStorage', `conflux-token-${code.toUpperCase()}`)) { connect(code, name); return; }  // page refresh: rejoin same seat
    $('room-code-input').value = code.toUpperCase();
    toast('Invitation loaded — enter your callsign and press JOIN.', 5000);
    $('player-name').focus();
  }
})();
