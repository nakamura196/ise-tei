#!/usr/bin/env python3
"""TEI から DLM の一括取り込み（POST /api/projects/:id/import）用の JSON を作る。

- 地名（listPlace の place）1 件 = DLM のピン 1 件。タグ「伊勢物語」を付ける
- 用例 = 場面 1 つ × そこに出る地名 1 つ。本文はその場面の本文と歌（版面の改行はつなぎ、歌だけ 1 行に分ける）。
  場面はやたがらすナビの区切り（挿絵ごと）を基本とし、SCENE_STARTS で更に分ける
- 資料「伊勢物語（嵯峨本）」を 1 件作り、用例はそこに属させる。ピンにも資料名 materialNames を付ける
  （取り込み窓口はピンの資料を受け付けないので、scripts/reload-dlm.mjs が取り込み後に付け直す）

使い方: python3 scripts/tei2dlm.py > data/dlm-import.json
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
ROOT = Path(__file__).resolve().parent.parent
MATERIAL = "伊勢物語（嵯峨本）"
TAG = "伊勢物語"
CERT_JA = {"high": "高", "medium": "中", "low": "低"}


# 翻刻元（やたがらすナビ）の区切り（挿絵ごと）の中に場面が 2 つある段。
# 段の番号 → 後の場面の書き出し（本文を改行なしでつないだ文字列で探す）
SCENE_STARTS = {
    69: ["野にありけと"],          # 伊勢での逢瀬 / 尾張へ発つ朝（逢坂の関）
    82: ["とてその木のもとはたちて"],  # 渚の院の桜 / 天の川
    87: ["このおとこなま宮つかへ"],  # 芦屋 / 布引の滝
}


def dan_label(n):
    return f"{n}段"


def flatten(div):
    """段を 1 文字ずつの列にする。各文字に (地名 id, 歌か, 丁) を持たせ、
    やたがらすナビの区切りを印として挟む。版面の改行（lb）はつなぐ。
    段が丁の途中から始まるときは、前の段の最後の丁を引き継ぐ（_last_page）。"""
    out = []
    page = _last_page

    def walk(el, outer_ref, outer_waka):
        tag = el.tag.replace(TEI, "")
        ref, waka = outer_ref, outer_waka
        if tag in ("figure", "note"):
            pass
        else:
            if tag == "milestone" and el.get("unit") == "yatanavi":
                out.append(("ms", el.get("corresp")))
            elif tag == "pb":
                page[0] = (el.get("n"), (el.get("facs") or "").lstrip("#"))
            if tag == "placeName":
                ref = (el.get("ref") or "").lstrip("#")
            if tag == "seg" and el.get("type") == "waka":
                waka = True
            for ch in el.text or "":
                if not ch.isspace():
                    out.append(("c", ch, ref, waka, page[0]))
            for c in el:
                walk(c, ref, waka)
        for ch in el.tail or "":
            if not ch.isspace():
                out.append(("c", ch, outer_ref, outer_waka, page[0]))

    for c in div:
        walk(c, None, False)
    return out


_last_page = [None]


def scenes_of(div, n):
    """段を場面に分ける。場面 = やたがらすナビの区切り 1 つ（SCENE_STARTS で更に分ける）。"""
    toks = flatten(div)
    segs, cur = [], None
    for t in toks:
        if t[0] == "ms":
            cur = {"url": t[1], "toks": []}
            segs.append(cur)
        else:
            cur["toks"].append(t)
    for anchor in SCENE_STARTS.get(n, []):
        for i, sg in enumerate(segs):
            text = "".join(t[1] for t in sg["toks"])
            k = text.find(anchor)
            if k > 0:
                tail = {"url": sg["url"], "toks": sg["toks"][k:]}
                sg["toks"] = sg["toks"][:k]
                segs.insert(i + 1, tail)
                break
        else:
            sys.exit(f"{n}段: 場面の書き出し「{anchor}」が見つからない")
    return [sg for sg in segs if sg["toks"]]


def scene_body(toks):
    """本文。歌は前後で改行して 1 行にする（版面の改行はつなぐ）。"""
    lines, buf, in_waka = [], [], False
    for _, ch, _, waka, _ in toks:
        if waka != in_waka:
            if buf:
                lines.append("".join(buf))
            buf, in_waka = [], waka
        buf.append(ch)
    if buf:
        lines.append("".join(buf))
    waka, cur, prev = [], [], False
    for _, ch, _, w, _ in toks:
        if w:
            cur.append(ch)
        elif prev:
            waka.append("".join(cur))
            cur = []
        prev = w
    if cur:
        waka.append("".join(cur))
    return "\n".join(lines), waka


def main():
    tree = ET.parse(ROOT / "tei/ise.tei.xml")
    root = tree.getroot()

    zone_canvas = {}
    for surf in root.iter(f"{TEI}surface"):
        for z in surf.iter(f"{TEI}zone"):
            zone_canvas[z.get(XML_ID)] = surf.get("sameAs")
    manifest = root.find(f".//{TEI}facsimile").get("sameAs")

    places = {}
    for pl in root.iter(f"{TEI}place"):
        pid = pl.get(XML_ID)
        lat, lng = map(float, pl.find(f"{TEI}location/{TEI}geo").text.split())
        note = pl.find(f"{TEI}note")
        places[pid] = {
            "name": pl.find(f"{TEI}placeName").text,
            "type": pl.get("type"),
            "cert": pl.get("cert"),
            "lat": lat,
            "lng": lng,
            "note": note.text if note is not None else "",
            "dans": [],
            "forms": [],
        }
    wikidata = {}
    for line in (ROOT / "data/places.tsv").read_text().splitlines()[1:]:
        cols = line.split("\t")
        wikidata[cols[0]] = cols[3]

    # 本文の表記（地名ごと）
    for div in root.iter(f"{TEI}div"):
        if div.get("type") != "dan":
            continue
        n = int(div.get("n"))
        for pn in div.iter(f"{TEI}placeName"):
            ref = (pn.get("ref") or "").lstrip("#")
            if ref not in places:
                continue
            form = "".join(pn.itertext()).replace("\n", "").replace(" ", "")
            if n not in places[ref]["dans"]:
                places[ref]["dans"].append(n)
            if form not in places[ref]["forms"]:
                places[ref]["forms"].append(form)

    # 用例 = 場面 × その場面に出る地名 1 つ
    yorei = []
    for div in root.iter(f"{TEI}div"):
        if div.get("type") != "dan":
            continue
        n = int(div.get("n"))
        scenes = [sc for sc in scenes_of(div, n) if any(t[2] in places for t in sc["toks"])]
        for i, sc in enumerate(scenes, 1):
            refs = []
            for t in sc["toks"]:
                if t[2] in places and t[2] not in refs:
                    refs.append(t[2])
            body, waka = scene_body(sc["toks"])
            label = dan_label(n) + (f" その{i}" if len(scenes) > 1 else "")
            pages = list(dict.fromkeys(t[4] for t in sc["toks"]))
            canvas = zone_canvas.get(pages[0][1], "")
            for r in refs:
                name = places[r]["name"]
                yorei.append({
                    "title": f"伊勢物語 {label}（{name}）",
                    "author": "",
                    "bodyOriginal": body,
                    "bodyReading": "",
                    "bodyTranslation": "",
                    "context": f"嵯峨本『伊勢物語』{label}（丁 {', '.join(pg[0] for pg in pages)}）",
                    "notes": "翻刻はやたがらすナビ（翻刻部分は著作権なし）。地名の付与と場面の切り分けは ise-tei による",
                    "location": name,
                    "era": "平安時代",
                    "category": "物語",
                    "tags": [TAG],
                    "externalUrl": sc["url"] or "",
                    "metadata": {
                        "段": str(n),
                        "歌": " / ".join(waka),
                        "IIIF manifest": manifest,
                        "IIIF canvas": canvas,
                    },
                    "materialName": MATERIAL,
                    "pinNames": [name],
                })

    pins = []
    for pid, p in places.items():
        if not p["dans"]:
            continue
        dans = sorted(p["dans"])
        desc = f"『伊勢物語』{'・'.join(dan_label(d) for d in dans)}に出る地名。"
        if p["cert"] == "low":
            desc += "位置はおおよそ（確からしさ: 低）。"
        md = {
            "作品": "伊勢物語",
            "段": ", ".join(map(str, dans)),
            "本文の表記": "、".join(p["forms"]),
            "種類": p["type"],
            "位置の確からしさ": CERT_JA.get(p["cert"], p["cert"]),
            "座標の注記": p["note"],
            "出所": "ise-tei（嵯峨本 TEI）",
            "ise-tei id": pid,
        }
        if wikidata.get(pid):
            md["Wikidata"] = wikidata[pid]
        pins.append({
            "title": p["name"],
            "description": desc,
            "lat": p["lat"],
            "lng": p["lng"],
            "tags": [TAG],
            "metadata": md,
            "materialNames": [MATERIAL],
        })

    out = {
        "materials": [{
            "title": MATERIAL,
            "type": "文献",
            "author": "",
            "year": "慶長13年（1608）",
            "source": "国文学研究資料館 鉄心斎文庫 200024817",
            "url": "https://kokusho.nijl.ac.jp/biblio/200024817",
            "imageUrl": "",
            "description": "嵯峨本『伊勢物語』。翻刻はやたがらすナビ（https://yatanavi.org/text/ise/）。",
        }],
        "pins": pins,
        "yorei": yorei,
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
