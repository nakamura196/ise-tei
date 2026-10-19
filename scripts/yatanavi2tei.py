#!/usr/bin/env python3
"""やたがらすナビの嵯峨本『伊勢物語』翻刻を TEI/XML にする。

    python3 -I scripts/yatanavi2tei.py            # tei/ise.tei.xml を書き出す

材料（先に scripts/fetch.zsh で取ってくる）:
- source/yatanavi/txt/sag_ise*.txt  段ごとの DokuWiki 記法。「===== 翻刻 =====」の節だけを使う
  （校訂本文は CC BY-SA 4.0 なので使わない）
- source/manifest-200024817.json    国書データベースの IIIF マニフェスト（嵯峨本・鉄心斎文庫）
- data/places.tsv                   地名の台帳（listPlace になる）
- data/annotations.tsv              どの段のどの文字列に placeName を付けるか

翻刻の約束（やたがらすナビの凡例より）:
- 行末の「／s17l」は「ここまでが国書データベースの 17 コマ目の左半分」の意味。
  段の途中でコマが終わらなくても、段の終わりには印が付く
- 【絵】は挿絵。字下げ「　　」で始まる行は歌
"""
import csv
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
TXT = ROOT / 'source/yatanavi/txt'
MANIFEST = ROOT / 'source/manifest-200024817.json'
OUT = ROOT / 'tei/ise.tei.xml'
MARK = re.compile(r'／s(\d+)([lr])$')
YATA = 'https://yatanavi.org/text/ise/'


def attr(v):
    return escape(str(v), {'"': '&quot;'})


def read_honkoku(path):
    """翻刻の節を行の並びにする。[(kind, text, waka, mark)]"""
    s = path.read_text(encoding='utf-8')
    i = s.find('===== 翻刻 =====')
    if i < 0:
        return []
    out = []
    for raw in s[i:].splitlines()[1:]:
        if raw.startswith('====='):
            break
        if not raw.startswith('  '):
            continue  # 空行・コマへのリンク
        line = raw[2:].rstrip()
        mark = None
        m = MARK.search(line)
        if m:
            mark = (int(m.group(1)), m.group(2))
            line = line[:m.start()]
        if line == '【絵】':
            out.append(('figure', '', False, mark))
            continue
        waka = line.startswith('　　') and path.stem != 'sag_iseoku'
        out.append(('line', line.lstrip('　') if waka else line, waka, mark))
    return out


def dan_of(stem):
    m = re.fullmatch(r'sag_ise(\d{3})[a-z]?', stem)
    return int(m.group(1)) if m else 'oku'


def load_tsv(path):
    with path.open(encoding='utf-8') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def main():
    files = sorted(p for p in TXT.glob('sag_ise*.txt'))
    if not files:
        sys.exit('source/ がありません。先に scripts/fetch.zsh を実行してください')
    canvases = json.loads(MANIFEST.read_text())['sequences'][0]['canvases']
    places = load_tsv(ROOT / 'data/places.tsv')
    pid = {p['id'] for p in places}
    ann = load_tsv(ROOT / 'data/annotations.tsv')
    for a in ann:
        if a['place'] not in pid:
            sys.exit(f'annotations.tsv: 台帳に無い地名 {a["place"]}')

    # 全段を通した行の並び。各行のコマは「次に現れる印」で決まる
    items = []
    for f in files:
        rows = read_honkoku(f)
        for k, (kind, text, waka, mark) in enumerate(rows):
            items.append({'dan': dan_of(f.stem), 'file': f.stem, 'first': k == 0,
                          'kind': kind, 'text': text, 'waka': waka, 'mark': mark})
    page = None
    for it in reversed(items):
        if it['mark']:
            page = it['mark']
        if page is None:
            sys.exit(f'{it["file"]}: コマの印の無い行が末尾にあります')
        it['page'] = page

    used_pages = []
    for it in items:
        if not used_pages or used_pages[-1] != it['page']:
            used_pages.append(it['page'])

    # 段ごとに組む
    dans = []
    for it in items:
        if not dans or dans[-1]['dan'] != it['dan']:
            dans.append({'dan': it['dan'], 'items': []})
        dans[-1]['items'].append(it)

    stats = {'placeName': 0, 'unmatched': []}
    state = {'page': None, 'lineno': {}}
    body = [build_dan(d, ann, state, stats) for d in dans]
    for a in stats['unmatched']:
        print(f'警告: {a["dan"]} 段で見つからない: {a["match"]}', file=sys.stderr)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(header(places) + facsimile(used_pages, canvases)
                   + '  <text>\n    <body>\n' + ''.join(body)
                   + '    </body>\n  </text>\n</TEI>\n', encoding='utf-8')
    n_lines = sum(1 for it in items if it['kind'] == 'line')
    print(f'{OUT.relative_to(ROOT)}: 段 {len(dans)}・行 {n_lines}・半丁 {len(used_pages)}'
          f'・placeName {stats["placeName"]}')


def zone_id(page):
    return f'z{page[0]:03d}{page[1]}'


def build_dan(d, ann, state, stats):
    """1 段を <div> にする。文字位置の上に「開き・閉じ・空要素」を置いてから書き出す。"""
    text = ''
    at = {}  # 位置 -> 空要素の並び（pb, lb, figure, milestone）
    lines = []  # (start, end, waka)
    for it in d['items']:
        pos = len(text)
        ev = at.setdefault(pos, [])
        if it['first']:
            ev.append(f'<milestone unit="yatanavi" corresp="{YATA}{it["file"]}"/>')
        if state['page'] != it['page']:
            state['page'] = it['page']
            p = it['page']
            ev.append(f'<pb n="{p[0]}{p[1]}" facs="#{zone_id(p)}"/>')
        if it['kind'] == 'figure':
            ev.append('<figure><figDesc>挿絵</figDesc></figure>')
            continue
        p = it['page']
        n = state['lineno'][p] = state['lineno'].get(p, 0) + 1
        ev.append(f'<lb n="{p[0]}{p[1]}-{n:02d}"/>')
        text += it['text']
        lines.append((pos, len(text), it['waka']))

    spans = []  # (start, end, open, close, rank)  rank が小さいほど外側
    k = 0
    while k < len(lines):
        if lines[k][2]:
            j = k
            while j + 1 < len(lines) and lines[j + 1][2]:
                j += 1
            spans.append((lines[k][0], lines[j][1], '<seg type="waka">', '</seg>', 0))
            k = j + 1
        else:
            k += 1
    for a in ann:
        if str(a['dan']) != str(d['dan']):
            continue
        m = re.fullmatch(r'(.*)\{(.+)\}(.*)', a['match'])
        pre, core, post = m.groups() if m else ('', a['match'], '')
        hits = [h.start() + len(pre) for h in re.finditer(re.escape(pre + core + post), text)]
        if not hits:
            stats['unmatched'].append(a)
        typ = f' type="{attr(a["type"])}"' if a['type'] else ''
        for h in hits:
            spans.append((h, h + len(core), f'<placeName ref="#{a["place"]}"{typ}>', '</placeName>', 1))
            stats['placeName'] += 1
    check_nesting(spans, d['dan'])

    opens, closes = {}, {}
    for s in sorted(spans, key=lambda s: (s[0], s[4], -s[1])):
        opens.setdefault(s[0], []).append(s[2])
    for s in sorted(spans, key=lambda s: (s[1], -s[4], -s[0])):
        closes.setdefault(s[1], []).append(s[3])

    out = []
    for i in range(len(text) + 1):
        out += closes.get(i, [])
        out += at.get(i, [])
        out += opens.get(i, [])
        if i < len(text):
            out.append(escape(text[i]))
    xid = f'dan{d["dan"]:03d}' if d['dan'] != 'oku' else 'oku'
    n = d['dan']
    typ = 'dan' if n != 'oku' else 'colophon'
    # 空要素の前で改行して、行ごとに読めるようにする
    xml = ''.join(out).replace('<pb ', '\n<pb ').replace('<lb ', '\n<lb ')
    xml = '\n'.join('          ' + x for x in xml.strip().split('\n'))
    return (f'      <div type="{typ}" n="{n}" xml:id="{xid}">\n        <ab>\n{xml}\n'
            f'        </ab>\n      </div>\n')


def check_nesting(spans, dan):
    for a in spans:
        for b in spans:
            if a is not b and a[0] < b[0] < a[1] < b[1]:
                sys.exit(f'{dan} 段: 要素が交差します {a[2]} と {b[2]}')


def facsimile(pages, canvases):
    by_n = {}
    for p in pages:
        by_n.setdefault(p[0], []).append(p[1])
    out = ['  <facsimile sameAs="https://kokusho.nijl.ac.jp/biblio/200024817/manifest">\n']
    for n, halves in by_n.items():
        c = canvases[n - 1]
        if c['label'] != str(n):
            sys.exit(f'コマ {n} がマニフェストの {n} 番目にありません')
        w, h = c['width'], c['height']
        svc = c['images'][0]['resource']['service']['@id']
        out.append(f'    <surface xml:id="c{n:03d}" sameAs="{attr(c["@id"])}" ulx="0" uly="0" lrx="{w}" lry="{h}">\n'
                   f'      <graphic url="{attr(svc)}/full/full/0/default.jpg" width="{w}px" height="{h}px"/>\n')
        for half in halves:
            ulx, lrx = (w // 2, w) if half == 'r' else (0, w // 2)
            out.append(f'      <zone xml:id="{zone_id((n, half))}" ulx="{ulx}" uly="0" lrx="{lrx}" lry="{h}"/>\n')
        out.append('    </surface>\n')
    out.append('  </facsimile>\n')
    return ''.join(out)


def header(places):
    lp = []
    for i, p in enumerate(places, 1):
        idno = f'\n              <idno type="wikidata">{p["wikidata"]}</idno>' if p['wikidata'] else ''
        lp.append(f'''            <place xml:id="{p['id']}" type="{p['type']}" n="{i}" cert="{p['cert']}">
              <placeName>{escape(p['name'])}</placeName>
              <location><geo>{p['lat']} {p['lon']}</geo></location>
              <note>{escape(p['note'])}</note>{idno}
            </place>
''')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="ja">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>伊勢物語（嵯峨本）</title>
        <respStmt>
          <resp>翻刻</resp>
          <name ref="https://yatanavi.org/text/ise/">中川聡（やたがらすナビ）</name>
        </respStmt>
        <respStmt xml:id="snakamura">
          <resp>TEI 符号化・地名の付与</resp>
          <name>中村覚（東京大学）</name>
        </respStmt>
      </titleStmt>
      <publicationStmt>
        <authority>中村覚（東京大学）</authority>
        <availability>
          <p>翻刻はやたがらすナビの表示により著作権が存在しない。TEI の符号化と地名の付与は
            <ref target="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</ref>。</p>
        </availability>
      </publicationStmt>
      <sourceDesc>
        <bibl type="witness">
          <title>伊勢物語</title>
          <note>嵯峨本。慶長13年（1608）刊。2巻。</note>
          <orgName>国文学研究資料館</orgName>
          <note type="collection">鉄心斎文庫</note>
          <idno type="DOI">10.20730/200024817</idno>
          <ref target="https://kokusho.nijl.ac.jp/biblio/200024817">国書データベース</ref>
        </bibl>
        <bibl type="transcription">
          <title>嵯峨本『伊勢物語』</title>
          <editor>中川聡</editor>
          <publisher>やたがらすナビ</publisher>
          <edition>Ver.1.0（2024-03-04）</edition>
          <ref target="https://yatanavi.org/_media/text/ise/ise_1.0.zip">ise_1.0.zip</ref>
        </bibl>
      </sourceDesc>
    </fileDesc>
    <encodingDesc>
      <p>本文はやたがらすナビの「翻刻」をそのまま用いた（校訂本文は用いない）。翻刻では、漢字の直後のものを除き、繰り返し記号を開いてある。</p>
      <p>pb の n は国書データベースのコマ番号と見開きの左右（r＝右、l＝左）。左右の領域は画像を縦に二等分した近似値で、のどの位置は測っていない。</p>
      <p>地名（placeName）は九段だけに付けた。type="comparison" はたとえとして出る地名。</p>
    </encodingDesc>
    <profileDesc>
      <settingDesc>
        <listPlace>
{''.join(lp)}        </listPlace>
      </settingDesc>
    </profileDesc>
  </teiHeader>
'''


if __name__ == '__main__':
    main()
