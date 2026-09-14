const {test} = require('node:test');
const assert = require('node:assert/strict');
const {choose, reconcile, shuffle} = require('../static/composition.js');
const fonts = [1, 2, 3].map(id => ({id, peso: id, disponivel: true, caracteres: [65, 66, 32, 233, 0x1f600]}));

test('weighted choice respects interval boundaries', () => {
    assert.equal(choose(fonts, 'A', null, false, () => 0), 1);
    assert.equal(choose(fonts, 'A', null, false, () => 1 / 6), 2);
    assert.equal(choose(fonts, 'A', null, false, () => .5), 3);
});
test('zero priority excludes every font without silent fallback', () => {
    assert.equal(choose(fonts.map(f => ({...f, peso: 0})), 'A', null, false), null);
});
test('unsupported glyphs and unavailable fonts are excluded', () => {
    assert.equal(choose(fonts, '中', null, false), null);
    assert.equal(choose(fonts.map(f => ({...f, disponivel: false})), 'A', null, false), null);
});
test('avoid repeats when alternatives exist', () => {
    assert.equal(choose(fonts, 'A', 1, true, () => 0), 2);
    assert.equal(choose([fonts[0]], 'A', 1, true, () => 0), 1);
});
test('typing preserves existing choices', () => {
    const previous = [{char: 'A', fonte: 2, travada: true}];
    const next = reconcile('AB', previous, fonts, true, false);
    assert.deepEqual(next[0], previous[0]);
});
test('removed font is replaced with a compatible font', () => {
    assert.equal(reconcile('A', [{char: 'A', fonte: 99}], fonts, false, false)[0].fonte, 1);
});
test('Unicode supplementary character remains one object and accents normalise', () => {
    const next = reconcile('😀e\u0301', [], fonts, false, false);
    assert.equal(next.length, 2);
    assert.equal(next[1].char, 'é');
});
test('shuffle preserves locked letters and spaces without mutating old state', () => {
    const old = [{char: 'A', fonte: 1, travada: true}, {char: ' ', fonte: 1}, {char: 'B', fonte: 1}];
    const next = shuffle(old, fonts, false, () => .9);
    assert.equal(next[0].fonte, 1);
    assert.equal(next[1].fonte, 1);
    assert.equal(next[2].fonte, 3);
    assert.equal(old[2].fonte, 1);
});
test('deterministic sample follows 1:2:3 priority distribution', () => {
    const counts = {1: 0, 2: 0, 3: 0};
    for (let i = 0; i < 6000; i++) counts[choose(fonts, 'A', null, false, () => (i + .5) / 6000)]++;
    assert.deepEqual(counts, {1: 1000, 2: 2000, 3: 3000});
});
