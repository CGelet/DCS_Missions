"""Render kneeboard pages (768x1024 PNG) with headless Chromium."""
from __future__ import annotations

from pathlib import Path

from .build_html import env, view_model

PAGES = ["mission", "nav", "threats"]
SIZE = {"width": 768, "height": 1024}


def build(data: dict, out_dir: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    vm = view_model(data)
    tpl = env().get_template("kneeboard.html.j2")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=SIZE)
        for i, name in enumerate(PAGES, 1):
            page.set_content(tpl.render(**vm, page=name, page_no=i, page_count=len(PAGES)))
            path = out_dir / f"{i:02d}_{name}.png"
            page.screenshot(path=str(path), clip={"x": 0, "y": 0, **SIZE})
            paths.append(path)
        browser.close()
    return paths
