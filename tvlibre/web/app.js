/* tvlibre: interfaz para el control remoto. ES5 a propósito (navegadores de TV de 2014). */
(function () {
  'use strict';

  var KEY = {LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, ENTER: 13};
  var BACK = [8, 27, 461, 10009];
  var REFRESH_MS = 60000;

  var $ = function (id) { return document.getElementById(id); };
  var data = null;          // última respuesta de /api/home
  var rows = [];            // [{name, el, items}] filas navegables, en orden vertical
  var focus = {row: 0, col: 0};
  var brightness = 100;
  var player = null;        // estado del reproductor mientras está abierto
  var retryTimer = null;    // un solo reintento pendiente aunque fallen varias cargas

  // ---------- utilidades ----------
  function xhr(method, url, body, cb) {
    var x = new XMLHttpRequest();
    x.open(method, url);
    x.timeout = 30000;
    if (body) { x.setRequestHeader('Content-Type', 'application/json'); }
    x.onload = function () {
      if (!cb) { return; }
      if (x.status >= 200 && x.status < 300) { cb(null, x.responseText ? JSON.parse(x.responseText) : null); }
      else { cb(new Error('HTTP ' + x.status)); }
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
    return days <= 0 ? 'hoy' : days === 1 ? 'ayer' : 'hace ' + days + ' días';
  }
  function since(iso) {
    var min = Math.max(0, Math.round((new Date().getTime() - parseIso(iso)) / 60000));
    return min < 60 ? 'hace ' + min + ' min' : 'hace ' + Math.floor(min / 60) + ' h ' + (min % 60) + ' min';
  }
  function viewers(n) {
    if (n == null) { return ''; }
    return n >= 1000 ? (Math.round(n / 100) / 10).toString().replace('.', ',') + ' mil espectadores' : n + ' espectadores';
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

  // ---------- brillo ----------
  function setBrightness(v, save) {
    brightness = Math.max(30, Math.min(100, v));
    $('dim').style.opacity = String((100 - brightness) / 100);
    $('brilloVal').innerHTML = brightness;
    $('pBri').innerHTML = brightness + '%';
    if (save) { xhr('POST', '/api/state', {brightness: brightness}); }
  }

  // ---------- portada ----------
  function liveCard(it) {
    return '<div class="card live ' + it.platform + '" data-id="' + esc(it.id) + '" style="' + img(it.thumb, true) + '">' +
      '<span class="badge">● EN VIVO</span><div class="shade">' +
      '<div><span class="plat ' + it.platform + '">' + it.platform.toUpperCase() + '</span></div>' +
      '<div class="n">' + esc(it.channel) + '</div>' +
      '<div class="t">' + esc(it.title) + '</div>' +
      '<div class="t">' + viewers(it.viewers) + ' · ' + since(it.started_at) + '</div></div></div>';
  }
  function vodCard(it) {
    var prog = it.resume_s && it.duration_s ? '<div class="prog" style="width:' + Math.min(100, 100 * it.resume_s / it.duration_s) + '%"></div>' : '';
    return '<div class="card vod" data-id="' + esc(it.id) + '">' +
      '<div class="th ' + it.platform + '" style="' + img(it.thumb) + '"><span class="dur">' + hms(it.duration_s) + '</span>' + prog + '</div>' +
      '<div class="t">' + esc(it.title) + '</div>' +
      '<div class="m"><span class="plat ' + it.platform + '">' + it.platform.toUpperCase() + '</span>' +
      esc(it.channel) + ' · ' + relDay(it.started_at) + '</div></div>';
  }

  function focusedId() {
    var r = rows[focus.row];
    return r && r.items[focus.col] ? r.items[focus.col].id : null;
  }

  function render(keepId) {
    var live = data.live, vods = data.vods, i;
    var lh = '', vh = '';
    for (i = 0; i < live.length; i++) { lh += liveCard(live[i]); }
    for (i = 0; i < vods.length; i++) { vh += vodCard(vods[i]); }
    $('liveRow').innerHTML = lh;
    $('vodRow').innerHTML = vh || '<div class="empty">No hay streams anteriores.</div>';
    $('liveSec').style.display = live.length ? '' : 'none';
    $('msg').innerHTML = data.errors.length ? 'No se pudo consultar: ' + esc(data.errors.join(' · ')) : '';

    rows = [{name: 'top', el: null, items: [{id: '__brillo'}]}];
    if (live.length) { rows.push({name: 'live', el: $('liveRow'), items: live}); }
    if (vods.length) { rows.push({name: 'vods', el: $('vodRow'), items: vods}); }

    var placed = false;
    if (keepId) {
      for (var r = 0; r < rows.length && !placed; r++) {
        for (var c = 0; c < rows[r].items.length; c++) {
          if (rows[r].items[c].id === keepId) { focus = {row: r, col: c}; placed = true; break; }
        }
      }
    }
    if (!placed) {
      // primer arranque: el directo si hay; si no, el anterior más reciente
      focus = {row: rows.length > 1 ? 1 : 0, col: 0};
    }
    applyFocus();
  }

  function applyFocus(noScroll) {
    var all = document.querySelectorAll('.focus'), i;
    for (i = 0; i < all.length; i++) { all[i].className = all[i].className.replace(/\s*\bfocus\b/g, ''); }
    var row = rows[focus.row];
    if (!row) { return; }
    if (row.name === 'top') { $('brillo').className += ' focus'; return; }
    var card = row.el.children[focus.col];
    if (!card) { return; }
    card.className += ' focus';
    if (noScroll) { return; }
    // desplaza la fila para que la tarjeta enfocada quede a la vista
    var off = Math.max(0, card.offsetLeft - row.el.offsetLeft - 40);
    var max = Math.max(0, row.el.scrollWidth - 1200);
    off = Math.min(off, max);
    row.el.style.webkitTransform = 'translateX(-' + off + 'px)';
    row.el.style.transform = 'translateX(-' + off + 'px)';
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
      if (!player) { render(keepId); }
    });
  }

  function homeKey(k) {
    var row = rows[focus.row];
    if (!row) { return; }
    if (k === KEY.DOWN && focus.row < rows.length - 1) {
      focus.row++; focus.col = Math.min(focus.col, rows[focus.row].items.length - 1);
    } else if (k === KEY.UP && focus.row > 0) {
      focus.row--; focus.col = Math.min(focus.col, rows[focus.row].items.length - 1);
    } else if (row.name === 'top' && (k === KEY.LEFT || k === KEY.RIGHT)) {
      setBrightness(brightness + (k === KEY.RIGHT ? 10 : -10), true);
    } else if (k === KEY.LEFT && focus.col > 0) {
      focus.col--;
    } else if (k === KEY.RIGHT && focus.col < row.items.length - 1) {
      focus.col++;
    } else if (k === KEY.ENTER && row.name !== 'top') {
      openPlayer(row.items[focus.col]);
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
      $('loading').style.display = 'none';
      $('perr').innerHTML = 'No se pudo reproducir (código ' + (v.error ? v.error.code : '?') + '). Atrás para volver.';
      $('perr').style.display = 'block';
    };
    v.src = '/play/' + encodeURIComponent(player.item.id) + '.m3u8?q=' + quality();
    v.load();
    v.play();
  }

  function openPlayer(it) {
    player = {item: it, target: null, seekTimer: null, barTimer: null, lastKey: 0, lastCode: 0, repeat: 0, started: false,
      muted: []};
    if (it.platform === 'twitch' && it.kind === 'vod') {
      xhr('GET', '/api/muted/' + encodeURIComponent(it.id), null, function (err, d) {
        if (!err && player && player.item === it) { player.muted = d.ranges; drawBar(); }
      });
    }
    $('pTitle').innerHTML = esc(it.channel) + ' · ' + esc(it.title);
    $('player').style.display = 'block';
    $('home').style.display = 'none';
    start(it.kind === 'vod' ? it.resume_s : 0);
    player.resumeTimer = setInterval(saveResume, 15000);
    showBar();
    try { history.pushState({player: 1}, ''); } catch (e) { /* sin historial: Atrás por tecla sigue cerrando */ }
  }

  function closePlayer() {
    saveResume();
    clearInterval(player.resumeTimer);
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
    // la barra roja de retomar se actualiza al volver
    setTimeout(function () { loadHome(id); }, 300);
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
    } else {
      showBar();
    }
  }

  // ---------- teclado ----------
  document.onkeydown = function (e) {
    var k = e.keyCode;
    if (inArr(BACK, k)) {
      e.preventDefault();  // que Backspace no haga "atrás" en el navegador
      if (player) { history.back(); }
      return;
    }
    if (k === KEY.LEFT || k === KEY.RIGHT || k === KEY.UP || k === KEY.DOWN || k === KEY.ENTER) { e.preventDefault(); }
    if (player) { playerKey(k); } else if (data) { homeKey(k); }
  };

  // ---------- puntero (muchos navegadores de TV mueven una manito en vez de mandar teclas) ----------
  window.onpopstate = function () { if (player) { closePlayer(); } };

  function cardOf(el) {
    while (el && el !== document.body) {
      if (el.getAttribute && el.getAttribute('data-id')) { return el; }
      el = el.parentNode;
    }
    return null;
  }
  function rowIndex(name) {
    for (var i = 0; i < rows.length; i++) { if (rows[i].name === name) { return i; } }
    return -1;
  }
  function itemById(id) {
    for (var r = 0; r < rows.length; r++) {
      for (var c = 0; c < rows[r].items.length; c++) {
        if (rows[r].items[c].id === id) { return {row: r, col: c, item: rows[r].items[c]}; }
      }
    }
    return null;
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
  bindRow($('liveRow'));
  bindRow($('vodRow'));

  var navs = document.querySelectorAll('.nav');
  for (var n = 0; n < navs.length; n++) {
    navs[n].onclick = function () {
      var name = this.getAttribute('data-row'), r = rowIndex(name);
      if (r < 0) { return; }
      var col = focus.row === r ? focus.col : 0;
      var dir = this.className.indexOf('next') >= 0 ? 1 : -1;
      focus = {row: r, col: TVL.pageCol(col, rows[r].items.length, name === 'live' ? 2 : 4, dir)};
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
      if (a === 'back') { history.back(); } else if (a === 'pause') { togglePause(); } else if (a === 'q') { toggleQuality(); } else if (a === 'b-' || a === 'b+') { setBrightness(brightness + (a === 'b+' ? 10 : -10), true); showBar(); } else { seekBy(+a); showBar(); }
    };
  }

  // ---------- arranque ----------
  function clock() {
    var d = new Date(), h = d.getHours(), ap = h < 12 ? 'a. m.' : 'p. m.';
    $('hora').innerHTML = ((h % 12) || 12) + ':' + pad(d.getMinutes()) + ' ' + ap;
  }
  clock();
  setInterval(clock, 30000);
  setInterval(function () { if (!player && data) { loadHome(focusedId()); } }, REFRESH_MS);
  loadHome(null);
})();
