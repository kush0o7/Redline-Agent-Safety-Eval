"""Build docs/demo.gif and docs/social-preview.png from real `redline compare fake-safe fake-degraded` output.

No screen recorder needed: this runs the real CLI (offline, simulated models), then draws the
terminal frames with Pillow. macOS fonts are used when present (Menlo + Apple Color Emoji).

    python3 scripts/make_visuals.py           # writes docs/demo.gif and docs/social-preview.png

For a true screen recording instead, see docs/demo.tape (vhs).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MONO = ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/SFNSMono.ttf", "DejaVuSansMono.ttf"]
EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"
BG, FG, DIM, RED, GREEN, YEL, CYAN = "#0d1117", "#e6edf3", "#8b949e", "#ff7b72", "#3fb950", "#d29922", "#79c0ff"
COMMAND = "redline compare fake-safe fake-degraded"


def _font(size: int) -> ImageFont.FreeTypeFont:
    for f in MONO:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _emoji(ch: str, px: int) -> Image.Image | None:
    try:
        f = ImageFont.truetype(EMOJI, 160)
    except OSError:
        return None
    im = Image.new("RGBA", (180, 180))
    ImageDraw.Draw(im).text((0, 0), ch, font=f, embedded_color=True)
    return im.crop(im.getbbox()).resize((px, px), Image.LANCZOS)


def run_cli() -> list[str]:
    out = Path(tempfile.mkdtemp(prefix="redline-gif-"))
    env = dict(os.environ, COLUMNS="100")
    res = subprocess.run([sys.executable, "-m", "redline.cli", "compare", "fake-safe", "fake-degraded", "--out", str(out)],
                         capture_output=True, text=True, env=env, cwd=ROOT / "backend")
    if res.returncode not in (0, 1):
        sys.exit(res.stderr)
    return res.stdout.replace(str(out), "./redline-out").splitlines()


def colour(line: str) -> str:
    s = line.strip()
    if s.startswith(("❌", "✗")) or "Don't ship" in s:
        return RED
    if s.startswith("✅"):
        return GREEN
    if s.startswith(("·", "(", "Grader", "Cases")) or s.startswith("──"):
        return DIM
    if s.startswith(("Biggest risks", "By area", "Tests that broke", "What to do")):
        return YEL
    if s.startswith("Redline compare"):
        return CYAN
    return FG


class Term:
    def __init__(self, cols=100, rows=31, size=15):
        self.font = _font(size)
        self.cw = int(self.font.getlength("M"))
        self.lh = int(size * 1.45)
        self.cols, self.rows = cols, rows
        self.pad, self.bar = 18, 34
        self.w = self.cw * cols + self.pad * 2
        self.h = self.lh * rows + self.pad * 2 + self.bar
        self.emoji = {c: _emoji(c, int(size * 1.15)) for c in ("❌", "✅")}

    def frame(self, lines: list[tuple[str, str]], cursor: bool = False) -> Image.Image:
        im = Image.new("RGB", (self.w, self.h), BG)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, self.w, self.bar], fill="#161b22")
        for i, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
            d.ellipse([14 + i * 22, 11, 26 + i * 22, 23], fill=c)
        d.text((self.w // 2 - 40, 9), "terminal", font=self.font, fill=DIM)
        shown = lines[-self.rows:]
        for i, (text, col) in enumerate(shown):
            y = self.bar + self.pad + i * self.lh
            x = self.pad
            for ch in text[: self.cols]:
                e = self.emoji.get(ch)
                if e is not None:
                    im.paste(e, (x, y), e)
                    x += self.cw * 2
                    continue
                d.text((x, y), ch, font=self.font, fill=col)
                x += self.cw
            if cursor and i == len(shown) - 1:
                d.rectangle([x + 2, y + 2, x + self.cw, y + self.lh - 4], fill=FG)
        return im


CONT = "\x00"  # marks a wrapped continuation line (takes the colour of the line above)


def soft_wrap(lines: list[str], cols: int) -> list[str]:
    """Wrap long lines the way a terminal would, keeping the indent (emoji count as 2 columns)."""
    out = []
    for ln in lines:
        width = cols - (1 if ln[:1] in ("❌", "✅") else 0)
        if len(ln) <= width:
            out.append(ln)
            continue
        lead = len(ln) - len(ln.lstrip(" "))
        indent = " " * (lead + 3)
        cur, first = " " * lead, True
        for w in ln.lstrip(" ").split(" "):
            if cur.strip() and len(cur) + 1 + len(w) > width:
                out.append(cur if first else CONT + cur)
                cur, first = indent + w, False
            else:
                cur = f"{cur} {w}" if cur.strip() else cur + w
        out.append(cur if first else CONT + cur)
    return out


def build_gif(lines: list[str], path: Path) -> float:
    t = Term()
    lines = soft_wrap(lines, t.cols)
    frames, durs = [], []
    prompt = "$ "

    def add(buf, ms, cursor=False):
        frames.append(t.frame(buf, cursor))
        durs.append(ms)

    buf: list[tuple[str, str]] = []
    add(buf + [(prompt, GREEN)], 600, True)
    for i in range(0, len(COMMAND) + 1, 2):
        add([(prompt + COMMAND[:i], FG)], 55, True)
    add([(prompt + COMMAND, FG)], 400, True)
    buf = [(prompt + COMMAND, FG)]
    # Header lines (up to the blank line before the result), then a quick progress tick.
    head_end = next(i for i, ln in enumerate(lines) if ln.startswith("❌") or ln.startswith("✅"))
    for ln in lines[:head_end]:
        buf.append((ln.lstrip(CONT), colour(ln)))
        add(buf, 220)
    # Result block up to and including the By area table, then the first broken test.
    stop = next((i for i, ln in enumerate(lines) if ln.strip().startswith("Tests that broke")), len(lines))
    body = lines[head_end:stop + 7]
    col = FG
    for j, ln in enumerate(body):
        col = col if ln.startswith(CONT) else colour(ln)
        buf.append((ln.lstrip(CONT), col))
        add(buf, 1800 if j == 0 else 120)
    add(buf, 7000)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durs, loop=0, optimize=True)
    return sum(durs) / 1000


def _wrap(text: str, font, width: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if font.getlength(nxt) <= width:
            cur = nxt
        else:
            out.append(cur)
            cur = w
    return out + [cur]


def build_social(lines: list[str], path: Path) -> None:
    W, H = 1280, 640
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    try:
        bold = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 58)
        sub = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
    except OSError:
        bold, sub = _font(52), _font(28)
    mono = _font(24)
    d.text((70, 60), "Redline", font=sub, fill=RED)
    y = 110
    for ln in _wrap("Did your fine-tune just get less safe? Find out in one command.", bold, W - 140):
        d.text((70, y), ln, font=bold, fill=FG)
        y += 70
    # terminal card
    y += 30
    d.rounded_rectangle([60, y, W - 60, H - 60], radius=18, fill="#161b22", outline="#30363d", width=2)
    d.text((95, y + 28), "$ " + COMMAND, font=mono, fill=DIM)
    head = next(ln for ln in lines if ln.startswith(("❌", "✅")))
    e = _emoji(head[0], 30)
    ty = y + 78
    x = 95
    if e is not None:
        im.paste(e, (x, ty), e)
        x += 44
    text = head[1:].strip()
    first, _, rest = text.partition(". ")
    d.text((x, ty - 2), first + ".", font=ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 32)
           if Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf").exists() else mono, fill=RED)
    for i, ln in enumerate(_wrap(rest, sub, W - 220)[:3]):
        d.text((95, ty + 50 + i * 40), ln, font=sub, fill=FG)
    d.text((95, H - 105), "pip install redline-evals   ·   github.com/kush0o7/Redline-Agent-Safety-Eval", font=_font(20), fill=DIM)
    im.save(path, optimize=True)


def main() -> None:
    lines = run_cli()
    secs = build_gif(lines, ROOT / "docs" / "demo.gif")
    build_social(lines, ROOT / "docs" / "social-preview.png")
    print(f"docs/demo.gif ({secs:.1f} s, {(ROOT / 'docs' / 'demo.gif').stat().st_size // 1024} KB)")
    print("docs/social-preview.png (1280x640)")


if __name__ == "__main__":
    main()
