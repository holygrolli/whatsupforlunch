"""Prepare stage: ordered pipeline of named preparers.

Available preparers (plan sections 3.2 and 3.5):

- ``pdfseparate``: split a multi-page PDF into one PDF per page.
- ``pdftoppm``: render a PDF page to an image (``image.png`` / ``image.jpg``).
- ``pdftotext``: extract text from a PDF into ``chatgpt_user.txt``.
- ``html_to_text``: reduce an HTML page to the menu text (Le Casino HTML
  variant; the ``cleaned_*.html`` text reduction from the old scra.py).
- ``reduce_to_text``: copy an already-textual scrape result to
  ``chatgpt_user.txt`` (used for div-type spiders whose content is already
  cleaned text/HTML).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class PrepareError(Exception):
    pass


def _run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise PrepareError(
            f"command {' '.join(cmd)} failed ({result.returncode}): "
            f"{result.stderr.strip()}"
        )


def pdfseparate(run_dir: Path, filename: str, **_opts) -> list[str]:
    """Split ``filename`` into ``<stem>_separated_<n>.pdf`` pages; removes the
    original (mirrors the current workflow shell)."""
    source = run_dir / filename
    if not source.is_file():
        raise PrepareError(f"pdfseparate: {filename} not found")
    pattern = f"{source.stem}_separated_%d.pdf"
    _run(["pdfseparate", source.name, pattern], cwd=run_dir)
    source.unlink()
    pages = sorted(p.name for p in run_dir.glob(f"{source.stem}_separated_*.pdf"))
    if not pages:
        raise PrepareError(f"pdfseparate produced no pages for {filename}")
    return pages


def pdftoppm(run_dir: Path, filename: str, resolution: int = 150,
             format: str = "png", singlefile: bool = True, **_opts) -> list[str]:
    """Render a PDF to ``image.<format>`` (singlefile) like the workflows do."""
    source = run_dir / filename
    if not source.is_file():
        raise PrepareError(f"pdftoppm: {filename} not found")
    cmd = ["pdftoppm"]
    if singlefile:
        cmd.append("-singlefile")
    # A separated PDF page must not overwrite the image produced for the
    # previous page.  Preserve the historical ``image.<ext>`` name for a
    # normal single input, but derive a stable unique prefix for pages.
    output_prefix = (
        source.stem
        if re.search(r"_separated_\d+$", source.stem)
        else "image"
    )
    cmd += ["-r", str(resolution), f"-{format}", source.name, output_prefix]
    _run(cmd, cwd=run_dir)
    ext = "jpg" if format in ("jpeg", "jpg") else format
    out = run_dir / f"{output_prefix}.{ext}"
    if not out.is_file():
        raise PrepareError(f"pdftoppm produced no image for {filename}")
    return [out.name]


def pdftotext(run_dir: Path, filename: str, **_opts) -> list[str]:
    """Extract text from a PDF into ``chatgpt_user.txt``."""
    source = run_dir / filename
    if not source.is_file():
        raise PrepareError(f"pdftotext: {filename} not found")
    _run(["pdftotext", source.name, "chatgpt_user.txt"], cwd=run_dir)
    return ["chatgpt_user.txt"]


def html_to_text(run_dir: Path, filename: str, **_opts) -> list[str]:
    """Reduce an HTML menu page to its text content (Le Casino HTML variant).

    Looks for the ``Speiseplan`` heading container first, then for a block
    containing weekday names; falls back to the whole document. All non-empty
    text fragments are written one per line to ``chatgpt_user.txt`` — the same
    reduction the old ``lecasino/scra.py`` performed.
    """
    import lxml.html as lxml_html

    source = run_dir / filename
    if not source.is_file():
        raise PrepareError(f"html_to_text: {filename} not found")
    raw = source.read_text(encoding="utf-8", errors="replace")
    try:
        response_doc = lxml_html.fromstring(raw)
    except Exception as exc:
        raise PrepareError(f"html_to_text: cannot parse {filename}: {exc}") from exc

    cleaned_html = None
    headings = response_doc.xpath(
        "//h2[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'speiseplan')]"
    )
    if headings:
        heading = headings[0]
        container = heading.xpath(
            "ancestor::div[contains(@class,'group/container')][1]"
        ) or [heading.getparent()]
        if container and container[0] is not None:
            cleaned_html = lxml_html.tostring(container[0], encoding="unicode")
    if not cleaned_html:
        weekdays = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag"]
        expr = " or ".join(
            f"contains(translate(normalize-space(.), "
            f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{w}')"
            for w in weekdays
        )
        blocks = response_doc.xpath(f"//*[({expr})]")
        if blocks:
            anc = blocks[0].xpath(
                "ancestor::div[(@class) and (string-length(normalize-space(.))>0)][1]"
            )
            target = anc[0] if anc else blocks[0]
            cleaned_html = lxml_html.tostring(target, encoding="unicode")
    if not cleaned_html:
        cleaned_html = raw

    doc = lxml_html.fromstring(cleaned_html)
    for bad in doc.xpath("//script|//style"):
        bad.getparent().remove(bad)
    texts = [t.strip() for t in doc.itertext() if t and t.strip()]
    out = run_dir / "chatgpt_user.txt"
    out.write_text("\n".join(texts), encoding="utf-8")
    return [out.name]


def reduce_to_text(run_dir: Path, filename: str, **_opts) -> list[str]:
    """Copy an already-textual scrape result to ``chatgpt_user.txt``."""
    source = run_dir / filename
    if not source.is_file():
        raise PrepareError(f"reduce_to_text: {filename} not found")
    out = run_dir / "chatgpt_user.txt"
    out.write_text(source.read_text(encoding="utf-8", errors="replace"),
                   encoding="utf-8")
    return [out.name]


PREPARERS = {
    "pdfseparate": pdfseparate,
    "pdftoppm": pdftoppm,
    "pdftotext": pdftotext,
    "html_to_text": html_to_text,
    "reduce_to_text": reduce_to_text,
}


def prepare_one(run_dir: str | Path, filename: str, steps: list[dict]) -> list[str]:
    """Run the ordered prepare pipeline for one downloaded file.

    Returns the list of files produced. A step that yields multiple files
    (``pdfseparate``) applies the remaining steps to each produced file.
    """
    run_dir = Path(run_dir)
    current = [filename]
    for step in steps or []:
        name, opts = next(iter(step.items()))
        fn = PREPARERS.get(name)
        if fn is None:
            raise PrepareError(f"unknown preparer {name!r}")
        produced: list[str] = []
        for item in current:
            produced.extend(fn(run_dir, item, **(opts or {})))
        current = produced
    return current
