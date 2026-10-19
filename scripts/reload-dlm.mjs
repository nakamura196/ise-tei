#!/usr/bin/env node
/**
 * DLM の東海道プロジェクトから伊勢物語の分を消し、data/dlm-import.json を入れ直す。
 *
 * 消すもの: タグ「伊勢物語」のピン・用例、資料「伊勢物語（嵯峨本）」とその用例。
 * 入れ直したあと、ピンに資料を直接ひも付ける（取り込み窓口はピンの資料を受け付けないため、
 * dlm-import.json の pins[].materialNames を見て PUT で付ける）。
 *
 * 使い方（鍵は app/.env.local の op:// 参照から注入する）:
 *   op run --env-file=../app/.env.local -- node scripts/reload-dlm.mjs          # 何が起きるかを表示するだけ
 *   op run --env-file=../app/.env.local -- node scripts/reload-dlm.mjs --apply  # 実行する
 */
import { readFileSync } from "node:fs";

const args = process.argv.slice(2);
const opt = (n, d) => {
  const i = args.indexOf(n);
  return i >= 0 ? args[i + 1] : d;
};
const API = opt("--api", "https://digital-literary-map.vercel.app/api");
const PROJECT = opt("--project", "Fs2np9PlovJypuBKfpyV");
const APPLY = args.includes("--apply");
const TAG = "伊勢物語";
const KEY = process.env.API_SECRET_KEY;
if (!KEY) {
  console.error("API_SECRET_KEY が未設定です。op run 経由で実行してください。");
  process.exit(1);
}
const data = JSON.parse(readFileSync(new URL("../data/dlm-import.json", import.meta.url)));
const materialTitles = new Set(data.materials.map((m) => m.title));

async function call(method, path, body) {
  const r = await fetch(`${API}/projects/${PROJECT}${path}`, {
    method,
    headers: { Authorization: `Bearer ${KEY}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status} ${await r.text()}`);
  return r.status === 204 ? null : r.json();
}

// ---- 1. 消す対象を集める ----
const [pins, materials, yorei] = await Promise.all([call("GET", "/pins"), call("GET", "/materials"), call("GET", "/yorei")]);
const oldMaterials = materials.filter((m) => materialTitles.has(m.title));
const oldMaterialIds = new Set(oldMaterials.map((m) => m.id));
const oldPins = pins.filter((p) => (p.tags ?? []).includes(TAG));
const oldPinIds = new Set(oldPins.map((p) => p.id));
const oldYorei = yorei.filter((y) => (y.tags ?? []).includes(TAG) || oldMaterialIds.has(y.materialId));
const oldYoreiIds = new Set(oldYorei.map((y) => y.id));

// 消さない用例が、消すピンを指していないか（指していたら止める）
const stray = yorei.filter((y) => !oldYoreiIds.has(y.id) && (y.pinIds ?? []).some((id) => oldPinIds.has(id)));
// 消さないピンが、消す資料を指していないか
const strayPins = pins.filter((p) => !oldPinIds.has(p.id) && (p.materialIds ?? []).some((id) => oldMaterialIds.has(id)));

console.log(`現在: ピン ${pins.length}・資料 ${materials.length}・用例 ${yorei.length}`);
console.log(`消す: ピン ${oldPins.length}・資料 ${oldMaterials.length}・用例 ${oldYorei.length}`);
console.log(`入れる: ピン ${data.pins.length}・資料 ${data.materials.length}・用例 ${data.yorei.length}`);
if (stray.length || strayPins.length) {
  console.error("伊勢物語の外のデータが、消すピン・資料を指しています。止めます:");
  for (const y of stray) console.error(`  用例 ${y.id} ${y.title}`);
  for (const p of strayPins) console.error(`  ピン ${p.id} ${p.title}`);
  process.exit(1);
}
if (!APPLY) {
  console.log("（表示だけ。実行するには --apply）");
  process.exit(0);
}

// ---- 2. 消す（用例 → ピン → 資料の順） ----
for (const y of oldYorei) await call("DELETE", `/yorei/${y.id}`);
for (const p of oldPins) await call("DELETE", `/pins/${p.id}`);
for (const m of oldMaterials) await call("DELETE", `/materials/${m.id}`);
console.log("消しました");

// ---- 3. 取り込む ----
const result = await call("POST", "/import", {
  materials: data.materials,
  pins: data.pins.map(({ materialNames, ...p }) => p),
  yorei: data.yorei,
});
console.log("取り込み:", JSON.stringify(result.counts), "警告", (result.warnings ?? []).length);
for (const w of result.warnings ?? []) console.log("  ", JSON.stringify(w));

// ---- 4. ピンに資料を付ける ----
const [pins2, materials2] = await Promise.all([call("GET", "/pins"), call("GET", "/materials")]);
const matId = Object.fromEntries(materials2.filter((m) => materialTitles.has(m.title)).map((m) => [m.title, m.id]));
const wanted = Object.fromEntries(data.pins.map((p) => [p.title, p.materialNames ?? []]));
let n = 0;
for (const p of pins2) {
  if (!(p.tags ?? []).includes(TAG) || !wanted[p.title]) continue;
  const ids = [...new Set([...(p.materialIds ?? []), ...wanted[p.title].map((t) => matId[t]).filter(Boolean)])];
  await call("PUT", `/pins/${p.id}`, { materialIds: ids });
  n++;
}
console.log(`ピンに資料を付けました: ${n} 件`);
