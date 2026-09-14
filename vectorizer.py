"""Contornos e layout compartilhados pelo preview e pelo SVG exportado."""
import math
import re
import xml.etree.ElementTree as ET

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen


def font_metadata(font):
    if not any(table in font for table in ('glyf', 'CFF ', 'CFF2')):
        raise ValueError('A fonte precisa conter contornos vetoriais TTF ou OTF.')
    names = font['name']
    family = names.getDebugName(16) or names.getDebugName(1) or 'Fonte sem nome'
    style = names.getDebugName(17) or names.getDebugName(2) or 'Regular'
    axes, instances = [], []
    if 'fvar' in font:
        for axis in font['fvar'].axes:
            axes.append(dict(tag=axis.axisTag, nome=names.getDebugName(axis.axisNameID) or axis.axisTag,
                             min=axis.minValue, max=axis.maxValue, default=axis.defaultValue))
        for instance in font['fvar'].instances:
            instances.append(dict(nome=names.getDebugName(instance.subfamilyNameID) or 'Variação',
                                  eixos=instance.coordinates))
    return dict(nome=f'{family} — {style}', familia=family, estilo=style, eixos=axes,
                variacoes=instances, caracteres=list((font.getBestCmap() or {}).keys()))


def number(value, minimum, maximum, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f'{label} deve estar entre {minimum} e {maximum}.')
    return float(value)


def fmt(value):
    return format(value, '.8f').rstrip('0').rstrip('.') or '0'


def render_svg(letters, fonts, options):
    if not isinstance(options, dict):
        raise ValueError('Opções inválidas.')
    size = number(options.get('tamanho', 54), 8, 300, 'Tamanho')
    spacing = number(options.get('espacamento', 0), -100, 200, 'Espaçamento')
    leading = number(options.get('entrelinha', 1.4), 0.5, 5, 'Entrelinha')
    width = number(options.get('largura', 1000), 100, 5000, 'Largura')
    margin = number(options.get('margem', 24), 0, min(200, (width - 1) / 2), 'Margem')
    alignment = options.get('alinhamento', 'left')
    if alignment not in ('left', 'center', 'right'):
        raise ValueError('Alinhamento inválido.')
    color = options.get('cor', '#ffffff')
    if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('Cor inválida.')
    wrap = options.get('quebrar', True)
    lines = [[]]
    cursor = 0
    cache = {}
    for index, item in enumerate(letters):
        char = item['char']
        if char == '\n':
            lines.append([])
            cursor = 0
            continue
        if ord(char) < 32:
            raise ValueError('Use espaços ou quebras de linha, sem outros caracteres de controle.')
        font = fonts[item['fonte']]
        glyph_name = (font.getBestCmap() or {}).get(ord(char))
        if glyph_name is None:
            raise ValueError(f'A fonte {font_metadata(font)["nome"]} não contém o caractere {char!r}. Escolha outra fonte.')
        scale = size * number(item.get('escala', 1), 0.25, 4, 'Escala da fonte') / font['head'].unitsPerEm
        location = item.get('eixos', {})
        if not isinstance(location, dict):
            raise ValueError('Eixos inválidos.')
        axes = {axis.axisTag: axis for axis in font['fvar'].axes} if 'fvar' in font else {}
        for tag, value in location.items():
            if tag not in axes:
                raise ValueError(f'Eixo {tag} não existe nesta fonte.')
            number(value, axes[tag].minValue, axes[tag].maxValue, tag)
        key = (item['fonte'], tuple(sorted(location.items())))
        if key not in cache:
            cache[key] = font.getGlyphSet(location=location)
        glyphs = cache[key]
        glyph = glyphs[glyph_name]
        bounds_pen = BoundsPen(glyphs)
        glyph.draw(bounds_pen)
        bounds = bounds_pen.bounds
        left = min(0, bounds[0] * scale) if bounds else 0
        right = max(glyph.width * scale, bounds[2] * scale) if bounds else glyph.width * scale
        advance = glyph.width * scale
        if wrap and lines[-1] and cursor + right - left > width - 2 * margin:
            lines.append([])
            cursor = 0
        lines[-1].append(dict(index=index, char=char, glyph=glyph, glyphs=glyphs,
                              x=cursor, scale=scale, bounds=bounds, advance=advance))
        cursor += advance + spacing

    root = ET.Element('svg', xmlns='http://www.w3.org/2000/svg', version='1.1')
    baseline = 0
    global_left, global_right, global_top, global_bottom = 0, width, 0, 0
    for line_index, line in enumerate(lines):
        left = min([0] + [g['x'] + (g['bounds'][0] * g['scale'] if g['bounds'] else 0) for g in line])
        right = max([0] + [g['x'] + max(g['advance'], g['bounds'][2] * g['scale'] if g['bounds'] else 0) for g in line])
        ascent = max([size * 0.8] + [g['bounds'][3] * g['scale'] for g in line if g['bounds']])
        descent = max([size * 0.2] + [-g['bounds'][1] * g['scale'] for g in line if g['bounds']])
        if line_index == 0:
            baseline = margin + ascent
        else:
            baseline += max(size * leading, previous_descent + ascent + size * (leading - 1))
        previous_descent = descent
        free = width - 2 * margin - (right - left)
        offset = margin - left + (free / 2 if alignment == 'center' else free if alignment == 'right' else 0)
        global_left = min(global_left, offset + left - margin)
        global_right = max(global_right, offset + right + margin)
        global_top = min(global_top, baseline - ascent - margin)
        global_bottom = max(global_bottom, baseline + descent + margin)
        for g in line:
            pen = SVGPathPen(g['glyphs'], ntos=fmt)
            # Achatar a transformação mantém cada caractere como um path editável.
            g['glyph'].draw(TransformPen(pen, (g['scale'], 0, 0, -g['scale'], offset + g['x'], baseline)))
            path = ET.SubElement(root, 'path', id=f'caractere-{g["index"]}',
                                 d=pen.getCommands(), fill=color,
                                 attrib={'data-index': str(g['index']), 'data-char': g['char']})
            ET.SubElement(path, 'title').text = g['char']
    root.set('viewBox', ' '.join(map(fmt, (global_left, global_top, global_right - global_left, global_bottom - global_top))))
    root.set('width', fmt(global_right - global_left))
    root.set('height', fmt(global_bottom - global_top))
    return ET.tostring(root, encoding='unicode')
