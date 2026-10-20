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
    // Destino de un salto; si no se conoce la duración no se acota por arriba.
    seekTarget: function (base, delta, duration) {
      var t = Math.max(0, base + delta);
      return duration > 0 ? Math.min(duration - 5, t) : t;
    }
  };
  if (typeof module !== 'undefined' && module.exports) { module.exports = TVL; } else { root.TVL = TVL; }
}(this));
