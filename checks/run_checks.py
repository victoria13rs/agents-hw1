"""Проверки T1-T5 из ДЗ 1 в настоящем Chrome (Playwright, headless).

Запуск: python run_checks.py v1|v2 путь/к/tracker.html [папка_для_скриншотов]
Каждая проверка идет в новом контексте браузера: чистый localStorage = исходный пример.
Селекторы отличаются у двух версий, поэтому для каждой описан свой адаптер.
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

VERSION, HTML = sys.argv[1], Path(sys.argv[2]).resolve()
SHOTS = Path(sys.argv[3]) if len(sys.argv) > 3 else HTML.parent
URL = HTML.as_uri()


def num(text):
    m = re.search(r"-?\d+(?:[.,]\d+)?", text or "")
    return float(m.group(0).replace(",", ".")) if m else None


class V1:
    title, hours, submit = "#title", "#hours", "#addForm button[type=submit]"
    rows = "#list li:not(.empty)"
    error = "#error"

    def filter(self, pg, name):
        pg.click(f'[data-filter="{name}"]')

    def stats(self, pg):
        note = pg.inner_text("#progressNote")
        return {"total": num(pg.inner_text("#statTotal")), "done": num(pg.inner_text("#statDone")),
                "percent": num(re.search(r"Выполнено\s+(\d+)%", note).group(1)) if "%" in note else None}

    def row(self, pg, title):
        return pg.locator(self.rows).filter(has_text=title)

    def toggle(self, pg, title):
        self.row(pg, title).locator("input[type=checkbox]").click()

    def delete(self, pg, title):
        self.row(pg, title).locator("button.del").click()

    def titles(self, pg):
        return [t.strip() for t in pg.locator(f"{self.rows} .task-title").all_inner_texts()]

    def error_text(self, pg):
        return pg.inner_text(self.error).strip()


class V2(V1):
    title, hours, submit = "#title-input", "#hours-input", "#add-form button[type=submit]"
    rows = "#task-list li"

    def filter(self, pg, name):
        pg.check(f'input[name=filter][value="{name}"]')

    def stats(self, pg):
        return {"total": num(pg.inner_text("#total-hours")), "done": num(pg.inner_text("#done-hours")),
                "percent": num(pg.inner_text("#progress-text"))}

    def delete(self, pg, title):
        self.row(pg, title).locator('button[data-action="remove"]').click()

    def error_text(self, pg):
        # Ошибки стоят под своими полями; помечаем, у какого поля ошибка
        parts = []
        for field, sel in (("название", "#title-error"), ("часы", "#hours-error")):
            if pg.is_visible(sel) and pg.inner_text(sel).strip():
                parts.append(f"[{field}] {pg.inner_text(sel).strip()}")
        return " ".join(parts)


ADAPTER = {"v1": V1, "v2": V2}[VERSION]()


def bad_text(pg):
    body = pg.inner_text("body")
    return [w for w in ("NaN", "Infinity", "undefined") if w in body]


def try_add(a, pg, title, hours):
    before = len(a.titles(pg))
    pg.fill(a.title, title)
    pg.fill(a.hours, hours)
    pg.click(a.submit)
    after = len(a.titles(pg))
    return {"title": title, "hours": hours, "added": after > before, "error": a.error_text(pg),
            "kept_title": pg.input_value(a.title), "kept_hours": pg.input_value(a.hours)}


def main():
    a, out = ADAPTER, {}
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)

        def fresh(width=1100):
            ctx = br.new_context(viewport={"width": width, "height": 900})
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("dialog", lambda d: d.accept())
            pg.goto(URL)
            return ctx, pg, errors

        # T1 · исходный пример
        ctx, pg, js = fresh()
        out["T1"] = {"titles": a.titles(pg), **a.stats(pg), "js_errors": js}
        pg.screenshot(path=str(SHOTS / f"{VERSION}-desktop.png"), full_page=True)
        ctx.close()

        # T2 · статус: «Практика» готова, затем данные переживают перезагрузку
        ctx, pg, js = fresh()
        a.toggle(pg, "Практика")
        t2 = a.stats(pg)
        pg.reload()
        out["T2"] = {**t2, "after_reload": a.stats(pg), "js_errors": js}
        ctx.close()

        # T3 · фильтр «активные» не меняет базу расчета
        ctx, pg, js = fresh()
        a.filter(pg, "active")
        out["T3"] = {"titles": a.titles(pg), **a.stats(pg), "js_errors": js}
        a.filter(pg, "all")
        out["T3"]["titles_after_all"] = a.titles(pg)
        ctx.close()

        # T4 · ошибки ввода и границы
        cases = [("", "2"), ("   ", "2"), ("Тест", ""), ("Тест", "-1"),
                 ("Тест", "0"), ("Тест", "0.3"), ("Тест", "1.3"), ("Тест", "24.5"),
                 ("Тест 0,5", "0.5"), ("Тест 24", "24")]
        out["T4"] = []
        for title, hours in cases:
            ctx, pg, js = fresh()
            r = try_add(a, pg, title, hours)
            r["js_errors"] = js
            out["T4"].append(r)
            if (title, hours) == ("Тест", ""):
                pg.screenshot(path=str(SHOTS / f"{VERSION}-error.png"))
            ctx.close()

        # T5 · пустое состояние
        ctx, pg, js = fresh()
        for t in list(a.titles(pg)):
            a.delete(pg, t)
        t5 = {"titles": a.titles(pg), **a.stats(pg), "bad_text": bad_text(pg)}
        r = try_add(a, pg, "После очистки", "1")
        t5["add_after_empty"] = r["added"]
        t5["stats_after_add"] = a.stats(pg)
        t5["js_errors"] = js
        out["T5"] = t5
        ctx.close()

        # Узкий экран 390 px, с длинным названием
        ctx, pg, js = fresh(390)
        try_add(a, pg, "Очень-длинное-название-задачи-без-пробелов-для-проверки-переноса-строки", "1")
        out["W390"] = pg.evaluate("({scrollWidth: document.documentElement.scrollWidth,"
                                  " clientWidth: document.documentElement.clientWidth})")
        pg.screenshot(path=str(SHOTS / f"{VERSION}-390px.png"), full_page=True)
        ctx.close()

        # Внешние ресурсы
        html = HTML.read_text(encoding="utf-8")
        out["external"] = re.findall(r'(?:src|href)\s*=\s*["\'](https?:[^"\']+)', html)
        br.close()

    print(json.dumps(out, ensure_ascii=False, indent=1))


main()
