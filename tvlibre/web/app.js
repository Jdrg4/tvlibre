/* tvlibre: interfaz para el control remoto. ES5 a propósito (navegadores de TV de 2014). */
(function () {
  'use strict';

  var KEY = {LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, ENTER: 13};
  var BACK = [8, 27, 461, 10009];
  var CANAL_KEYS = [71, 404];  // G y el botón verde del control: abre el canal de la tarjeta enfocada
  var REFRESH_MS = 60000;

  var $ = function (id) { return document.getElementById(id); };
  var data = null;          // última respuesta de /api/home
  var view = null;          // página de un canal abierta: {slug, data} (null = portada)
  var homeDirty = false;    // se siguió o dejó de seguir algo desde la página de un canal
  var rows = [];            // [{name, el, items}] filas navegables, en orden vertical
  var focus = {row: 0, col: 0};
  var brightness = 100;
  var player = null;        // estado del reproductor mientras está abierto
  var retryTimer = null;    // un solo reintento pendiente aunque fallen varias cargas
  var discAsked = false;    // ya se volvió a pedir la portada para traer lo que se busca aparte

  // ---------- utilidades ----------
  function xhr(method, url, body, cb) {
    var x = new XMLHttpRequest();
    x.open(method, url);
    x.timeout = 30000;
    if (body) { x.setRequestHeader('Content-Type', 'application/json'); }
    x.onload = function () {
      if (!cb) { return; }
      if (x.status >= 200 && x.status < 300) { cb(null, x.responseText ? JSON.parse(x.responseText) : null); }
      else { cb(new Error(x.status === 404 ? 'no existe' : 'HTTP ' + x.status)); }
    };
    x.onerror = x.ontimeout = function () { if (cb) { cb(new Error('sin conexión')); } };
    x.send(body ? JSON.stringify(body) : null);
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c];
    });
  }
  function pad(n) { return n < 10 ? '0' + n : '' + n; }
  function hms(s) {
    s = Math.max(0, Math.floor(s || 0));
    return Math.floor(s / 3600) + ':' + pad(Math.floor(s / 60) % 60) + ':' + pad(s % 60);
  }
  function parseIso(iso) {
    var m = /^(\d+)-(\d+)-(\d+)T(\d+):(\d+):(\d+)/.exec(iso || '');
    return m ? Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]) : 0;
  }
  function relDay(iso) {
    var d = new Date(parseIso(iso)), now = new Date();
    var a = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    var b = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    var days = Math.round((b - a) / 86400000);
    if (days >= 730) { return 'hace ' + Math.floor(days / 365) + ' años'; }
    if (days >= 60) { return 'hace ' + Math.floor(days / 30) + ' meses'; }
    return days <= 0 ? 'hoy' : days === 1 ? 'ayer' : 'hace ' + days + ' días';
  }
  function since(iso) {
    if (!iso) { return ''; }
    var min = Math.max(0, Math.round((new Date().getTime() - parseIso(iso)) / 60000));
    return min < 60 ? 'hace ' + min + ' min' : 'hace ' + Math.floor(min / 60) + ' h ' + (min % 60) + ' min';
  }
  function many(n) {
    if (n >= 1000000) { return (Math.round(n / 100000) / 10).toString().replace('.', ',') + ' M'; }
    if (n >= 1000) { return (Math.round(n / 100) / 10).toString().replace('.', ',') + ' mil'; }
    return '' + n;
  }
  function viewers(n) {
    if (n == null) { return ''; }
    return many(n) + ' espectadores';
  }
  function img(url, fresh) {
    if (!url) { return ''; }
    var u = '/img?u=' + encodeURIComponent(url);
    if (fresh) { u += '&_=' + Math.floor(new Date().getTime() / 300000); }
    return 'background-image:url(\'' + u + '\')';
  }
  function store(k, v) {
    try { if (v === undefined) { return window.localStorage.getItem(k); } window.localStorage.setItem(k, v); } catch (e) { return null; }
    return null;
  }
  function inArr(a, v) { for (var i = 0; i < a.length; i++) { if (a[i] === v) { return true; } } return false; }
  function nameOf(it) { return it.name || it.channel; }
  function join(parts) {
    var out = [];
    for (var i = 0; i < parts.length; i++) { if (parts[i]) { out.push(parts[i]); } }
    return out.join(' · ');
  }

  // ---------- brillo ----------
  function setBrightness(v, save) {
    brightness = Math.max(30, Math.min(100, v));
    $('dim').style.opacity = String((100 - brightness) / 100);
    $('brilloVal').innerHTML = brightness;
    $('pBri').innerHTML = brightness + '%';
    if (save) { xhr('POST', '/api/state', {brightness: brightness}); }
  }

  // ---------- tarjetas ----------
  function liveCard(it) {
    return '<div class="card live" data-id="' + esc(it.id) + '" style="' + img(it.thumb, true) + '">' +
      '<span class="badge">● EN VIVO</span><div class="shade">' +
      '<div class="n">' + esc(nameOf(it)) + '</div>' +
      '<div class="t">' + esc(it.title) + '</div>' +
      '<div class="t">' + esc(join([viewers(it.viewers), it.category, since(it.started_at)])) + '</div></div></div>';
  }
  function vodCard(it) {
    var prog = it.resume_s && it.duration_s ? '<div class="prog" style="width:' + Math.min(100, 100 * it.resume_s / it.duration_s) + '%"></div>' : '';
    return '<div class="card vod" data-id="' + esc(it.id) + '">' +
      '<div class="th" style="' + img(it.thumb) + '"><span class="dur">' + hms(it.duration_s) + '</span>' + prog + '</div>' +
      '<div class="t">' + esc(it.title) + '</div>' +
      '<div class="m">' + esc(join([view ? '' : nameOf(it), relDay(it.started_at)])) + '</div></div>';
  }
  function discCard(it) {
    return '<div class="card vod disc" data-id="' + esc(it.id) + '">' +
      '<div class="th" style="' + img(it.thumb, true) + '"><span class="badge">● EN VIVO</span>' +
      '<span class="dur">' + esc(many(it.viewers || 0)) + '</span></div>' +
      '<div class="t">' + esc(it.title) + '</div>' +
      '<div class="m"><b>' + esc(nameOf(it)) + '</b>' + (it.category ? ' · ' + esc(it.category) : '') + '</div></div>';
  }

  // ---------- portada y página de canal: mismas filas, distinto contenido ----------
  function sections() {
    if (view) {
      var p = view.data;
      return [
        {name: 'live', title: 'En vivo ahora', items: p.live ? [p.live] : [], card: liveCard, per: 2},
        {name: 'vods', title: 'Streams anteriores', items: p.vods, card: vodCard, per: 4,
          empty: 'Este canal no tiene streams anteriores guardados.'},
        {name: 'hl', title: 'Destacados', items: p.highlights, card: vodCard, per: 4},
        {name: 'none', items: []}];
    }
    return [
      {name: 'live', title: 'En vivo ahora', items: data.live, card: liveCard, per: 2},
      {name: 'vods', title: 'Streams anteriores', items: data.vods, card: vodCard, per: 4,
        empty: (data.channels || []).length ? 'No hay streams anteriores.' : 'Todavía no sigues a nadie: busca un canal arriba.'},
      {name: 'top', title: 'Lo más visto ahora', items: data.top || [], card: discCard, per: 4},
      {name: 'disc', title: 'También en vivo', items: data.discover || [], card: discCard, per: 4}];
  }

  function focusedId() {
    var r = rows[focus.row];
    return r && r.items[focus.col] ? r.items[focus.col].id : null;
  }

  function drawHead() {
    $('chHead').style.display = view ? '' : 'none';
    if (!view) { return; }
    var c = view.data.channel;
    $('chAv').setAttribute('style', img(c.avatar));
    $('chName').innerHTML = esc(c.name);
    var last = view.data.live ? '' : (c.last_live ? 'último directo ' + relDay(c.last_live) : '');
    $('chMeta').innerHTML = esc(join([c.followers != null ? many(c.followers) + ' seguidores' : '', c.category, last]));
    $('chDesc').innerHTML = esc(c.description);
    $('chFollow').innerHTML = c.following ? '✓ Siguiendo' : '+ Seguir';
    $('chFollow').className = 'pill' + (c.following ? ' on' : '');
  }

  function render(keepId) {
    var secs = sections(), i, j, h, s, el;
    drawHead();
    rows = [{name: 'chan', el: null, items: [{id: '__canales'}]}, {name: 'bri', el: null, items: [{id: '__brillo'}]}];
    if (view) { rows.push({name: 'follow', el: null, items: [{id: '__seguir'}]}); }
    for (i = 0; i < secs.length; i++) {
      s = secs[i];
      el = $('row' + i);
      h = '';
      for (j = 0; j < s.items.length; j++) { h += s.card(s.items[j]); }
      el.innerHTML = h || (s.empty ? '<div class="empty">' + esc(s.empty) + '</div>' : '');
      el.style.webkitTransform = el.style.transform = '';
      $('sec' + i).style.display = h || s.empty ? '' : 'none';
      $('sec' + i).getElementsByTagName('h3')[0].innerHTML = esc(s.title || '');
      if (s.items.length) { rows.push({name: s.name, el: el, items: s.items, per: s.per}); }
    }
    showMsg(view ? [] : data.errors);
    $('hint').innerHTML = view ? 'OK ver · Atrás volver a la portada' : 'OK ver · verde o G: abrir el canal · ↑ buscar canal';

    var placed = false;
    if (keepId) {
      for (var r = 0; r < rows.length && !placed; r++) {
        for (var c = 0; c < rows[r].items.length; c++) {
          if (rows[r].items[c].id === keepId) { focus = {row: r, col: c}; placed = true; break; }
        }
      }
    }
    if (!placed) {
      // primer arranque: la primera fila de tarjetas (el directo si hay); sin tarjetas, el buscador
      var first = view ? 3 : 2;
      focus = {row: rows.length > first ? first : 0, col: 0};
    }
    applyFocus();
  }

  function showMsg(errors) {
    $('msg').innerHTML = errors && errors.length ? 'No se pudo consultar: ' + esc(errors.join(' · ')) : '';
  }

  function applyFocus(noScroll) {
    var all = document.querySelectorAll('.focus'), i;
    for (i = 0; i < all.length; i++) { all[i].className = all[i].className.replace(/\s*\bfocus\b/g, ''); }
    var row = rows[focus.row];
    if (!row) { return; }
    if (row.name === 'chan') { $('canales').className += ' focus'; scrollHome(0); return; }
    if (row.name === 'bri') { $('brillo').className += ' focus'; scrollHome(0); return; }
    if (row.name === 'follow') { $('chFollow').className += ' focus'; scrollHome(0); return; }
    var card = row.el.children[focus.col];
    if (!card) { return; }
    card.className += ' focus';
    // 720 px no dan para todas las filas: la página sube hasta que la fila enfocada queda entera a la vista
    var sec = row.el.parentNode.parentNode;
    scrollHome(Math.max(0, sec.offsetTop + sec.offsetHeight - 700));
    if (noScroll) { return; }
    // desplaza la fila para que la tarjeta enfocada quede a la vista
    var off = Math.max(0, card.offsetLeft - row.el.offsetLeft - 40);
    var max = Math.max(0, row.el.scrollWidth - 1200);
    off = Math.min(off, max);
    row.el.style.webkitTransform = 'translateX(-' + off + 'px)';
    row.el.style.transform = 'translateX(-' + off + 'px)';
  }
  function scrollHome(y) {
    $('home').style.webkitTransform = 'translateY(-' + y + 'px)';
    $('home').style.transform = 'translateY(-' + y + 'px)';
  }

  function loadHome(keepId) {
    xhr('GET', '/api/home', null, function (err, d) {
      if (err) {
        $('msg').innerHTML = 'No se pudo cargar la portada (' + esc(err.message) + '). Reintentando…';
        clearTimeout(retryTimer);
        retryTimer = setTimeout(function () { loadHome(keepId); }, 10000);
        return;
      }
      data = d;
      setBrightness(d.brightness, false);
      if (!player && !view) { render(keepId); }
      // "Lo más visto" y "También en vivo" se buscan aparte: en el primer arranque llegan unos segundos después
      if (!discAsked && !(d.top || []).length && !(d.discover || []).length) {
        discAsked = true;
        setTimeout(function () { if (!player && !view && !chan) { loadHome(focusedId()); } }, 8000);
      }
    });
  }

  // ---------- página de un canal cualquiera ----------
  function openChannel(slug) {
    if (!slug) { return; }
    $('msg').innerHTML = 'Abriendo ' + esc(slug) + '…';
    xhr('GET', '/api/channel/' + encodeURIComponent(slug), null, function (err, d) {
      if (err) { $('msg').innerHTML = 'No se pudo abrir el canal ' + esc(slug) + ' (' + esc(err.message) + ').'; return; }
      $('msg').innerHTML = '';
      var fresh = !view;
      view = {slug: slug, data: d};
      if (player) { return; }
      // la página es un paso más en el historial: Atrás vuelve a la portada
      try { if (fresh) { history.pushState({canal: 1}, ''); } } catch (e) { /* sin historial: Atrás por tecla sigue cerrando */ }
      render(null);
    });
  }
  function reloadChannel(keepId) {
    var slug = view.slug;
    xhr('GET', '/api/channel/' + encodeURIComponent(slug), null, function (err, d) {
      if (err || !view || view.slug !== slug) { return; }
      view.data = d;
      if (!player) { render(keepId); }
    });
  }
  function closeChannel() {
    var dirty = homeDirty;
    view = null;
    homeDirty = false;
    scrollHome(0);
    if (data) { render(null); }
    if (dirty || !data) { loadHome(null); }
  }
  function toggleFollowView() {
    var c = view.data.channel, on = !c.following;
    xhr('POST', '/api/channels', {platform: 'twitch', slug: c.slug, follow: on}, function (err) {
      if (err) { $('msg').innerHTML = 'No se pudo guardar (' + esc(err.message) + ').'; return; }
      c.following = on;
      homeDirty = true;
      drawHead();
      applyFocus();
    });
  }

  function homeKey(k) {
    var row = rows[focus.row];
    if (!row) { return; }
    if (k === KEY.DOWN && focus.row < rows.length - 1) {
      focus.row++; focus.col = Math.min(focus.col, rows[focus.row].items.length - 1);
    } else if (k === KEY.UP && focus.row > 0) {
      focus.row--; focus.col = Math.min(focus.col, rows[focus.row].items.length - 1);
    } else if (row.name === 'bri' && (k === KEY.LEFT || k === KEY.RIGHT)) {
      setBrightness(brightness + (k === KEY.RIGHT ? 10 : -10), true);
    } else if (k === KEY.LEFT && focus.col > 0) {
      focus.col--;
    } else if (k === KEY.RIGHT && focus.col < row.items.length - 1) {
      focus.col++;
    } else if (k === KEY.ENTER && row.name === 'chan') {
      openChan();
      return;
    } else if (k === KEY.ENTER && row.name === 'follow') {
      toggleFollowView();
      return;
    } else if (k === KEY.ENTER && row.name !== 'bri') {
      openPlayer(row.items[focus.col]);
      return;
    } else if (inArr(CANAL_KEYS, k) && row.el && !view) {
      openChannel(row.items[focus.col].channel);
      return;
    }
    applyFocus();
  }

  // ---------- reproductor ----------
  var v = $('v');

  function quality() {
    var q = store('tvl_q');
    if (q === '720' || q === '1080') { return +q; }
    return data && data.default_quality === 720 ? 720 : 1080;
  }

  function showBar() {
    $('bar').className = '';
    clearTimeout(player.barTimer);
    player.barTimer = setTimeout(function () { if (player && !v.paused) { $('bar').className = 'hidden'; } }, 4000);
    drawBar();
  }
  function drawBar() {
    if (!player) { return; }
    var it = player.item, t = player.target != null ? player.target : v.currentTime;
    if (it.kind === 'live') {
      $('pTime').innerHTML = '● EN VIVO · ' + quality() + 'p' + (v.paused ? ' · en pausa' : '');
      $('pFill').style.width = '100%';
    } else {
      var d = isFinite(v.duration) && v.duration ? v.duration : (it.duration_s || 0);
      var mu = TVL.mutedUntil(player.muted, t);
      $('pTime').innerHTML = hms(t) + ' / ' + hms(d) + ' · ' + quality() + 'p' + (v.paused ? ' · en pausa' : '') +
        (mu !== null ? ' · Twitch silenció este tramo hasta ' + hms(mu) : '');
      $('pFill').style.width = (d ? Math.min(100, 100 * t / d) : 0) + '%';
    }
  }

  function saveResume() {
    if (!player || player.item.kind !== 'vod' || !player.started) { return; }
    xhr('POST', '/api/resume', {id: player.item.id, position_s: Math.floor(v.currentTime),
      duration_s: player.item.duration_s || Math.floor(v.duration || 0)});
  }

  // vigilante: si el video lleva STUCK_S segundos sin avanzar (y nadie lo pausó) se vuelve a pedir. Twitch mete
  // anuncios a mitad del directo con un corte de formato que el reproductor de la TV a veces no sabe pasar.
  var STUCK_S = 12, RETRY_MAX = 5;
  function restartPlayer() {
    if (!player) { return; }
    start(player.item.kind === 'vod' ? Math.floor(player.lastT || 0) : 0);
  }
  function watchdog() {
    if (!player) { return; }
    if (!player.started || v.paused || player.target != null) { player.stuck = 0; return; }
    if (v.currentTime !== player.lastT) {
      player.lastT = v.currentTime;
      player.stuck = 0;
      player.good += 2;
      if (player.good >= 60) { player.retries = 0; }  // un minuto bien: vuelve a tener todos los reintentos
      return;
    }
    player.stuck += 2;
    if (player.stuck >= STUCK_S && player.retries < RETRY_MAX) {
      player.retries++;
      player.stuck = player.good = 0;
      restartPlayer();
    }
  }

  function start(seekTo) {
    $('loading').style.display = 'block';
    $('perr').style.display = 'none';
    player.started = false;
    player.seekTo = seekTo || 0;
    v.onplaying = function () {
      $('loading').style.display = 'none';
      if (!player.started && seekTo) { v.currentTime = seekTo; }
      player.started = true;
      showBar();
    };
    v.onwaiting = function () { $('loading').style.display = 'block'; };
    v.onerror = function () {
      // un tropiezo (corte de red, servidor reiniciado, cambio a anuncio) se arregla volviendo a pedir el video
      if (player.retries < RETRY_MAX) {
        var p = player;
        p.retries++;
        p.stuck = 0;
        setTimeout(function () { if (player === p) { restartPlayer(); } }, 3000);
        return;
      }
      $('loading').style.display = 'none';
      $('perr').innerHTML = 'No se pudo reproducir (código ' + (v.error ? v.error.code : '?') + '). Atrás para volver.';
      $('perr').style.display = 'block';
    };
    v.src = '/play/' + encodeURIComponent(player.item.id) + '.m3u8?q=' + quality();
    v.load();
    v.play();
  }

  // ---------- chat de solo lectura: columna a la derecha que se muestra u oculta ----------
  var CHAT_KEYS = [67, 403];  // C y el botón rojo del control
  var COLOR_RE = /^#[0-9a-fA-F]{6}$/;
  var chatOn = store('tvl_chat') !== '0';

  // texto escapado y emotes/emojis como imágenes (la TV no trae fuente de emojis)
  function chatBody(m) {
    if (!m.parts) { return esc(m.text); }
    var h = '', i, p;
    for (i = 0; i < m.parts.length; i++) {
      p = m.parts[i];
      h += p.e ? '<img class="em" src="/img?u=' + encodeURIComponent(p.e) + '">' : esc(p.t);
    }
    return h;
  }
  function drawChat() {
    var h = '', s = player.chat.shown, i, m;
    for (i = Math.max(0, s.length - 18); i < s.length; i++) {
      m = s[i];
      h += '<div class="cl"><b style="color:' + (COLOR_RE.test(m.color || '') ? m.color : '#9aa0ff') + '">' +
        esc(m.user) + '</b> ' + chatBody(m) + '</div>';
    }
    $('chatList').innerHTML = h;
  }
  function chatTick() {
    if (!player || !chatOn || player.chatBusy) { return; }
    var it = player.item, st = player.chat, pos;
    if (it.kind === 'live') {
      if (++player.chatN % 3) { return; }  // en vivo, cada 3 s
    } else {
      if (!player.started) { return; }
      pos = player.target != null ? player.target : v.currentTime;
      if (TVL.chatJump(st, pos)) { st = player.chat = TVL.chatReset(); drawChat(); }
      if (TVL.chatDue(st, pos)) { drawChat(); }
      if (!TVL.chatNeedsFetch(st, pos)) { return; }
    }
    player.chatBusy = true;
    var from = it.kind === 'live' ? 0 : Math.floor(st.until >= 0 ? st.until : pos);
    xhr('GET', '/api/chat/' + encodeURIComponent(it.id) + '?t=' + from, null, function (err, d) {
      if (!player || player.item !== it) { return; }
      player.chatBusy = false;
      if (err) { return; }  // el chat nunca molesta al video: se reintenta en el siguiente ciclo
      if (it.kind === 'live') {
        if (TVL.chatAddLive(player.chat, d.messages)) { drawChat(); }
      } else if (player.chat === st) {
        TVL.chatAddVod(st, d);
      }
    });
  }
  function toggleChat() {
    chatOn = !chatOn;
    store('tvl_chat', chatOn ? '1' : '0');
    $('chat').style.display = chatOn ? 'block' : 'none';
    $('player').className = chatOn ? 'conchat' : '';
    player.chat = TVL.chatReset();
    drawChat();
    showBar();
  }

  function openPlayer(it) {
    player = {item: it, target: null, seekTimer: null, barTimer: null, lastKey: 0, lastCode: 0, repeat: 0, started: false,
      muted: [], chat: TVL.chatReset(), chatN: 0, chatBusy: false, lastT: -1, stuck: 0, good: 0, retries: 0};
    player.watchTimer = setInterval(watchdog, 2000);
    $('chat').style.display = chatOn ? 'block' : 'none';
    $('player').className = chatOn ? 'conchat' : '';
    $('chatList').innerHTML = '';
    player.chatTimer = setInterval(chatTick, 1000);
    if (it.platform === 'twitch' && it.kind === 'vod') {
      xhr('GET', '/api/muted/' + encodeURIComponent(it.id), null, function (err, d) {
        if (!err && player && player.item === it) { player.muted = d.ranges; drawBar(); }
      });
    }
    $('pTitle').innerHTML = esc(nameOf(it)) + (it.title ? ' · ' + esc(it.title) : '');
    $('player').style.display = 'block';
    $('home').style.display = 'none';
    start(it.kind === 'vod' ? it.resume_s : 0);
    player.resumeTimer = setInterval(saveResume, 15000);
    showBar();
    try { history.pushState({player: 1}, ''); } catch (e) { /* sin historial: Atrás por tecla sigue cerrando */ }
  }

  // sale del video a la página de su canal (botón verde, G o "Canal" con el puntero)
  var pendingChannel = null;
  function playerToChannel() {
    pendingChannel = player.item.channel;
    history.back();
  }

  function closePlayer() {
    saveResume();
    clearInterval(player.resumeTimer);
    clearInterval(player.chatTimer);
    clearInterval(player.watchTimer);
    clearTimeout(player.seekTimer);
    clearTimeout(player.barTimer);
    var id = player.item.id;
    v.onplaying = v.onerror = v.onwaiting = null;
    v.pause();
    v.removeAttribute('src');
    v.load();
    player = null;
    $('player').style.display = 'none';
    $('home').style.display = '';
    // la barra roja de retomar se actualiza al volver; si se pidió el canal del video, se abre su página
    var go = pendingChannel;
    pendingChannel = null;
    setTimeout(function () {
      if (go && (!view || view.slug !== go)) { openChannel(go); } else if (view) { reloadChannel(id); } else { loadHome(id); }
    }, 300);
  }

  function seekKey(k) {
    var now = new Date().getTime();
    player.repeat = (k === player.lastCode && now - player.lastKey < 300) ? player.repeat + 1 : 0;
    player.lastCode = k; player.lastKey = now;
    var step = player.repeat >= 9 ? 60 : player.repeat >= 3 ? 30 : 10;
    seekBy(k === KEY.RIGHT ? step : -step);
  }

  function seekBy(delta) {
    if (player.item.kind !== 'vod' || !player.started) { return; }
    var d = isFinite(v.duration) && v.duration ? v.duration : (player.item.duration_s || 0);
    var base = player.target != null ? player.target : v.currentTime;
    player.target = TVL.seekTarget(base, delta, d);
    showBar();
    clearTimeout(player.seekTimer);
    player.seekTimer = setTimeout(function () {
      if (!player) { return; }
      v.currentTime = player.target;
      player.target = null;
      drawBar();
    }, 400);
  }

  function togglePause() {
    if (v.paused) { v.play(); } else { v.pause(); }
    showBar();
  }
  function toggleQuality() {
    var t = player.item.kind === 'vod' ? TVL.resumePoint(player, v.currentTime) : 0;
    player.target = null;
    store('tvl_q', quality() === 1080 ? '720' : '1080');
    start(t);
    showBar();
  }

  function playerKey(k) {
    if (k === KEY.ENTER) {
      togglePause();
    } else if (k === KEY.LEFT || k === KEY.RIGHT) {
      seekKey(k);
    } else if (k === KEY.UP || k === KEY.DOWN) {
      setBrightness(brightness + (k === KEY.UP ? 10 : -10), true);
      showBar();
    } else if (inArr(CANAL_KEYS, k)) {
      playerToChannel();
    } else if (inArr(CHAT_KEYS, k)) {
      toggleChat();
    } else {
      showBar();
    }
  }


  // ---------- buscar canal: cualquier streamer de Twitch; OK abre su página, → lo sigue o deja de seguir ----------
  var chan = null;  // estado del panel mientras está abierto: {items, idx (-1 = buscador), changed, timer, seq}
  var q = $('q');

  function chanItems() {
    var out = [], cs = data.channels || [];
    for (var i = 0; i < cs.length; i++) {
      out.push({platform: cs[i].platform, slug: cs[i].slug, name: cs[i].slug, live: false, following: true});
    }
    return out;
  }
  function drawChan() {
    var h = '', it, i;
    for (i = 0; i < chan.items.length; i++) {
      it = chan.items[i];
      h += '<div class="ci' + (i === chan.idx ? ' focus' : '') + '" data-i="' + i + '">' +
        '<div class="av" style="' + img(it.avatar) + '"></div>' +
        '<span class="nm">' + esc(it.name) +
        '<span class="sub">' + esc(join([it.followers != null ? many(it.followers) + ' seguidores' : '',
          it.live ? viewers(it.viewers) : '', it.category])) + '</span></span>' +
        (it.live ? '<span class="lv">● EN VIVO</span>' : '') +
        '<span class="fo' + (it.following ? ' on' : '') + '" data-f="1">' + (it.following ? '✓ Siguiendo' : '+ Seguir') + '</span></div>';
    }
    $('chanList').innerHTML = h || '<div class="empty">Sin resultados.</div>';
    q.className = chan.idx < 0 ? 'focus' : '';
    var list = $('chanList'), sel = list.children[chan.idx];
    list.scrollTop = sel ? Math.max(0, sel.offsetTop - list.offsetTop - 160) : 0;
  }
  function openChan() {
    chan = {items: chanItems(), idx: -1, changed: false, timer: null, seq: 0};
    q.value = '';
    $('chanTitle').innerHTML = chan.items.length ? 'Tus canales' : 'Escribe el nombre de un streamer';
    $('chanMsg').innerHTML = '';
    $('chan').style.display = 'block';
    drawChan();
    q.focus();  // en la TV abre su teclado en pantalla
    try { history.pushState({chan: 1}, ''); } catch (e) { /* sin historial: Atrás por tecla sigue cerrando */ }
  }
  function closeChan() {
    clearTimeout(chan.timer);
    var changed = chan.changed;
    chan = null;
    q.blur();
    $('chan').style.display = 'none';
    if (changed) {
      homeDirty = true;
      if (view) { reloadChannel(focusedId()); } else { homeDirty = false; loadHome(focusedId()); }
    }
  }
  function pickChan(i) {
    // abre la página del canal en lugar del panel: Atrás desde ella vuelve a la portada
    var it = chan.items[i];
    if (!it) { return; }
    if (chan.changed) { homeDirty = true; }
    clearTimeout(chan.timer);
    chan = null;
    q.blur();
    $('chan').style.display = 'none';
    try { history.replaceState({canal: 1}, ''); } catch (e) { /* sin historial */ }
    view = null;
    $('msg').innerHTML = 'Abriendo ' + esc(it.name) + '…';
    xhr('GET', '/api/channel/' + encodeURIComponent(it.slug), null, function (err, d) {
      if (err) {
        $('msg').innerHTML = 'No se pudo abrir el canal ' + esc(it.name) + ' (' + esc(err.message) + ').';
        try { history.back(); } catch (e) { /* sin historial */ }
        return;
      }
      $('msg').innerHTML = '';
      view = {slug: it.slug, data: d};
      if (!player) { render(null); }
    });
  }
  function searchChan() {
    clearTimeout(chan.timer);
    var text = q.value.replace(/^\s+|\s+$/g, '');
    if (!text) {
      chan.items = chanItems();
      $('chanTitle').innerHTML = 'Tus canales';
      drawChan();
      return;
    }
    var seq = ++chan.seq;
    $('chanTitle').innerHTML = 'Buscando “' + esc(text) + '”…';
    xhr('GET', '/api/search?q=' + encodeURIComponent(text.slice(0, 40)), null, function (err, d) {
      if (!chan || seq !== chan.seq) { return; }  // llegó tarde: ya se buscó otra cosa
      if (err) { $('chanMsg').innerHTML = 'No se pudo buscar (' + esc(err.message) + ').'; return; }
      chan.items = d.results;
      $('chanTitle').innerHTML = 'Resultados de “' + esc(text) + '”' + (d.results.length ? '' : ': nada');
      $('chanMsg').innerHTML = d.errors.length ? 'No respondió: ' + esc(d.errors.join(' · ')) : '';
      drawChan();
    });
  }
  function toggleFollow(i) {
    var it = chan.items[i], on = !it.following;
    xhr('POST', '/api/channels', {platform: it.platform, slug: it.slug, follow: on}, function (err) {
      if (!chan) { return; }
      if (err) { $('chanMsg').innerHTML = 'No se pudo guardar (' + esc(err.message) + ').'; return; }
      it.following = on;
      chan.changed = true;
      drawChan();
    });
  }
  function chanKey(k) {
    if (k === KEY.DOWN && chan.idx < chan.items.length - 1) {
      chan.idx++;
      q.blur();
    } else if (k === KEY.UP && chan.idx >= 0) {
      chan.idx--;
      if (chan.idx < 0) { q.focus(); }
    } else if (k === KEY.ENTER) {
      if (chan.idx < 0) {
        searchChan();
        if (chan.items.length) { chan.idx = 0; q.blur(); }
      } else {
        pickChan(chan.idx);
        return;
      }
    } else if (k === KEY.RIGHT && chan.idx >= 0) {
      toggleFollow(chan.idx);
    }
    drawChan();
  }
  q.oninput = function () {
    if (!chan) { return; }
    clearTimeout(chan.timer);
    chan.timer = setTimeout(searchChan, 700);
  };
  $('chanList').onclick = function (e) {
    var el = e.target, follow = false;
    while (el && el !== this && !(el.getAttribute && el.getAttribute('data-i'))) {
      if (el.getAttribute && el.getAttribute('data-f')) { follow = true; }
      el = el.parentNode;
    }
    if (!chan || !el || el === this) { return; }
    chan.idx = +el.getAttribute('data-i');
    if (follow) { toggleFollow(chan.idx); } else { pickChan(chan.idx); }
  };
  $('canales').onclick = function () { if (!player && !chan && data) { openChan(); } };
  $('chFollow').onclick = function () { if (!player && view) { toggleFollowView(); } };

  // ---------- teclado ----------
  document.onkeydown = function (e) {
    var k = e.keyCode;
    // Backspace borra en el buscador; vacío, es Atrás (el control de algunas TVs manda 8 como Atrás)
    if (chan && k === 8 && document.activeElement === q && q.value !== '') { return; }
    if (inArr(BACK, k)) {
      e.preventDefault();  // que Backspace no haga "atrás" en el navegador
      if (player || chan || view) { history.back(); }
      return;
    }
    if (chan) {
      // en el buscador ← → mueven el cursor del texto
      if (k === KEY.UP || k === KEY.DOWN || k === KEY.ENTER || (chan.idx >= 0 && (k === KEY.LEFT || k === KEY.RIGHT))) {
        e.preventDefault();
      }
      // con el teclado de la TV abierto, G es una letra del nombre, no "abrir canal"
      chanKey(k);
      return;
    }
    if (k === KEY.LEFT || k === KEY.RIGHT || k === KEY.UP || k === KEY.DOWN || k === KEY.ENTER) { e.preventDefault(); }
    if (player) { playerKey(k); } else if (data) { homeKey(k); }
  };

  // Atrás del navegador o del control: cierra lo que esté encima (reproductor, buscador, página de canal)
  window.onpopstate = function () {
    if (player) { closePlayer(); } else if (chan) { closeChan(); } else if (view) { closeChannel(); }
  };

  // ---------- puntero (muchos navegadores de TV mueven una manito en vez de mandar teclas) ----------
  function cardOf(el) {
    while (el && el !== document.body) {
      if (el.getAttribute && el.getAttribute('data-id')) { return el; }
      el = el.parentNode;
    }
    return null;
  }
  function itemById(id) {
    for (var r = 0; r < rows.length; r++) {
      for (var c = 0; c < rows[r].items.length; c++) {
        if (rows[r].items[c].id === id) { return {row: r, col: c, item: rows[r].items[c]}; }
      }
    }
    return null;
  }
  function rowOfEl(el) {
    for (var i = 0; i < rows.length; i++) { if (rows[i].el === el) { return i; } }
    return -1;
  }
  function bindRow(el) {
    el.onclick = function (e) {
      var card = cardOf(e.target), hit = card && itemById(card.getAttribute('data-id'));
      if (hit) { focus = {row: hit.row, col: hit.col}; openPlayer(hit.item); }
    };
    el.onmouseover = function (e) {
      var card = cardOf(e.target), hit = card && itemById(card.getAttribute('data-id'));
      if (hit && (hit.row !== focus.row || hit.col !== focus.col)) { focus = {row: hit.row, col: hit.col}; applyFocus(true); }
    };
  }
  for (var ri = 0; ri < 4; ri++) { bindRow($('row' + ri)); }

  var navs = document.querySelectorAll('.nav');
  for (var n = 0; n < navs.length; n++) {
    navs[n].onclick = function () {
      var r = rowOfEl($('row' + this.getAttribute('data-row')));
      if (r < 0) { return; }
      var col = focus.row === r ? focus.col : 0;
      var dir = this.className.indexOf('next') >= 0 ? 1 : -1;
      focus = {row: r, col: TVL.pageCol(col, rows[r].items.length, rows[r].per || 4, dir)};
      applyFocus();
    };
  }
  $('bMenos').onclick = function () { setBrightness(brightness - 10, true); };
  $('bMas').onclick = function () { setBrightness(brightness + 10, true); };

  $('player').onmousemove = function () { if (player) { showBar(); } };
  $('v').onclick = function () { if (player) { showBar(); } };
  var cbtns = document.querySelectorAll('.cbtn');
  for (var b = 0; b < cbtns.length; b++) {
    cbtns[b].onclick = function (e) {
      if (!player) { return; }
      var a = this.getAttribute('data-a');
      if (e && e.stopPropagation) { e.stopPropagation(); }
      if (a === 'back') { history.back(); } else if (a === 'pause') { togglePause(); } else if (a === 'q') { toggleQuality(); } else if (a === 'chat') { toggleChat(); } else if (a === 'canal') { playerToChannel(); } else if (a === 'b-' || a === 'b+') { setBrightness(brightness + (a === 'b+' ? 10 : -10), true); showBar(); } else { seekBy(+a); showBar(); }
    };
  }

  // ---------- arranque ----------
  function clock() {
    var d = new Date(), h = d.getHours(), ap = h < 12 ? 'a. m.' : 'p. m.';
    $('hora').innerHTML = ((h % 12) || 12) + ':' + pad(d.getMinutes()) + ' ' + ap;
  }
  clock();
  setInterval(clock, 30000);
  setInterval(function () {
    if (player || chan) { return; }
    if (view) { reloadChannel(focusedId()); } else if (data) { loadHome(focusedId()); }
  }, REFRESH_MS);
  loadHome(null);
})();
