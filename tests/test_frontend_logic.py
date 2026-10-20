"""Lógica pura del front (tvlibre/web/logic.js), ejecutada con node si está instalado."""
import json
import os
import shutil
import subprocess
import unittest

LOGIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tvlibre', 'web', 'logic.js')


def run(expr):
    code = 'var TVL = require(%s); console.log(JSON.stringify(%s));' % (json.dumps(LOGIC), expr)
    out = subprocess.run(['node', '-e', code], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which('node'), 'sin node')
class LogicTest(unittest.TestCase):
    def test_cambio_calidad_antes_de_arrancar_conserva_retomar(self):
        # el video aún carga (currentTime 0) y tenía que retomar en 1800 s
        self.assertEqual(run('TVL.resumePoint({started: false, seekTo: 1800, target: null}, 0)'), 1800)

    def test_cambio_calidad_con_salto_pendiente(self):
        self.assertEqual(run('TVL.resumePoint({started: true, seekTo: 0, target: 900}, 600)'), 900)

    def test_cambio_calidad_reproduciendo(self):
        self.assertEqual(run('TVL.resumePoint({started: true, seekTo: 1800, target: null}, 2400)'), 2400)

    def test_pagina_siguiente_y_anterior(self):
        # con puntero no se alcanzan las tarjetas fuera de pantalla: las flechas pasan de página
        self.assertEqual(run('TVL.pageCol(0, 40, 4, 1)'), 4)
        self.assertEqual(run('TVL.pageCol(38, 40, 4, 1)'), 39)
        self.assertEqual(run('TVL.pageCol(5, 40, 4, -1)'), 1)
        self.assertEqual(run('TVL.pageCol(2, 40, 4, -1)'), 0)
        self.assertEqual(run('TVL.pageCol(0, 0, 4, 1)'), 0)

    def test_tramo_silenciado(self):
        self.assertEqual(run('TVL.mutedUntil([[100, 200], [300, 400]], 150)'), 200)
        self.assertEqual(run('TVL.mutedUntil([[100, 200]], 200)'), None)
        self.assertEqual(run('TVL.mutedUntil([], 50)'), None)

    def test_salto_sin_duracion_no_va_a_cero(self):
        self.assertEqual(run('TVL.seekTarget(600, 10, 0)'), 610)
        self.assertEqual(run('TVL.seekTarget(5000, 10, 5000)'), 4995)
        self.assertEqual(run('TVL.seekTarget(5, -10, 5000)'), 0)


if __name__ == '__main__':
    unittest.main()
