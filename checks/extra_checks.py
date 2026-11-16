"""Доп. проверки: работа при недоступном localStorage и встроенный самотест v2."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BLOCK = "Object.defineProperty(window,'localStorage',{get(){throw new DOMException('blocked','SecurityError')}})"
res = {}
with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    for ver, path, box, notice in (("v1-fixed", "v1/tracker-v1-fixed.html", "#list li input[type=checkbox]", None),
                                   ("v2", "v2/tracker-v2.html", "#task-list li input[type=checkbox]", "#storage-notice")):
        ctx = br.new_context(); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script(BLOCK)
        pg.goto(Path(path).resolve().as_uri())
        n = pg.locator(box).count()
        if n: pg.locator(box).nth(1).click()
        r = {"tasks_shown": n, "js_errors": errs, "body_has_75": "75%" in pg.inner_text("body")}
        if notice: r["notice"] = pg.inner_text(notice) if pg.is_visible(notice) else "(скрыто)"
        res[ver + "_storage_blocked"] = r
        ctx.close()
    ctx = br.new_context(); pg = ctx.new_page()
    pg.goto(Path("v2/tracker-v2.html").resolve().as_uri())
    res["v2_selfTest"] = pg.evaluate("typeof __tracker!=='undefined' && __tracker.selfTest ? __tracker.selfTest() : 'нет функции'")
    br.close()
print(json.dumps(res, ensure_ascii=False, indent=1))
