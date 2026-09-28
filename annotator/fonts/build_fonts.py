"""Regenerate the self-hosted web fonts in annotator/fonts/ (build-time only).

The app never runs this; it serves the committed .woff2 files. Run it after the
Chinese copy changes, so the two CJK subsets still cover every character:

    PYTHONPATH=<brotli site-packages> .venv/bin/python annotator/fonts/build_fonts.py <src-dir>

<src-dir> holds the upstream OFL sources, fetched from google/fonts at commit
23e54b51ddffbc7713c583748e3bd86f62b1fa4a (2026-09-24):
    ofl/zillaslab/ZillaSlab-{Regular,Italic,Medium,SemiBold}.ttf
    ofl/barlow/Barlow-{Regular,Medium,SemiBold,Bold}.ttf
    ofl/dmmono/DMMono-{Regular,Medium}.ttf
    ofl/notosanssc/NotoSansSC[wght].ttf      (variable; instanced at 400 and 500)
    ofl/notoserifsc/NotoSerifSC[wght].ttf    (variable; instanced at 400, 500, 700)
and tygfhzb/level-1.txt: level 1 (3,500 hanzi) of 通用规范汉字表, from
github.com/shengdoushi/common-standard-chinese-characters-table at d9b599a.
Laid out as <src-dir>/<family-dir>/<file>. fontTools is in the project venv; the
woff2 writer also needs the `brotli` module (on this host:
/nix/store/gwyaqilhj7najkz88dkmzd7n2npf9kks-python3.14-brotli-1.2.0/lib/python3.14/site-packages).

Only the faces the app renders are built (measured with document.fonts across
every tab in EN and 中). Latin families keep Basic Latin, Latin-1 and the
punctuation, arrows and symbols the copy uses. The CJK families keep exactly the
characters of the Chinese copy in ops.js (`words`), vision-stage.js (`COPY.zh`),
app.js (its zh table) and the two HTML files, plus ASCII and the symbols above.
"""
from pathlib import Path
import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parent
ANNOTATOR = HERE.parent
COPY_FILES = ('ops.js', 'vision-stage.js', 'app.js', 'ops.html', 'app.html')

LATIN = set(range(0x20, 0x7F)) | set(range(0xA0, 0x100)) | {
    0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x2032, 0x2033,
    0x20AC, 0x2122, 0x2190, 0x2191, 0x2192, 0x2193, 0x2197, 0x21BB, 0x2212, 0x2260,
    0x2264, 0x2265, 0x00D7, 0x00B1, 0x00B7, 0x00B0}

# (output file, source file, variable-axis weight or None)
LATIN_FACES = (
    ('zilla-slab-400.woff2', 'zillaslab/ZillaSlab-Regular.ttf'),
    ('zilla-slab-400-italic.woff2', 'zillaslab/ZillaSlab-Italic.ttf'),
    ('zilla-slab-500.woff2', 'zillaslab/ZillaSlab-Medium.ttf'),
    ('zilla-slab-600.woff2', 'zillaslab/ZillaSlab-SemiBold.ttf'),
    ('barlow-400.woff2', 'barlow/Barlow-Regular.ttf'),
    ('barlow-500.woff2', 'barlow/Barlow-Medium.ttf'),
    # Bold body text: plain <strong> in the roster and match rows (seen only with
    # real data, not in the empty fixture) and the 600 weight the type scale uses.
    ('barlow-600.woff2', 'barlow/Barlow-SemiBold.ttf'),
    ('barlow-700.woff2', 'barlow/Barlow-Bold.ttf'),
    ('dm-mono-400.woff2', 'dmmono/DMMono-Regular.ttf'),
    ('dm-mono-500.woff2', 'dmmono/DMMono-Medium.ttf'),
)
CJK_FACES = (
    ('noto-sans-sc-400.woff2', 'notosanssc/NotoSansSC[wght].ttf', 400),
    ('noto-sans-sc-500.woff2', 'notosanssc/NotoSansSC[wght].ttf', 500),
    ('noto-serif-sc-400.woff2', 'notoserifsc/NotoSerifSC[wght].ttf', 400),
    ('noto-serif-sc-500.woff2', 'notoserifsc/NotoSerifSC[wght].ttf', 500),
    ('noto-serif-sc-700.woff2', 'notoserifsc/NotoSerifSC[wght].ttf', 700),
)
# The common-hanzi files exist only for the faces that draw text staff type, measured
# on every tab in 中 and EN (out/impeccable/ledger/typeset/cjk-census.txt): names and
# notes in Barlow 400 (Sans 300-400 face), bold match rows in Barlow 700 (Sans
# 500-900 face), names and the event name in Zilla Slab 500 (Serif 500-600 face;
# the strip's current-match label is set in that same name weight, so no Serif 400
# file is needed). Each is declared with exactly its UI face's weight range: the
# browser composes faces by unicode-range only when every other descriptor matches.
COMMON_FACES = (
    ('noto-sans-sc-400-common.woff2', 'notosanssc/NotoSansSC[wght].ttf', 400),
    ('noto-sans-sc-500-common.woff2', 'notosanssc/NotoSansSC[wght].ttf', 500),
    ('noto-serif-sc-500-common.woff2', 'notoserifsc/NotoSerifSC[wght].ttf', 500),
)


def common_codepoints(src, ui):
    """Level 1 of 通用规范汉字表 (3,500 common hanzi) plus CJK punctuation and the
    full-width forms, minus what the UI file already has: the text staff type
    (names, event names, notes). Served as a second file per face and declared
    with a unicode-range, so a page downloads it only when it shows one of these."""
    level1 = (src / 'tygfhzb' / 'level-1.txt').read_text(encoding='utf-8')
    points = {ord(ch) for ch in level1 if 0x3400 <= ord(ch) <= 0x9FFF}
    assert len(points) == 3500, f'level-1.txt should hold 3500 hanzi, found {len(points)}'
    points |= set(range(0x3000, 0x3040)) | set(range(0xFF01, 0xFF5F))
    return points - ui


def unicode_range(points):
    """The unicode-range for the -common faces: the blocks their code points fall in.

    Coarse on purpose. The UI face of the same family/weight has no unicode-range, so it
    covers everything and is tried first; the browser fetches a -common file only for a
    character the UI face lacks *and* the range includes. An exact per-character list
    (about 18 KB, repeated in each rule) would change nothing but the CSS size."""
    blocks = ((0x3000, 0x303F), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xFF00, 0xFFEF))
    used = [(a, b) for a, b in blocks if any(a <= p <= b for p in points)]
    return ','.join(f'U+{a:X}-{b:X}' for a, b in used)


def copy_codepoints():
    """Every non-ASCII code point in the app's copy files (the CJK subset's text)."""
    points = set()
    for name in COPY_FILES:
        points |= {ord(ch) for ch in (ANNOTATOR / name).read_text(encoding='utf-8') if ord(ch) > 0x7F}
    # Every non-ASCII character of the copy: the CJK text itself, and the arrows and
    # symbols (→ ← ✓ ● ◀ ▶ ◆ ⏎ …) that Barlow and DM Mono lack, which the stacks
    # therefore draw with the Noto face next in line.
    return points | LATIN


def options():
    opts = subset.Options()
    opts.flavor = 'woff2'
    opts.layout_features = ['kern', 'liga', 'calt', 'tnum', 'lnum', 'pnum', 'case', 'locl', 'vert', 'halt', 'palt']
    opts.name_IDs = ['*']            # keep copyright, licence and licence-URL name records
    opts.name_languages = ['*']
    opts.notdef_outline = True
    opts.hinting = False
    opts.desubroutinize = True
    return opts


def build(font, unicodes, out):
    sub = subset.Subsetter(options())
    sub.populate(unicodes=sorted(unicodes))
    sub.subset(font)
    font.flavor = 'woff2'
    font.save(str(out))
    return out.stat().st_size


def main(src):
    src = Path(src)
    cjk = copy_codepoints()
    sizes = []
    for out, rel in LATIN_FACES:
        sizes.append((out, build(TTFont(src / rel), LATIN, HERE / out)))
    common = common_codepoints(src, cjk)
    for faces, points in ((CJK_FACES, cjk), (COMMON_FACES, common)):
        for out, rel, weight in faces:
            # updateFontNames renames the instance from STAT (e.g. "Noto Sans SC Medium"),
            # so a 500 file is not left carrying the default instance's "Thin" name.
            font = instancer.instantiateVariableFont(TTFont(src / rel), {'wght': weight}, updateFontNames=True)
            sizes.append((out, build(font, points, HERE / out)))
    (HERE / 'common-unicode-range.txt').write_text(unicode_range(common) + '\n')
    print(f'common subset: {len(common)} code points; unicode-range in fonts/common-unicode-range.txt')
    print(f'CJK subset: {len(cjk)} code points ({len(cjk - LATIN)} from the copy beyond the Latin set)')
    for out, size in sizes:
        print(f'{size:>9,} B  {out}')
    print(f'{sum(s for _, s in sizes):>9,} B  total')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'out/impeccable/font-src')
