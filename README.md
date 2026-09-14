# Misturador de fontes · LAY

Aplicação local Flask para combinar fontes por caractere e exportar a composição como SVG editável em curvas.

## Executar

Na pasta do projeto, no PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

O ambiente `.venv` desta entrega já está preparado. Para abrir novamente, basta o último comando. Acesse <http://127.0.0.1:5000>. Reinicie a instância anterior antes de usar a versão nova na mesma porta.

## Usar

1. Adicione TTF, OTF, WOFF ou WOFF2, sem preencher nome. Família, estilo, eixos e variações nomeadas são lidos do arquivo.
2. Digite o texto. As amostras sob cada nome mostram o mesmo texto em uma única fonte, independentemente da mistura principal.
3. Ajuste tamanho global, tamanho relativo por fonte, espaçamento, entrelinha, largura, margem, alinhamento e cor. Fontes variáveis oferecem seus eixos reais e variações nomeadas; arquivos estáticos mostram apenas o estilo que contêm.
4. Use sorteio ponderado, exclusão com prioridade 0 e prevenção de repetições consecutivas. Clique nas letras para trocar de fonte ou escolher manualmente; a trava preserva a escolha durante novos sorteios.
5. Exporte o SVG. Cada caractere visível é um `path` separado, com contornos compostos preservados. Espaços ocupam sua largura; quebras de linha só alteram o layout. O fundo é transparente.

O preview principal recebe o próprio SVG produzido pelo servidor. O download usa essa mesma string, sem recalcular posições ou sortear fontes. Durante atualização ou erro, a exportação fica desabilitada. Caracteres ausentes geram indicação explícita, sem substituição por Arial.

## Estrutura e contratos

- `app.py`: API Flask, SQLite, importação e validação de arquivos. O banco e os caminhos são relativos à pasta da aplicação.
- `vectorizer.py`: metadados, curvas, métricas, variações e layout. Usa [fontTools SVGPathPen](https://fonttools.readthedocs.io/en/latest/pens/svgPathPen.html).
- `static/composition.js`: regras puras de sorteio, compatibilidade e preservação das escolhas.
- `static/app.js`: controles, amostras e descarte de respostas antigas.
- `templates/index.html` e `static/style.css`: interface responsiva.
- `POST /api/renderizar`: recebe `{letras: [{char, fonte, escala, eixos}], opcoes: {tamanho, espacamento, entrelinha, largura, margem, alinhamento, cor, quebrar}}`; devolve `{svg}` ou erro 400 com `{msg}`.
- `GET/POST /api/fontes`: lista metadados ou importa arquivo; `DELETE /api/fontes/<id>` remove o cadastro; `PUT /api/fontes/<id>/peso` altera a prioridade.

O esquema SQLite existente foi mantido. Importações novas usam nome de arquivo por SHA-256 para evitar sobrescritas. Remover um cadastro preserva o arquivo em disco. Fontes e prioridades persistem; texto, escolhas e ajustes visuais duram a sessão da página.

## Limites

- Até 1000 caracteres por composição e 20 MB por upload.
- O SVG contém formas, portanto o texto passa a ser editado por nós/contornos no editor vetorial.
- A composição opera caractere a caractere, sem ligaduras ou modelagem contextual de escrita complexa. A entrada é normalizada em NFC para acentos compostos.
- Fontes sem contornos TTF/OTF, como fontes exclusivamente bitmap, não são aceitas. Camadas coloridas de fontes não são reproduzidas; a composição usa a cor escolhida.
- A importação Google Fonts baixa o estilo padrão e precisa de internet. Outros estilos/eixos exigem o arquivo correspondente. Cadastros antigos do Google sem arquivo precisam ser importados novamente.
- Fontes não instaladas no computador de destino não são necessárias para os contornos exportados. A importação dentro do Figma não foi automatizada nesta entrega.

## Testes

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m unittest tests.test_vectorizer -v
node --test tests/composition.test.js
.\.venv\Scripts\python -m tests.browser_check
```

A suíte de navegador usa o Edge instalado e executa as rotas Flask reais com transporte em memória, banco temporário e cópias das fontes. Não modifica o banco do usuário. Para usar HTTP local real, configure `$env:BROWSER_HTTP = '1'` antes do último comando.

A validação compara os contornos e os pixels do SVG baixado com o preview, usando fontes misturadas, e cobre upload, variações, edição, exclusão, sorteio, respostas atrasadas e tela móvel. As evidências são gravadas em `artifacts/`.

A suíte HTTP encontrou bloqueios intermitentes `ERR_NETWORK_ACCESS_DENIED` do ambiente no Chrome e no Edge. A comparação visual também passou por HTTP; a bateria completa usa o transporte em memória para não depender desse bloqueio. O download externo do Google é testado com resposta controlada, sem afirmar disponibilidade do serviço externo.
