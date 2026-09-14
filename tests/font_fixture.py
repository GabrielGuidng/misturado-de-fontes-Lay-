from pathlib import Path

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor, InstanceDescriptor
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.varLib import build


def make_font(path, width=500):
    builder = FontBuilder(1000, isTTF=True)
    names = ['.notdef', 'space', 'A', 'B', 'amp', 'less', 'greater', 'e', 'acute', 'eacute', 'g', 'smile']
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({32: 'space', 65: 'A', 66: 'B', 38: 'amp', 60: 'less',
                               62: 'greater', 101: 'e', 233: 'eacute', 103: 'g', 0x1F600: 'smile'})
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(glyphs)
        if name == 'eacute':
            pen.addComponent('e', (1, 0, 0, 1, 0, 0))
            pen.addComponent('acute', (1, 0, 0, 1, 100, 200))
        elif name != 'space':
            bottom, top = (-200, 700) if name == 'g' else (0, 700)
            pen.moveTo((-30, bottom))
            pen.lineTo((width, bottom))
            pen.lineTo((width, top))
            pen.lineTo((-30, top))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (width + 80, -30) for name in names})
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    builder.setupNameTable({'familyName': 'Teste Vetorial', 'styleName': 'Regular',
                           'uniqueFontIdentifier': 'TesteVetorial', 'fullName': 'Teste Vetorial Regular',
                           'psName': 'TesteVetorial-Regular'})
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-200, usWinAscent=900, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)


def make_variable(directory):
    directory = Path(directory)
    document = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.name, axis.tag = 'Weight', 'wght'
    axis.minimum, axis.default, axis.maximum = 100, 100, 900
    document.addAxis(axis)
    for weight, width in [(100, 300), (900, 750)]:
        path = directory / f'master-{weight}.ttf'
        make_font(path, width)
        source = SourceDescriptor()
        source.path, source.name = str(path), f'master-{weight}'
        source.familyName, source.styleName = 'Teste Vetorial', str(weight)
        source.location = {'Weight': weight}
        source.copyInfo = source.copyLib = source.copyFeatures = weight == 100
        document.addSource(source)
        instance = InstanceDescriptor()
        instance.familyName = 'Teste Vetorial'
        instance.styleName = 'Leve' if weight == 100 else 'Pesada'
        instance.location = {'Weight': weight}
        document.addInstance(instance)
    font, _, _ = build(document)
    path = directory / 'variable.ttf'
    font.save(path)
    font.close()
    return path
