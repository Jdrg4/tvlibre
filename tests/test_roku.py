"""El canal de Roku no se puede ejecutar aquí: se comprueba que el paquete esté completo y bien armado."""
import importlib.util
import os
import re
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

ROKU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'roku')
spec = importlib.util.spec_from_file_location('roku_build', os.path.join(ROKU, 'build.py'))
roku_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roku_build)


def components():
    out = {}
    for f in os.listdir(os.path.join(ROKU, 'components')):
        if f.endswith('.xml'):
            out[f] = ET.parse(os.path.join(ROKU, 'components', f)).getroot()
    return out


class RokuPackageTest(unittest.TestCase):
    def test_scripts_exist(self):
        for name, root in components().items():
            for s in root.iter('script'):
                path = os.path.join(ROKU, 'components', s.get('uri'))
                self.assertTrue(os.path.exists(path), '%s pide %s' % (name, s.get('uri')))

    def test_referenced_components_exist(self):
        names = {r.get('name') for r in components().values()} | {'ContentNode', 'StandardKeyboardDialog', 'Label', 'Poster'}  # nodos del Roku
        used = set()
        for root in components().values():
            used |= {e.get('itemComponentName') for e in root.iter() if e.get('itemComponentName')}
        for d, _, fs in os.walk(ROKU):
            for f in fs:
                if f.endswith('.brs'):
                    with open(os.path.join(d, f), encoding='utf-8') as fh:
                        src = fh.read()
                    used |= set(re.findall(r'CreateObject\("roSGNode", "(\w+)"\)', src))
                    used |= set(re.findall(r'CreateScene\("(\w+)"\)', src))
        self.assertEqual(used - names, set())

    def test_no_builtin_names_as_variables(self):
        # en BrightScript estas son funciones: usarlas como variable o parámetro no compila
        builtin = r'pos|len|str|val|mid|tab|left|right|chr|asc|abs|int|fix|sgn|instr|ucase|lcase|eval|run|type|box'
        bad = re.compile(r'(?im)^\s*(%s)\s*=|\b(%s)\s+as\s+\w+' % (builtin, builtin))
        for d, _, fs in os.walk(ROKU):
            for f in fs:
                if f.endswith('.brs'):
                    with open(os.path.join(d, f), encoding='utf-8') as fh:
                        m = bad.search(fh.read())
                    self.assertIsNone(m, '%s usa %r' % (f, m and m.group(0)))

    def test_foco_no_en_la_escena(self):
        # m.top.setFocus deja el foco en la fila oculta: OK abría otra tarjeta en pleno video
        with open(os.path.join(ROKU, 'components', 'HomeScene.brs'), encoding='utf-8') as f:
            self.assertNotIn('m.top.setFocus', f.read())

    def test_panel_se_reabre(self):
        # sin alwaysNotify, reabrir el panel con los mismos canales no llamaba a open(): quedaba sin foco y trabado
        panel = components()['ChannelsPanel.xml']
        field = [f for f in panel.iter('field') if f.get('id') == 'channels'][0]
        self.assertEqual(field.get('alwaysNotify'), 'true')

    def test_manifest_images_exist(self):
        with open(os.path.join(ROKU, 'manifest'), encoding='utf-8') as f:
            for uri in re.findall(r'pkg:/(\S+)', f.read()):
                self.assertTrue(os.path.exists(os.path.join(ROKU, uri)), uri)

    def test_build_sets_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = roku_build.build('http://10.0.0.5:8099/', os.path.join(tmp, 'c.zip'))
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
                manifest = z.read('manifest').decode()
        self.assertIn('source/main.brs', names)
        self.assertIn('components/HomeScene.xml', names)
        self.assertFalse(any(n.endswith('.py') for n in names))
        self.assertIn('tvlibre_server=http://10.0.0.5:8099\n', manifest)
        self.assertEqual(manifest.count('tvlibre_server='), 1)

    def test_build_rejects_bad_server(self):
        for bad in ('192.168.1.10:8099', 'https://x/y', 'http://x/play'):
            with self.assertRaises(ValueError):
                roku_build.build(bad, os.path.join(tempfile.gettempdir(), 'nunca.zip'))


if __name__ == '__main__':
    unittest.main()
