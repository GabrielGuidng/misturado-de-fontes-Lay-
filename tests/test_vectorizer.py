from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont

import app as application
from vectorizer import font_metadata, render_svg
from tests.font_fixture import make_font, make_variable

NS = {'s': 'http://www.w3.org/2000/svg'}


class VectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.path = cls.directory / 'fixture.ttf'
        make_font(cls.path)
        cls.variable = make_variable(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def svg(self, text='AB', options=None, **attributes):
        with TTFont(self.path) as font:
            return render_svg([dict(char=c, fonte=1, **attributes) for c in text], {1: font}, options or {})

    def paths(self, svg):
        return ET.fromstring(svg).findall('s:path', NS)

    def bounds(self, path):
        pen = BoundsPen(None)
        parse_path(path.attrib['d'], pen)
        return pen.bounds

    def test_independent_paths_without_font_dependency(self):
        svg = self.svg('Aé &<>😀')
        self.assertEqual(len(self.paths(svg)), 7)
        self.assertNotIn('<text', svg)
        self.assertNotIn('font-family', svg)
        self.assertNotIn('<image', svg)
        self.assertEqual(len({p.attrib['id'] for p in self.paths(svg)}), 7)
        self.assertEqual(self.paths(svg)[-1].attrib['data-char'], '😀')

    def test_outline_matches_source_metrics(self):
        bounds = self.bounds(self.paths(self.svg('A', {'tamanho': 100}))[0])
        self.assertEqual(bounds, (24.0, 34.0, 77.0, 104.0))

    def test_composite_accent_is_in_same_object(self):
        path = self.paths(self.svg('é'))[0]
        self.assertEqual(path.attrib['d'].count('M'), 2)

    def test_spaces_have_advance_and_empty_path(self):
        compact = self.bounds(self.paths(self.svg('AA'))[1])[0]
        spaced = self.paths(self.svg('A A'))
        self.assertEqual(spaced[1].attrib['d'], '')
        self.assertAlmostEqual(self.bounds(spaced[2])[0] - compact, 580 * .054)

    def test_tracking_changes_second_glyph_only(self):
        a, b = self.paths(self.svg()), self.paths(self.svg(options={'espacamento': 20}))
        self.assertEqual(a[0].attrib['d'], b[0].attrib['d'])
        self.assertAlmostEqual(self.bounds(b[1])[0] - self.bounds(a[1])[0], 20)

    def test_alignment_shifts_outlines(self):
        positions = [self.bounds(self.paths(self.svg('A', {'alinhamento': align}))[0])[0]
                     for align in ['left', 'center', 'right']]
        self.assertLess(positions[0], positions[1])
        self.assertAlmostEqual(positions[1] - positions[0], positions[2] - positions[1])

    def test_scale_changes_outline_dimensions(self):
        normal = self.bounds(self.paths(self.svg('A'))[0])
        larger = self.bounds(self.paths(self.svg('A', escala=2))[0])
        self.assertAlmostEqual(larger[2] - larger[0], 2 * (normal[2] - normal[0]))

    def test_multiline_and_wrap(self):
        explicit = self.paths(self.svg('A\nB'))
        self.assertGreater(self.bounds(explicit[1])[1], self.bounds(explicit[0])[1])
        wrapped = self.paths(self.svg('AAAA', {'largura': 100}))
        self.assertGreater(self.bounds(wrapped[-1])[1], self.bounds(wrapped[0])[1])
        self.assertEqual(len(wrapped), 4)

    def test_no_clipping_for_overflow_negative_spacing_and_alignment(self):
        for alignment in ['left', 'center', 'right']:
            for spacing in [-100, 0, 200]:
                root = ET.fromstring(self.svg('géAAAA', {'largura': 100, 'tamanho': 300,
                    'alinhamento': alignment, 'espacamento': spacing, 'quebrar': False}))
                x, y, w, h = map(float, root.attrib['viewBox'].split())
                for path in root.findall('s:path', NS):
                    bounds = self.bounds(path)
                    self.assertGreaterEqual(bounds[0], x - .00001)
                    self.assertGreaterEqual(bounds[1], y - .00001)
                    self.assertLessEqual(bounds[2], x + w + .00001)
                    self.assertLessEqual(bounds[3], y + h + .00001)

    def test_missing_character_is_error_not_fallback(self):
        with self.assertRaisesRegex(ValueError, 'não contém'):
            self.svg('中')

    def test_invalid_options(self):
        for options in [{'tamanho': 0}, {'tamanho': float('nan')}, {'cor': 'url(test)'},
                        {'alinhamento': 'oops'}, {'largura': 100, 'margem': 100}, {'entrelinha': 0}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.svg(options=options)

    def test_variable_axes_change_real_contours(self):
        with TTFont(self.variable) as font:
            metadata = font_metadata(font)
            self.assertEqual(metadata['eixos'][0]['tag'], 'wght')
            svgs = [render_svg([dict(char='A', fonte=1, eixos={'wght': weight})], {1: font}, {})
                    for weight in [100, 500, 900]]
            widths = [self.bounds(self.paths(svg)[0])[2] - self.bounds(self.paths(svg)[0])[0] for svg in svgs]
            self.assertLess(widths[0], widths[1])
            self.assertLess(widths[1], widths[2])
            with self.assertRaises(ValueError):
                render_svg([dict(char='A', fonte=1, eixos={'wght': 1000})], {1: font}, {})

    def test_unknown_axis_rejected(self):
        with self.assertRaises(ValueError):
            self.svg(eixos={'wght': 500})

    def test_all_repository_fonts_produce_outlines(self):
        for path in (application.BASE_DIR / 'static/fonts').glob('*'):
            with self.subTest(font=path.name), TTFont(path) as font:
                cmap = font.getBestCmap()
                text = ''.join(c for c in 'ABabé&09' if ord(c) in cmap)
                result = render_svg([dict(char=c, fonte=1) for c in text], {1: font}, {})
                self.assertTrue(any(p.attrib['d'] for p in self.paths(result)))

    def test_api_upload_metadata_render_and_validation(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(application, 'DB_FILE', str(Path(folder) / 'test.db')), patch.object(application, 'UPLOAD_FOLDER', str(Path(folder) / 'fonts')):
            application.init_db()
            client = application.app.test_client()
            upload = lambda data, name: client.post('/api/fontes', data={'arquivo': (BytesIO(data), name)})
            self.assertEqual(upload(b'bad', 'broken.ttf').status_code, 400)
            self.assertEqual(client.get('/api/fontes').json, [])
            self.assertEqual(upload(self.path.read_bytes(), 'fixture.ttf').status_code, 201)
            row = client.get('/api/fontes').json[0]
            self.assertEqual(row['nome'], 'Teste Vetorial — Regular')
            self.assertEqual(upload(self.path.read_bytes(), 'renamed.ttf').status_code, 409)
            body = {'letras': [{'char': 'A', 'fonte': row['id']}]}
            response = client.post('/api/renderizar', json=body)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(self.paths(response.json['svg'])[0].attrib['d'])
            for value in [-1, '5', None, True, 1001]:
                self.assertEqual(client.put(f'/api/fontes/{row["id"]}/peso', json={'peso': value}).status_code, 400)
            self.assertEqual(client.put(f'/api/fontes/{row["id"]}/peso', json={'peso': 0}).status_code, 200)
            self.assertEqual(client.get('/api/fontes').json[0]['peso'], 0)
            for bad in [{}, {'letras': [{}]}, {'letras': [{'char': 'AB', 'fonte': 1}]}, {'letras': [{'char': 'A', 'fonte': 999}]}]:
                self.assertEqual(client.post('/api/renderizar', json=bad).status_code, 400)
            self.assertEqual(client.delete(f'/api/fontes/{row["id"]}').status_code, 200)
            self.assertEqual(client.post('/api/renderizar', json=body).status_code, 400)

    def test_woff_and_woff2_upload(self):
        with TTFont(self.path) as font:
            for flavour in ['woff', 'woff2']:
                buffer = BytesIO()
                font.flavor = flavour
                font.save(buffer)
                with application.read_font(BytesIO(buffer.getvalue())) as decoded:
                    self.assertEqual(font_metadata(decoded)['familia'], 'Teste Vetorial')

    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            application.font_path('../app.py')

    def test_google_download_uses_font_bytes(self):
        css = b'@font-face {src: url(https://fonts.gstatic.com/example.ttf)}'
        with patch.object(application.urllib.request, 'urlopen', side_effect=[BytesIO(css), BytesIO(self.path.read_bytes())]) as fetch:
            data = application.google_font('Teste Vetorial')
            with application.read_font(BytesIO(data)) as font:
                self.assertEqual(font_metadata(font)['familia'], 'Teste Vetorial')
            self.assertEqual(fetch.call_count, 2)
        with self.assertRaises(ValueError):
            application.google_font('https://example.org/file')

    def test_empty_text_and_blank_lines_are_valid(self):
        for text in ['', ' ', '\n', 'A\n\nB']:
            root = ET.fromstring(self.svg(text))
            self.assertGreater(float(root.attrib['height']), 0)


if __name__ == '__main__':
    unittest.main()
