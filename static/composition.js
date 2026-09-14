(function (root) {
    'use strict';
    function supports(font, char) {
        return font.disponivel && (char === '\n' || font.caracteres.includes(char.codePointAt(0)));
    }
    function choose(fonts, char, previous, avoidRepeat, random = Math.random) {
        let pool = fonts.filter(f => supports(f, char) && Number(f.peso) > 0);
        if (avoidRepeat && pool.some(f => f.id !== previous)) pool = pool.filter(f => f.id !== previous);
        const total = pool.reduce((sum, f) => sum + Number(f.peso), 0);
        let draw = random() * total;
        for (const font of pool) {
            draw -= Number(font.peso);
            if (draw < 0) return font.id;
        }
        return pool.at(-1)?.id ?? null;
    }
    function reconcile(text, old, fonts, randomise, avoidRepeat) {
        const next = [];
        for (const [i, char] of Array.from(text.normalize('NFC')).entries()) {
            const existing = old[i];
            if (existing?.char === char && fonts.some(f => f.id === existing.fonte && supports(f, char))) {
                next.push(existing);
            } else {
                const fonte = randomise ? choose(fonts, char, next.at(-1)?.fonte, avoidRepeat)
                    : fonts.find(f => supports(f, char))?.id ?? null;
                next.push({char, fonte, travada: false});
            }
        }
        return next;
    }
    function shuffle(letters, fonts, avoidRepeat, random = Math.random) {
        const next = [];
        for (const item of letters) {
            next.push(item.travada || /^\s$/u.test(item.char) ? {...item}
                : {...item, fonte: choose(fonts, item.char, next.at(-1)?.fonte, avoidRepeat, random)});
        }
        return next;
    }
    const api = {supports, choose, reconcile, shuffle};
    if (typeof module !== 'undefined') module.exports = api;
    else root.Composition = api;
})(globalThis);
