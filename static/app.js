'use strict';
const $ = id => document.getElementById(id);
let fontes = [], letras = [], selected = null, revision = 0, sampleRevision = 0;
let svgAtual = '', renderTimer, sampleTimer;
const settings = new Map();

function status(message, error = false) {
    $('status').textContent = message;
    $('status').className = error ? 'erro' : '';
}
async function api(url, method = 'GET', body) {
    const options = {method};
    if (body instanceof FormData) options.body = body;
    else if (body !== undefined) {
        options.headers = {'Content-Type': 'application/json'};
        options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.msg || 'Falha na operação.');
    return data;
}
function layout() {
    const result = {};
    for (const key of ['tamanho', 'espacamento', 'entrelinha', 'largura', 'margem']) result[key] = Number($(key).value);
    return {...result, alinhamento: $('alinhamento').value, cor: $('cor').value, quebrar: $('quebrar').checked};
}
function enriched(items) {
    return items.map(item => ({...item, ...settings.get(item.fonte)}));
}
function invalidate() {
    revision++;
    svgAtual = '';
    $('exportar').disabled = true;
    $('canvas-texto').replaceChildren();
    clearTimeout(renderTimer);
}
function scheduleRender() {
    invalidate();
    status('Atualizando preview…');
    renderTimer = setTimeout(renderMain, 100);
}
async function renderMain() {
    const current = revision;
    try {
        if (!letras.length) { status('Digite seu texto para começar.'); return; }
        if (letras.some(item => item.fonte === null)) throw new Error('Há caracteres sem fonte compatível. Adicione uma fonte que os contenha; para sorteio, use prioridade maior que 0.');
        const result = await api('/api/renderizar', 'POST', {letras: enriched(letras), opcoes: layout()});
        if (current !== revision) return;
        svgAtual = result.svg;
        $('canvas-texto').innerHTML = result.svg;
        $('exportar').disabled = !letras.some(item => !/^\s$/u.test(item.char));
        status('Preview pronto. O SVG exportado contém estes mesmos contornos.');
    } catch (error) {
        if (current === revision) status(error.message, true);
    }
}
function updateText() {
    letras = Composition.reconcile($('input-frase').value, letras, fontes,
        $('check-aleatorio-digitar').checked, $('evitar-repeticao').checked);
    selected = null;
    $('editor-letra').hidden = true;
    scheduleRender();
    scheduleSamples();
}
function scheduleSamples() {
    const current = ++sampleRevision;
    clearTimeout(sampleTimer);
    sampleTimer = setTimeout(() => renderSamples(current), 100);
}
async function renderSamples(current) {
    const text = Array.from($('input-frase').value.normalize('NFC'));
    await Promise.all(fontes.map(async font => {
        const container = $(`amostra-${font.id}`);
        if (!container) return;
        if (!text.length) { container.textContent = 'Digite seu texto para ver esta fonte.'; return; }
        if (!font.disponivel) { container.textContent = font.erro; return; }
        try {
            const sample = text.map(char => ({char, fonte: font.id}));
            const result = await api('/api/renderizar', 'POST', {letras: enriched(sample),
                opcoes: {...layout(), tamanho: 32, margem: 12, alinhamento: 'left', cor: '#ffffff'}});
            if (current === sampleRevision) container.innerHTML = result.svg;
        } catch (error) {
            if (current === sampleRevision) container.textContent = error.message;
        }
    }));
}
function element(tag, text, parent) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (parent) parent.append(node);
    return node;
}
function numeric(parent, label, value, min, max, step, change) {
    const wrapper = element('label', label, parent);
    const input = element('input', '', wrapper);
    Object.assign(input, {type: 'number', value, min, max, step});
    input.addEventListener('change', async () => {
        if (!input.reportValidity()) return;
        try { await change(Number(input.value)); } catch (error) { status(error.message, true); }
    });
    return input;
}
function renderLibrary() {
    const list = $('lista-gerenciamento');
    list.replaceChildren();
    if (!fontes.length) element('p', 'Adicione uma fonte para começar.', list);
    for (const font of fontes) {
        const card = element('article', '', list);
        card.className = 'item-fonte';
        card.dataset.fontId = font.id;
        const name = element('strong', font.nome, card);
        name.className = 'nome-fonte';
        const sample = element('div', '', card);
        sample.className = 'amostra';
        sample.id = `amostra-${font.id}`;
        const controls = element('div', '', card);
        controls.className = 'controles';
        numeric(controls, 'Prioridade no sorteio', font.peso, 0, 1000, 1, async value => {
            await api(`/api/fontes/${font.id}/peso`, 'PUT', {peso: value});
            font.peso = value;
        });
        if (font.disponivel) {
            const config = settings.get(font.id);
            numeric(controls, 'Tamanho relativo (%)', config.escala * 100, 25, 400, 1, value => {
                config.escala = value / 100;
                scheduleRender(); scheduleSamples();
            });
            const axesInputs = new Map();
            let variants;
            if (font.eixos.length) {
                variants = element('select', '', element('label', 'Variação do arquivo', controls));
                element('option', 'Personalizada / padrão', variants).value = '';
                font.variacoes.forEach((variant, index) => { element('option', variant.nome, variants).value = index; });
                variants.onchange = () => {
                    config.eixos = variants.value === '' ? Object.fromEntries(font.eixos.map(axis => [axis.tag, axis.default]))
                        : {...font.variacoes[Number(variants.value)].eixos};
                    axesInputs.forEach((input, tag) => { input.value = config.eixos[tag]; });
                    scheduleRender(); scheduleSamples();
                };
                for (const axis of font.eixos) {
                    axesInputs.set(axis.tag, numeric(controls, `${axis.nome} (${axis.tag})`, config.eixos[axis.tag], axis.min, axis.max, 'any', value => {
                        config.eixos[axis.tag] = value;
                        variants.value = '';
                        scheduleRender(); scheduleSamples();
                    }));
                }
            } else element('span', `Estilo: ${font.estilo} · arquivo sem eixos variáveis`, controls);
        }
        const remove = element('button', 'Remover', controls);
        remove.onclick = async () => {
            try { await api(`/api/fontes/${font.id}`, 'DELETE'); await loadFonts(); }
            catch (error) { status(error.message, true); }
        };
    }
}
async function loadFonts() {
    invalidate();
    fontes = await api('/api/fontes');
    for (const font of fontes) {
        if (!settings.has(font.id)) settings.set(font.id, {escala: 1,
            eixos: Object.fromEntries((font.eixos || []).map(axis => [axis.tag, axis.default]))});
    }
    renderLibrary();
    updateText();
}
function showSelection(index) {
    selected = index;
    const item = letras[index];
    $('letra-selecionada').textContent = `Caractere ${index + 1}: ${item.char}`;
    $('fonte-letra').replaceChildren();
    for (const font of fontes.filter(font => Composition.supports(font, item.char))) {
        const option = element('option', font.nome, $('fonte-letra'));
        option.value = font.id;
    }
    $('fonte-letra').value = item.fonte;
    $('travar-letra').checked = item.travada;
    $('editor-letra').hidden = false;
    $('opcoes-letra').replaceChildren();
    for (const font of fontes.filter(font => Composition.supports(font, item.char))) {
        const button = element('button', '', $('opcoes-letra'));
        button.setAttribute('aria-label', `Usar ${font.nome}`);
        const thumbnail = element('div', '', button);
        element('span', font.nome, button);
        button.onclick = () => {
            letras[index].fonte = font.id;
            $('fonte-letra').value = font.id;
            scheduleRender();
        };
        api('/api/renderizar', 'POST', {letras: enriched([{char: item.char, fonte: font.id}]),
            opcoes: {tamanho: 40, largura: 120, margem: 8, alinhamento: 'center'}})
            .then(result => { if (button.isConnected) thumbnail.innerHTML = result.svg; })
            .catch(error => { if (button.isConnected) button.title = error.message; });
    }
}
$('canvas-texto').onclick = event => {
    const path = event.target.closest('path[data-index]');
    if (!path) return;
    const index = Number(path.dataset.index);
    if ($('modo').value === 'ciclo') {
        const pool = fontes.filter(font => Composition.supports(font, letras[index].char));
        const position = pool.findIndex(font => font.id === letras[index].fonte);
        letras[index].fonte = pool[(position + 1) % pool.length].id;
        scheduleRender();
    }
    showSelection(index);
};
$('fonte-letra').onchange = () => { if (selected !== null) { letras[selected].fonte = Number($('fonte-letra').value); scheduleRender(); } };
$('travar-letra').onchange = () => { if (selected !== null) letras[selected].travada = $('travar-letra').checked; };
$('input-frase').oninput = updateText;
$('controles-layout').oninput = () => { scheduleRender(); scheduleSamples(); };
$('aleatorizar').onclick = () => {
    letras = Composition.shuffle(letras, fontes, $('evitar-repeticao').checked);
    if (selected !== null) showSelection(selected);
    scheduleRender();
};
$('exportar').onclick = () => {
    if (!svgAtual || $('exportar').disabled) return;
    const url = URL.createObjectURL(new Blob([svgAtual], {type: 'image/svg+xml;charset=utf-8'}));
    const anchor = element('a');
    anchor.href = url;
    anchor.download = 'texto_misturado.svg';
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
};
for (const [formId, createBody] of [
    ['upload-form', () => { const body = new FormData(); body.append('arquivo', $('arquivo-fonte').files[0]); return body; }],
    ['google-form', () => ({nome: $('nova-fonte-google').value.trim()})]
]) {
    $(formId).onsubmit = async event => {
        event.preventDefault();
        const button = event.currentTarget.querySelector('button');
        button.disabled = true;
        try {
            await api('/api/fontes', 'POST', createBody());
            $(formId).reset();
            await loadFonts();
        } catch (error) { status(error.message, true); }
        finally { button.disabled = false; }
    };
}
loadFonts().catch(error => status(error.message, true));
