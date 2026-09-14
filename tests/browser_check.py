"""Teste real no Edge, com banco e fontes isolados dos dados do usuário."""
import logging
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

import app as application
from tests.font_fixture import make_font, make_variable


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.artifacts = application.BASE_DIR / 'artifacts'
        cls.artifacts.mkdir(exist_ok=True)
        cls.fixture = cls.directory / 'fixture.ttf'
        make_font(cls.fixture)
        cls.variable = make_variable(cls.directory)
        cls.db_patch = patch.object(application, 'DB_FILE', str(cls.directory / 'test.db'))
        cls.font_patch = patch.object(application, 'UPLOAD_FOLDER', str(cls.directory / 'fonts'))
        cls.db_patch.start()
        cls.font_patch.start()
        application.init_db()
        # Usar as fontes reais sem cadastrar nem remover nada no banco do usuário.
        with application.database() as conn:
            paths = sorted(path for path in (application.BASE_DIR / 'static/fonts').iterdir() if path.suffix in {'.ttf', '.otf'})
            for index, path in enumerate(paths):
                shutil.copy2(path, Path(application.UPLOAD_FOLDER) / path.name)
                conn.execute('INSERT INTO fontes(nome, tipo, arquivo) VALUES (?, ?, ?)',
                             (f'original-{index}', 'local', path.name))
        cls.server = None
        cls.url = 'http://font-mixer.test'
        if os.environ.get('BROWSER_HTTP') == '1':
            cls.server = make_server('127.0.0.1', 0, application.app, threaded=True)
            cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
            cls.thread.start()
            cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel='msedge', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join()
        cls.db_patch.stop()
        cls.font_patch.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.delay_old = False
        # O transporte em memória executa as rotas Flask reais sem depender do
        # firewall local. BROWSER_HTTP=1 exercita o servidor HTTP da mesma suíte.
        if os.environ.get('BROWSER_HTTP') != '1':
            self.page.route('**/*', self.flask_route)
        self.page.goto(self.url)
        expect(self.page.locator('.item-fonte').first).to_be_visible()

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.page.close()

    def ready(self, text='ABBA'):
        self.page.locator('#input-frase').fill(text)
        expect(self.page.locator('#exportar')).to_be_enabled(timeout=10000)

    def test_live_samples_remain_separate_from_random_composition(self):
        self.ready('ABBA')
        expect(self.page.locator('.amostra svg').first).to_be_visible()
        self.page.wait_for_function("Array.from(document.querySelectorAll('.amostra')).every(e => e.querySelector('svg') || e.textContent.includes('não contém'))")
        outlines = self.page.locator('.amostra').evaluate_all('(els) => els.map(e => e.innerHTML)')
        self.page.locator('#aleatorizar').click()
        expect(self.page.locator('#exportar')).to_be_enabled()
        self.assertEqual(outlines, self.page.locator('.amostra').evaluate_all('(els) => els.map(e => e.innerHTML)'))

    def test_export_is_identical_to_preview_and_raster_pixels(self):
        self.ready('ABBA\nBA AB')
        self.page.evaluate('''() => {
            letras = letras.map((item, index) => {
                const pool = fontes.filter(f => !f.nome.toLowerCase().includes('morse') && Composition.supports(f, item.char));
                return {...item, fonte: pool[index % pool.length].id};
            });
            scheduleRender();
        }''')
        self.page.locator('#alinhamento').select_option('center')
        self.page.locator('#espacamento').fill('8')
        self.page.locator('#tamanho').fill('72')
        expect(self.page.locator('#exportar')).to_be_enabled()
        self.page.mouse.move(0, 0)
        svg = self.page.locator('#canvas-texto svg')
        # Inteiros evitam diferenças de rasterização por posição subpixel do elemento.
        self.page.add_style_tag(content='#canvas-texto {position:fixed;left:0;top:0;padding:0 0 2px;border:0;border-radius:0;z-index:999;background:#151719}')
        preview_png = svg.screenshot(path=str(self.artifacts / 'preview.png'))
        source = svg.evaluate('(e) => e.outerHTML')
        with self.page.expect_download() as info:
            self.page.locator('#exportar').click(force=True)
        download = info.value
        download.save_as(str(self.artifacts / 'texto_misturado.svg'))
        exported = Path(download.path()).read_text(encoding='utf-8')
        self.assertNotIn('<text', exported)
        standalone = self.browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
        try:
            standalone.set_content('<style>body{margin:0;background:#151719}svg{display:block}</style>' + exported)
            exported_png = standalone.locator('svg').screenshot(path=str(self.artifacts / 'exportado.png'))
            self.assertEqual(preview_png, exported_png, 'Pixels diferentes entre preview e SVG independente')
            self.assertEqual(source, standalone.locator('svg').evaluate('(e) => e.outerHTML'))
        finally:
            standalone.close()

    def test_upload_automatic_name_and_variable_controls(self):
        self.page.locator('#arquivo-fonte').set_input_files(str(self.variable))
        self.page.locator('#upload-form button').click()
        card = self.page.locator('.item-fonte').filter(has_text='Teste Vetorial')
        expect(card).to_have_count(1)
        self.ready('AB')
        before = self.page.locator('#canvas-texto svg').inner_html()
        card.get_by_label('Variação do arquivo').select_option(label='Pesada')
        expect(card.get_by_label('Weight (wght)')).to_have_value('900')
        expect(self.page.locator('#exportar')).to_be_enabled()
        self.assertNotEqual(before, self.page.locator('#canvas-texto svg').inner_html())
        card.get_by_label('Weight (wght)').fill('500')
        card.get_by_label('Weight (wght)').press('Tab')
        expect(self.page.locator('#exportar')).to_be_enabled()
        card.get_by_label('Tamanho relativo (%)').fill('150')
        card.get_by_label('Tamanho relativo (%)').press('Tab')
        expect(self.page.locator('#exportar')).to_be_enabled()
        self.page.screenshot(path=str(self.artifacts / 'interface.png'), full_page=True)
        card.get_by_role('button', name='Remover').click()
        expect(card).to_have_count(0)
        expect(self.page.locator('#exportar')).to_be_enabled()

    def test_manual_choice_lock_and_cycle(self):
        self.ready()
        self.page.locator('#modo').select_option('manual')
        path = self.page.locator('#canvas-texto path').first
        path.dispatch_event('click')
        expect(self.page.locator('#editor-letra')).to_be_visible()
        expect(self.page.locator('#opcoes-letra svg').first).to_be_visible()
        self.page.locator('#opcoes-letra button').first.click()
        expect(self.page.locator('#exportar')).to_be_enabled()
        options = self.page.locator('#fonte-letra option').evaluate_all('(els) => els.map(e => e.value)')
        self.page.locator('#fonte-letra').select_option(options[-1])
        expect(self.page.locator('#exportar')).to_be_enabled()
        self.page.locator('#travar-letra').check()
        self.page.locator('#aleatorizar').click()
        expect(self.page.locator('#exportar')).to_be_enabled()
        self.assertEqual(self.page.locator('#fonte-letra').input_value(), options[-1])
        self.page.locator('#modo').select_option('ciclo')
        self.page.locator('#canvas-texto path').first.dispatch_event('click')
        expect(self.page.locator('#exportar')).to_be_enabled()
        self.assertNotEqual(self.page.locator('#fonte-letra').input_value(), options[-1])

    def test_unsupported_glyph_disables_export_and_recovers(self):
        self.ready()
        self.page.locator('#input-frase').fill('中')
        expect(self.page.locator('#exportar')).to_be_disabled()
        expect(self.page.locator('#status')).to_contain_text('sem fonte compatível')
        self.ready('AB')

    def test_late_response_cannot_replace_new_text(self):
        self.delay_old = True
        if os.environ.get('BROWSER_HTTP') == '1':
            self.page.route('**/api/renderizar', self.delayed_route)
        self.page.locator('#input-frase').fill('AAAA')
        self.page.wait_for_timeout(160)
        self.page.locator('#input-frase').fill('BB')
        expect(self.page.locator('#exportar')).to_be_enabled()
        self.page.wait_for_timeout(700)
        self.assertEqual(self.page.locator('#canvas-texto path').count(), 2)
        self.assertEqual(self.page.locator('#canvas-texto path').first.get_attribute('data-char'), 'B')

    def delayed_route(self, route):
        body = route.request.post_data_json
        response = route.fetch()
        if len(body['letras']) == 4:
            self.page.wait_for_timeout(500)
        route.fulfill(response=response)

    def flask_route(self, route):
        request = route.request
        url = urlsplit(request.url)
        body = request.post_data_buffer
        content_type = request.headers.get('content-type')
        if content_type and content_type.startswith('multipart/form-data'):
            # Playwright omite os bytes dos arquivos em post_data_buffer.
            # Repor os bytes do File selecionado preserva o multipart real.
            data = self.page.locator('#arquivo-fonte').evaluate('async e => Array.from(new Uint8Array(await e.files[0].arrayBuffer()))')
            body = body.replace(b'\r\n\r\n', b'\r\n\r\n' + bytes(data), 1)
        with application.app.test_client() as client:
            response = client.open(url.path + ('?' + url.query if url.query else ''),
                                   method=request.method, data=body, content_type=content_type)
        if self.delay_old and url.path == '/api/renderizar' and len(request.post_data_json['letras']) == 4:
            self.page.wait_for_timeout(500)
        route.fulfill(status=response.status_code, body=response.data,
                      content_type=response.content_type)
        response.close()

    def test_mobile_has_no_page_overflow(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.ready('ABBA ABBA ABBA')
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.page.screenshot(path=str(self.artifacts / 'mobile.png'), full_page=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
