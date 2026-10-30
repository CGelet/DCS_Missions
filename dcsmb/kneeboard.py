"""Render kneeboard pages (768x1024 PNG) with headless Chromium."""
from __future__ import annotations

from pathlib import Path

from .build_html import env, view_model

PAGES = ["mission", "lineup", "nav", "comms", "threats"]
SIZE = {"width": 768, "height": 1024}
# Long pages (wordy situations, many waypoints) used to run off the bottom of the kneeboard.
# Zoom the whole page out in small steps until it fits, keeping the 768x1024 output size.
FIT_JS = """() => {
  const body = document.body, page = document.querySelector('.page');
  let z = 1;
  while (page.scrollHeight > page.clientHeight + 1 && z > 0.6) {
    z = Math.round((z - 0.02) * 100) / 100;
    body.style.width = (768 / z) + 'px'; body.style.height = (1024 / z) + 'px'; body.style.zoom = z;
  }
  return z;
}"""


def build(data: dict, out_dir: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    vm = view_model(data)
    pages = ["mission", "lineup", "nav", "comms", "rules"] if vm["is_training"] else PAGES
    tpl = env().get_template("kneeboard.html.j2")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):  # page names and numbers change when pages are added
        old.unlink()
    paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=SIZE)
        for i, name in enumerate(pages, 1):
            page.set_content(tpl.render(**vm, page=name, page_no=i, page_count=len(pages)))
            if page.evaluate(FIT_JS) <= 0.6:
                print(f"warning: kneeboard page '{name}' still doesn't fit at 60% zoom; shorten its text")
            path = out_dir / f"{i:02d}_{name}.png"
            page.screenshot(path=str(path), clip={"x": 0, "y": 0, **SIZE})
            paths.append(path)
        browser.close()
    return paths
