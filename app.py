from contextlib import ExitStack, contextmanager
from io import BytesIO
from pathlib import Path
import hashlib
import math
import re
import sqlite3
import urllib.parse
import urllib.request

from flask import Flask, jsonify, render_template, request
from fontTools.ttLib import TTFont
from vectorizer import font_metadata, render_svg

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = str(BASE_DIR / 'fontes.db')
UPLOAD_FOLDER = str(BASE_DIR / 'static' / 'fonts')
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024


@contextmanager
def database():
    conn = sqlite3.connect(DB_FILE)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    with database() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS fontes (
            id INTEGER PRIMARY KEY, nome TEXT UNIQUE, tipo TEXT,
            arquivo TEXT, peso INTEGER DEFAULT 1)''')


def font_path(filename):
    root = Path(UPLOAD_FOLDER).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not filename:
        raise ValueError('Arquivo de fonte indisponível. Importe o arquivo da fonte.')
    return path


def read_font(path):
    font = TTFont(path)
    try:
        font_metadata(font)
        return font
    except Exception:
        font.close()
        raise


def google_font(name):
    if not isinstance(name, str) or not re.fullmatch(r'[\w -]{1,100}', name):
        raise ValueError('Informe um nome de família válido do Google Fonts.')
    url = 'https://fonts.googleapis.com/css2?' + urllib.parse.urlencode({'family': name})
    with urllib.request.urlopen(url, timeout=15) as response:
        css = response.read(1_000_000).decode('utf-8')
    urls = re.findall(r'url\((https://fonts\.gstatic\.com/[^)]+)\)', css)
    if not urls:
        raise ValueError('Não foi possível baixar a fonte. Importe o arquivo local.')
    with urllib.request.urlopen(urls[-1], timeout=15) as response:
        data = response.read(app.config['MAX_CONTENT_LENGTH'] + 1)
    if len(data) > app.config['MAX_CONTENT_LENGTH']:
        raise ValueError('Arquivo de fonte muito grande.')
    return data


@app.errorhandler(413)
def too_large(_error):
    return jsonify(msg='Limite de upload: 20 MB.'), 413


@app.route('/')
def index():
    return render_template('index.html')


def json_object():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


@app.route('/api/fontes', methods=['GET', 'POST'])
def gerenciar_fontes():
    if request.method == 'POST':
        try:
            if 'arquivo' in request.files:
                upload = request.files['arquivo']
                if Path(upload.filename or '').suffix.lower() not in {'.ttf', '.otf', '.woff', '.woff2'}:
                    raise ValueError('Use um arquivo TTF, OTF, WOFF ou WOFF2.')
                data = upload.read()
                tipo = 'local'
            else:
                data = google_font(json_object().get('nome'))
                tipo = 'google'
            with read_font(BytesIO(data)) as font:
                metadata = font_metadata(font)
            filename = hashlib.sha256(data).hexdigest() + '.font'
            with database() as conn:
                if conn.execute('SELECT id FROM fontes WHERE arquivo = ?', (filename,)).fetchone():
                    return jsonify(msg='Este arquivo já foi adicionado.'), 409
                name = metadata['nome']
                if conn.execute('SELECT id FROM fontes WHERE nome = ?', (name,)).fetchone():
                    name += ' · ' + filename[:8]
                font_path(filename).write_bytes(data)
                conn.execute('INSERT INTO fontes (nome, tipo, arquivo) VALUES (?, ?, ?)',
                             (name, tipo, filename))
            return jsonify(status='sucesso'), 201
        except Exception as error:
            app.logger.info('Falha ao importar fonte: %s', error)
            message = str(error) if isinstance(error, ValueError) else 'Não foi possível ler ou baixar a fonte. Verifique o arquivo ou a conexão.'
            return jsonify(msg=message), 400

    with database() as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute('SELECT * FROM fontes ORDER BY id DESC')]
    for row in rows:
        try:
            with read_font(font_path(row['arquivo'])) as font:
                row.update(font_metadata(font))
            row['disponivel'] = True
        except Exception:
            row.update(disponivel=False, erro='Arquivo indisponível ou incompatível. Importe novamente.')
    return jsonify(rows)


@app.delete('/api/fontes/<int:id_fonte>')
def deletar_fonte(id_fonte):
    with database() as conn:
        conn.execute('DELETE FROM fontes WHERE id = ?', (id_fonte,))
    return jsonify(status='sucesso')


@app.put('/api/fontes/<int:id_fonte>/peso')
def atualizar_peso(id_fonte):
    peso = json_object().get('peso')
    if isinstance(peso, bool) or not isinstance(peso, (int, float)) or not math.isfinite(peso) or not 0 <= peso <= 1000:
        return jsonify(msg='Prioridade deve estar entre 0 e 1000.'), 400
    with database() as conn:
        cursor = conn.execute('UPDATE fontes SET peso = ? WHERE id = ?', (peso, id_fonte))
    if not cursor.rowcount:
        return jsonify(msg='Fonte não encontrada.'), 404
    return jsonify(status='sucesso')


@app.post('/api/renderizar')
def renderizar():
    payload = request.get_json(silent=True)
    try:
        if not isinstance(payload, dict):
            raise ValueError('Composição inválida.')
        letters = payload.get('letras')
        if not isinstance(letters, list) or len(letters) > 1000:
            raise ValueError('Use até 1000 caracteres.')
        ids = set()
        for item in letters:
            if not isinstance(item, dict) or not isinstance(item.get('char'), str) or len(item['char']) != 1:
                raise ValueError('Cada objeto deve conter exatamente um caractere.')
            if not isinstance(item.get('fonte'), int) or isinstance(item['fonte'], bool):
                raise ValueError('Escolha uma fonte para cada caractere.')
            ids.add(item['fonte'])
        with database() as conn:
            rows = dict(conn.execute('SELECT id, arquivo FROM fontes'))
        with ExitStack() as stack:
            fonts = {}
            for font_id in ids:
                if font_id not in rows:
                    raise ValueError('Uma fonte foi removida. Escolha outra fonte.')
                fonts[font_id] = stack.enter_context(read_font(font_path(rows[font_id])))
            return jsonify(svg=render_svg(letters, fonts, payload.get('opcoes', {})))
    except ValueError as error:
        return jsonify(msg=str(error)), 400
    except Exception:
        app.logger.exception('Falha na vetorização')
        return jsonify(msg='Não foi possível vetorizar esta fonte. Verifique o arquivo.'), 400


init_db()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
