# 伊勢物語（嵯峨本）TEI の生成・検証・派生
# 必要: python3, jing, saxon（XSLT 3.0）, curl
.PHONY: all fetch tei validate geojson

all: tei validate geojson

fetch:
	./scripts/fetch.zsh

tools/tei_all.rng:
	mkdir -p tools && curl -sSfL -o $@ https://tei-c.org/release/xml/tei/custom/schema/relaxng/tei_all.rng

tei:
	python3 -I scripts/yatanavi2tei.py

validate: tools/tei_all.rng
	jing tools/tei_all.rng tei/ise.tei.xml && echo "valid: tei/ise.tei.xml"

# 地名の点（kiko-tei の XSLT をそのまま使う）
geojson:
	saxon -s:tei/ise.tei.xml -xsl:../kiko-tei/xslt/tei2geojson.xsl > data/ise-places.geojson
