from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import werkzeug.utils

app = Flask(__name__)
DB_FILE = "fontes.db"
UPLOAD_FOLDER = "static/fonts"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS fontes (
                        id INTEGER PRIMARY KEY, 
                        nome TEXT UNIQUE, 
                        tipo TEXT, 
                        arquivo TEXT, 
                        peso INTEGER DEFAULT 1)""")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fontes", methods=["GET", "POST"])
def gerenciar_fontes():
    with sqlite3.connect(DB_FILE) as conn:
        if request.method == "POST":
            # Verifica se é um arquivo (fonte local) ou JSON (Google Fonts)
            if "arquivo" in request.files:
                file = request.files["arquivo"]
                nome = request.form.get("nome")
                filename = werkzeug.utils.secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                tipo, arquivo_bd = "local", filename
            else:
                nome = request.json.get("nome")
                tipo, arquivo_bd = "google", ""

            try:
                conn.execute(
                    "INSERT INTO fontes (nome, tipo, arquivo) VALUES (?, ?, ?)",
                    (nome, tipo, arquivo_bd),
                )
                return jsonify({"status": "sucesso"}), 201
            except sqlite3.IntegrityError:
                return jsonify({"status": "erro", "msg": "Fonte já existe"}), 400

        # GET: Retorna todas as fontes
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM fontes ORDER BY id DESC")
        fontes = [dict(row) for row in cursor.fetchall()]
        return jsonify(fontes)


@app.route("/api/fontes/<int:id_fonte>", methods=["DELETE"])
def deletar_fonte(id_fonte):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM fontes WHERE id = ?", (id_fonte,))
    return jsonify({"status": "sucesso"})


@app.route("/api/fontes/<int:id_fonte>/peso", methods=["PUT"])
def atualizar_peso(id_fonte):
    novo_peso = request.json.get("peso")
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("UPDATE fontes SET peso = ? WHERE id = ?", (novo_peso, id_fonte))
    return jsonify({"status": "sucesso"})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
