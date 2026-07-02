"""
build_golden_set.py — подготовка golden set для eval_tagging.py
================================================================
1. Стратифицированная выборка 100 луков (равномерно по брендам, seed=42).
2. Предзаполнение тегами из существующего enriched_looks*.csv (черновик —
   его нужно ПРОВЕРИТЬ и исправить руками, это и есть смысл golden set).
3. Генерация output/annotate.html — локальный разметчик: открой в браузере,
   проверь каждый лук, исправь теги, нажми «Экспорт» → golden_set.json,
   положи его в output/.

Запуск:
    python3 build_golden_set.py            # 100 луков
    python3 build_golden_set.py --n 20     # быстрая проба
"""

import argparse
import csv
import json
import os
import random
from collections import defaultdict

import taxonomy as tx

DRAFT_PATH = "output/golden_set_draft.json"
HTML_PATH = "output/annotate.html"


def sample_looks(input_csv, n, seed=42):
    by_designer = defaultdict(list)
    with open(input_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("image_url"):
                by_designer[r["designer"]].append(r)
    rng = random.Random(seed)
    designers = sorted(by_designer)
    picked, i = [], 0
    while len(picked) < n and any(by_designer.values()):
        d = designers[i % len(designers)]
        if by_designer[d]:
            picked.append(by_designer[d].pop(
                rng.randrange(len(by_designer[d]))))
        i += 1
    return picked[:n]


def prefill(looks):
    """Черновые теги из уже обогащённых CSV (v3 приоритетнее v2)."""
    enriched = {}
    for path in ("output/enriched_looks.csv", "output/enriched_looks_v3.csv"):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    enriched[r["image_url"]] = r

    out = []
    for row in looks:
        e = enriched.get(row["image_url"])
        items, styles = [], []
        if e:
            styles = [s for s in e["style_tags"].split(",") if s]
            for it in json.loads(e["items_json"]):
                items.append({
                    "category": it.get("category", "Other"),
                    "materials": it.get("materials", []),
                    "pattern": it.get("pattern", tx.NOT_VISIBLE),
                    "silhouette": it.get("silhouette", []),
                    "construction": it.get("construction", []),
                    "decoration": it.get("decoration", []),
                })
        out.append({
            "image_url": row["image_url"],
            "designer": row["designer"],
            "show": row["show"],
            "look_number": row["look_number"],
            "styles": styles,
            "items": items,
            "verified": False,
        })
    return out


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>Golden Set Annotator</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;display:flex;height:100vh}
 #left{width:44%;background:#111;display:flex;align-items:center;
   justify-content:center}
 #left img{max-width:100%;max-height:100vh;object-fit:contain}
 #right{width:56%;overflow-y:auto;padding:16px 20px;box-sizing:border-box}
 h3{margin:4px 0 10px}
 .nav{display:flex;gap:8px;align-items:center;margin-bottom:10px;
   position:sticky;top:0;background:#fff;padding:6px 0;z-index:5}
 button{padding:6px 12px;cursor:pointer;border:1px solid #999;
   border-radius:6px;background:#f5f5f5}
 button.primary{background:#1a73e8;color:#fff;border-color:#1a73e8}
 .item{border:1px solid #ddd;border-radius:8px;padding:10px;margin:10px 0}
 .field{margin:6px 0}
 label.fname{font-weight:600;font-size:12px;display:block;margin-bottom:2px}
 select{max-width:100%;font-size:13px}
 select[multiple]{width:100%;height:96px}
 .chips{display:flex;flex-wrap:wrap;gap:4px}
 .chips label{font-size:12px;border:1px solid #ccc;border-radius:12px;
   padding:2px 8px;cursor:pointer;user-select:none}
 .chips input{vertical-align:middle;margin:0 3px 0 0}
 .chips input:checked+span{font-weight:700}
 .chips label:has(input:checked){background:#dbeafe;border-color:#1a73e8}
 .verified{color:#0a7d28;font-weight:700}
 .progress{font-size:13px;color:#555}
 details{margin:8px 0}
</style></head><body>
<div id="left"><img id="photo" src=""></div>
<div id="right">
 <div class="nav">
  <button onclick="nav(-1)">← Пред</button>
  <button onclick="nav(1)">След →</button>
  <span id="counter"></span>
  <button onclick="markVerified()" class="primary" id="vbtn">✓ Проверен</button>
  <button onclick="exportJson()">💾 Экспорт golden_set.json</button>
 </div>
 <div class="progress" id="progress"></div>
 <h3 id="title"></h3>
 <details open><summary><b>Стили лука (0–3)</b></summary>
   <div class="chips" id="styles"></div></details>
 <div id="items"></div>
 <button onclick="addItem()">+ Добавить предмет</button>
</div>
<script>
const TX = __TAXONOMY__;
const RU = __RU__;
let DATA = __DATA__;
let cur = 0;

// автосохранение в localStorage
const LSKEY = 'golden_set_progress';
try { const saved = localStorage.getItem(LSKEY);
  if (saved) { const p = JSON.parse(saved);
    if (p.length === DATA.length) DATA = p; } } catch(e){}
function save(){ try{ localStorage.setItem(LSKEY, JSON.stringify(DATA)); }
  catch(e){} }

function ruName(dim, v){ return (RU[dim] && RU[dim][v]) ? RU[dim][v] : v; }

function chips(containerId, dim, values, selected, onchange){
  const el = document.getElementById(containerId);
  el.innerHTML = '';
  values.forEach(v => {
    const l = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.checked = selected.includes(v);
    cb.onchange = () => onchange(v, cb.checked);
    const s = document.createElement('span');
    s.textContent = ruName(dim, v);
    l.appendChild(cb); l.appendChild(s); el.appendChild(l);
  });
}

function multiSelect(dim, values, selected, onchange, withNV){
  const sel = document.createElement('select');
  sel.multiple = true;
  const vals = withNV ? values.concat(['not_visible']) : values;
  vals.forEach(v => {
    const o = document.createElement('option');
    o.value = v; o.textContent = ruName(dim, v) ;
    if (v === 'not_visible') o.textContent = 'не видно';
    o.selected = selected.includes(v);
    sel.appendChild(o);
  });
  sel.onchange = () => onchange([...sel.selectedOptions].map(o => o.value));
  return sel;
}

function singleSelect(dim, values, selected, onchange, withNV){
  const sel = document.createElement('select');
  const vals = withNV ? values.concat(['not_visible']) : values;
  vals.forEach(v => {
    const o = document.createElement('option');
    o.value = v; o.textContent = v==='not_visible'?'не видно':ruName(dim,v);
    o.selected = (v === selected);
    sel.appendChild(o);
  });
  sel.onchange = () => onchange(sel.value);
  return sel;
}

function field(name, node){
  const d = document.createElement('div'); d.className = 'field';
  const l = document.createElement('label'); l.className = 'fname';
  l.textContent = name; d.appendChild(l); d.appendChild(node);
  return d;
}

function renderItems(){
  const box = document.getElementById('items');
  box.innerHTML = '';
  const look = DATA[cur];
  look.items.forEach((it, idx) => {
    const div = document.createElement('div'); div.className = 'item';
    const head = document.createElement('div');
    head.innerHTML = '<b>Предмет ' + (idx+1) + '</b> ';
    const del = document.createElement('button');
    del.textContent = '✕'; del.style.float = 'right';
    del.onclick = () => { look.items.splice(idx,1); save(); renderItems(); };
    head.appendChild(del); div.appendChild(head);
    div.appendChild(field('Категория', singleSelect('category',
      TX.category, it.category, v => { it.category = v; save(); })));
    div.appendChild(field('Принт', singleSelect('pattern',
      TX.pattern, it.pattern, v => { it.pattern = v; save(); }, true)));
    div.appendChild(field('Материалы (Ctrl+клик)', multiSelect('materials',
      TX.materials, it.materials, v => { it.materials = v; save(); }, true)));
    div.appendChild(field('Силуэт', multiSelect('silhouette',
      TX.silhouette, it.silhouette, v => { it.silhouette = v; save(); })));
    div.appendChild(field('Крой/конструкция', multiSelect('construction',
      TX.construction, it.construction,
      v => { it.construction = v; save(); })));
    div.appendChild(field('Отделка', multiSelect('decoration',
      TX.decoration, it.decoration, v => { it.decoration = v; save(); })));
    box.appendChild(div);
  });
}

function render(){
  const look = DATA[cur];
  document.getElementById('photo').src = look.image_url;
  document.getElementById('counter').textContent =
    (cur+1) + ' / ' + DATA.length;
  document.getElementById('title').innerHTML = look.designer + ' — ' +
    look.show + ' — Look ' + look.look_number +
    (look.verified ? ' <span class="verified">✓ проверен</span>' : '');
  const done = DATA.filter(l => l.verified).length;
  document.getElementById('progress').textContent =
    'Проверено: ' + done + ' из ' + DATA.length;
  chips('styles', 'styles', TX.styles, look.styles, (v, on) => {
    if (on) { if (!look.styles.includes(v)) look.styles.push(v); }
    else look.styles = look.styles.filter(x => x !== v);
    save(); });
  renderItems();
}

function nav(d){ cur = Math.min(Math.max(cur + d, 0), DATA.length - 1);
  render(); window.scrollTo(0,0); }
function addItem(){ DATA[cur].items.push({category:'Other',
  materials:[], pattern:'not_visible', silhouette:[], construction:[],
  decoration:[]}); save(); renderItems(); }
function markVerified(){ DATA[cur].verified = true; save();
  if (cur < DATA.length - 1) nav(1); else render(); }

function exportJson(){
  const unv = DATA.filter(l => !l.verified).length;
  if (unv > 0 && !confirm(unv +
    ' луков не отмечены проверенными. Всё равно экспортировать?')) return;
  const out = DATA.map(({verified, ...rest}) => rest);
  const blob = new Blob([JSON.stringify(out, null, 1)],
    {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'golden_set.json'; a.click();
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'SELECT') return;
  if (e.key === 'ArrowLeft') nav(-1);
  if (e.key === 'ArrowRight') nav(1);
  if (e.key === 'v') markVerified();
});
render();
</script></body></html>"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--input", default="output/all_designers.csv")
    args = p.parse_args()

    looks = sample_looks(args.input, args.n)
    draft = prefill(looks)
    with open(DRAFT_PATH, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=1)

    tx_json = {
        "styles": tx.STYLES, "category": tx.CATEGORIES,
        "materials": tx.MATERIALS, "pattern": tx.PATTERNS,
        "silhouette": tx.SILHOUETTES, "construction": tx.CONSTRUCTION,
        "decoration": tx.DECORATION,
    }
    ru_json = {
        "styles": tx.RU_STYLES, "category": tx.RU_CATEGORIES,
        "materials": tx.RU_MATERIALS, "pattern": tx.RU_PATTERNS,
        "silhouette": tx.RU_SILHOUETTES, "construction": tx.RU_CONSTRUCTION,
        "decoration": tx.RU_DECORATION,
    }
    html = (HTML_TEMPLATE
            .replace("__TAXONOMY__", json.dumps(tx_json, ensure_ascii=False))
            .replace("__RU__", json.dumps(ru_json, ensure_ascii=False))
            .replace("__DATA__", json.dumps(draft, ensure_ascii=False)))
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    prefilled = sum(1 for d in draft if d["items"])
    print(f"✅ Выборка: {len(draft)} луков "
          f"({len({d['designer'] for d in draft})} брендов), "
          f"предзаполнено из старой разметки: {prefilled}")
    print(f"   Черновик: {DRAFT_PATH}")
    print(f"   Разметчик: открой {HTML_PATH} в браузере, проверь каждый лук,")
    print(f"   нажми «Экспорт» и сохрани golden_set.json в output/")


if __name__ == "__main__":
    main()
