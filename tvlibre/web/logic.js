/* Lógica pura del reproductor, separada para poder probarla con node. ES5. */
(function (root) {
  'use strict';
  var TVL = {
    // Segundo desde el que retomar al recargar el video (p. ej. al cambiar de calidad).
    // Si aún no arrancó, currentTime vale 0 y se perdería el punto de retomar pendiente.
    resumePoint: function (p, currentTime) {
      if (p.target != null) { return p.target; }
      return p.started ? currentTime : (p.seekTo || 0);
    },
    // Columna tras pasar una página (flechas ‹ › para puntero): avanza perPage, sin salirse de la fila.
    pageCol: function (col, len, perPage, dir) {
      if (len <= 0) { return 0; }
      return Math.max(0, Math.min(len - 1, col + dir * perPage));
    },
    // ---------- chat: en vivo se agrega lo nuevo; en un anterior cada mensaje sale cuando el video llega a su segundo ----------
    chatReset: function () { return {shown: [], buf: [], ids: {}, nIds: 0, lastIds: [], until: -1, last: -1}; },
    _chatKeep: function (s) {
      if (s.shown.length > 40) { s.shown = s.shown.slice(s.shown.length - 40); }
      if (s.nIds <= 500) { return; }
      // en un directo de horas los ids crecían sin tope: basta con lo visible, lo pendiente y la última respuesta
      var keep = s.shown.concat(s.buf), i;
      s.ids = {}; s.nIds = 0;
      for (i = 0; i < keep.length; i++) { s.ids[keep[i].id] = 1; s.nIds++; }
      for (i = 0; i < s.lastIds.length; i++) { if (!s.ids[s.lastIds[i]]) { s.ids[s.lastIds[i]] = 1; s.nIds++; } }
    },
    _chatSeen: function (s, msgs) {
      s.lastIds = [];
      for (var i = 0; i < msgs.length; i++) { s.lastIds.push(msgs[i].id); }
    },
    chatAddLive: function (s, msgs) {
      var n = 0;
      TVL._chatSeen(s, msgs);
      for (var i = 0; i < msgs.length; i++) {
        if (!s.ids[msgs[i].id]) { s.ids[msgs[i].id] = 1; s.nIds++; s.shown.push(msgs[i]); n++; }
      }
      TVL._chatKeep(s);
      return n;
    },
    chatAddVod: function (s, resp) {
      TVL._chatSeen(s, resp.messages);
      for (var i = 0; i < resp.messages.length; i++) {
        var m = resp.messages[i];
        if (!s.ids[m.id]) { s.ids[m.id] = 1; s.nIds++; s.buf.push(m); }
      }
      s.until = Math.max(s.until, resp.until);
      TVL._chatKeep(s);
    },
    // Pasa a pantalla los mensajes cuyo segundo ya llegó; devuelve cuántos.
    chatDue: function (s, pos) {
      var n = 0, rest = [];
      for (var i = 0; i < s.buf.length; i++) {
        if (s.buf[i].at <= pos) { s.shown.push(s.buf[i]); n++; } else { rest.push(s.buf[i]); }
      }
      s.buf = rest;
      s.last = pos;
      TVL._chatKeep(s);
      return n;
    },
    chatNeedsFetch: function (s, pos) { return s.until < 0 || pos + 8 >= s.until; },
    // Un salto hacia atrás o muy adelante deja el chat de otra hora: hay que reiniciarlo.
    chatJump: function (s, pos) {
      return (s.last >= 0 && pos < s.last - 3) || (s.until >= 0 && pos > s.until + 40);
    },
    // Fin del tramo que Twitch silenció en el segundo t, o null si ahí hay audio.
    mutedUntil: function (ranges, t) {
      for (var i = 0; i < ranges.length; i++) {
        if (t >= ranges[i][0] && t < ranges[i][1]) { return ranges[i][1]; }
      }
      return null;
    },
    // Destino de un salto; si no se conoce la duración no se acota por arriba.
    seekTarget: function (base, delta, duration) {
      var t = Math.max(0, base + delta);
      return duration > 0 ? Math.min(duration - 5, t) : t;
    }
  };
  if (typeof module !== 'undefined' && module.exports) { module.exports = TVL; } else { root.TVL = TVL; }
}(this));
