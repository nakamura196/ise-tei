#!/usr/bin/env zsh
# 変換の材料を source/ に取ってくる（git 管理外）。
#
# - やたがらすナビ 嵯峨本『伊勢物語』のソース（段ごとの txt、DokuWiki 記法）
#   翻刻部分は「著作権が存在しません」と明記。校訂本文は CC BY-SA 4.0 なので、変換では使わない
# - 国書データベース 200024817（嵯峨本、国文研 鉄心斎文庫、PDM）の IIIF マニフェスト
#
# 使い方: ./scripts/fetch.zsh
set -euo pipefail
cd "${0:A:h}/.."

mkdir -p source/yatanavi
curl -sSfL -o source/yatanavi/ise_1.0.zip https://yatanavi.org/_media/text/ise/ise_1.0.zip
rm -rf source/yatanavi/txt
unzip -q -o source/yatanavi/ise_1.0.zip -d source/yatanavi/txt
curl -sSfL -o source/manifest-200024817.json https://kokusho.nijl.ac.jp/biblio/200024817/manifest

echo "zip: $(shasum -a 256 source/yatanavi/ise_1.0.zip | cut -d' ' -f1)"
echo "txt: $(ls source/yatanavi/txt/sag_ise*.txt | wc -l | tr -d ' ') 本"
echo "manifest canvases: $(python3 -I -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["sequences"][0]["canvases"]))' source/manifest-200024817.json)"
