# 伊勢物語（嵯峨本）TEI — 歌枕の地名アノテーション

嵯峨本『伊勢物語』（慶長13年＝1608年刊、国文学研究資料館 鉄心斎文庫）の翻刻を TEI/XML にし、
地名に `placeName` を付けて、DLM（東海道分間之図）の「伊勢物語」層の元データにする。
形は[校異源氏物語テキストDB](https://kouigenjimonogatari.github.io/)にならう（翻刻の行と IIIF 画像の対応を持つ TEI）。

いまは試作。全 125 段と奥書を TEI にしてあり、七段以降の全段に地名を付けた（placeName 148 か所・地名 71）。一段〜六段はまだ付けていない。

## 材料

| 材料 | 出典 | 利用条件 |
|---|---|---|
| 翻刻 | [やたがらすナビ 嵯峨本『伊勢物語』](https://yatanavi.org/text/ise/)（中川聡、Ver.1.0、2024-03-04） | 翻刻部分は「著作権が存在しません」と明記。校訂本文（CC BY-SA 4.0）は使わない |
| 画像 | [国書データベース 200024817](https://kokusho.nijl.ac.jp/biblio/200024817)（IIIF、126 コマ） | パブリックドメイン・マーク |
| 地名の座標 | Wikidata（`data/places.tsv` に QID） | CC0 |

材料は `source/`（git 管理外）に取ってくる。

## 作り方

```
make fetch      # やたがらすナビの zip と IIIF マニフェストを source/ に取る
make all        # tei/ise.tei.xml を作り、tei_all で検証し、data/ise-places.geojson を出す
```

- `data/places.tsv` — 地名の台帳。TEI の `listPlace` になる
- `data/annotations.tsv` — どの段のどの文字列に `placeName` を付けるか。
  `{するか}なる` のように書くと、前後の文字で場所を絞り、波括弧の中だけに付ける
- 地名を増やすときは、この 2 つに行を足して `make all`

## TEI の作り

- 段ごとに `<div type="dan" n="9" xml:id="dan009"><ab>`。奥書は `type="colophon"`
- `<pb n="17l" facs="#z017l"/>` — 国書データベースの 17 コマ目の左半分。`facsimile` の `zone` を指す
- `<lb n="17l-03"/>` — その半丁の 3 行目
- 歌は `<seg type="waka">`、挿絵は `<figure>`
- `<milestone unit="yatanavi" corresp="…/sag_ise009b"/>` — やたがらすナビのページの切れ目
- `<placeName ref="#yatsuhashi">`。たとえとして出る地名には `type="comparison"`

## ライセンス

TEI の符号化と地名の付与は CC BY 4.0。翻刻はやたがらすナビの表示に従う（著作権なし）。
