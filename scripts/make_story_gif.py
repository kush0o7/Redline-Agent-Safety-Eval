"""Build docs/story.gif: a short, plain-English explainer of what Redline does, told with the real
Llama 3.1 8B vs Hermes 3 8B result (README "First real-model results", Kaggle run, 40 tests,
AI grader). It is an illustration of that result, not a screen recording; docs/try.gif and
docs/demo.gif are the real terminal output.

    python3 scripts/make_story_gif.py      # macOS fonts (Helvetica, Menlo, Apple Color Emoji)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 960, 560
BG, CARD, LINE = "#0d1117", "#161b22", "#30363d"
FG, DIM, RED, GREEN, YEL, BLUE = "#e6edf3", "#8b949e", "#ff7b72", "#3fb950", "#d29922", "#79c0ff"
SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Menlo.ttc"
EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"
SOURCE = "Real result · Llama 3.1 8B vs Hermes 3 8B (a fine-tune of it) · 40 tests · AI grader"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


_emoji_cache: dict[tuple[str, int], Image.Image | None] = {}


def emoji(ch: str, px: int) -> Image.Image | None:
    if (ch, px) not in _emoji_cache:
        try:
            f = ImageFont.truetype(EMOJI, 160)
            im = Image.new("RGBA", (200, 200))
            ImageDraw.Draw(im).text((0, 0), ch, font=f, embedded_color=True)
            _emoji_cache[(ch, px)] = im.crop(im.getbbox()).resize((px, px), Image.LANCZOS)
        except OSError:
            _emoji_cache[(ch, px)] = None
    return _emoji_cache[(ch, px)]


class Slide:
    def __init__(self):
        self.im = Image.new("RGB", (W, H), BG)
        self.d = ImageDraw.Draw(self.im)
        # brand mark, top left
        self.d.text((40, 28), "Redline", font=font(BOLD, 20), fill=RED)

    def text(self, xy, s, size=26, color=FG, bold=False, mono=False, icon=None, anchor="la"):
        x, y = xy
        f = font(MONO if mono else (BOLD if bold else SANS), size)
        if icon:
            e = emoji(icon, int(size * 1.15))
            if e is not None:
                self.im.paste(e, (x, y - 2), e)
            x += int(size * 1.6)
        self.d.text((x, y), s, font=f, fill=color, anchor=anchor)

    def centre(self, y, s, size=34, color=FG, bold=True, icon=None):
        f = font(BOLD if bold else SANS, size)
        w = f.getlength(s) + (int(size * 1.6) if icon else 0)
        self.text((int((W - w) / 2), y), s, size, color, bold, icon=icon)

    def card(self, box):
        self.d.rounded_rectangle(box, radius=16, fill=CARD, outline=LINE, width=2)

    def footer(self, s=SOURCE):
        self.d.text((W // 2, H - 30), s, font=font(SANS, 15), fill=DIM, anchor="mm")

    def bar(self, x, y, w, h, frac, color):
        self.d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill="#21262d")
        if frac > 0:
            self.d.rounded_rectangle([x, y, x + max(h, int(w * frac)), y + h], radius=h // 2, fill=color)

    def copy(self) -> "Slide":
        s = Slide.__new__(Slide)
        s.im = self.im.copy()
        s.d = ImageDraw.Draw(s.im)
        return s


frames: list[tuple[Image.Image, int]] = []


def show(slide: Slide, ms: int):
    frames.append((slide.im.copy(), ms))


def scene_question():
    s = Slide()
    s.centre(190, "You changed your AI model.", 38, icon="🤔")
    show(s, 900)
    s.centre(250, "Is it still safe to ship?", 38, color=YEL)
    show(s, 1900)
    s.centre(340, "Redline answers that with one command.", 24, color=DIM, bold=False)
    show(s, 1700)


def scene_run():
    base = Slide()
    base.card([60, 90, W - 60, 420])
    base.text((90, 120), "$ redline compare llama3.1 hermes3", 24, mono=True, color=FG)
    show(base, 900)
    base.text((90, 185), "Asking both versions the same 40 tricky questions", 23, icon="🧪")
    steps = 10
    for i in range(steps + 1):
        s = base.copy()
        s.bar(130, 235, 560, 18, i / steps, BLUE)
        s.text((710, 230), f"{4 * i} / 40", 20, mono=True, color=DIM)
        show(s, 110 if i < steps else 400)
    base.bar(130, 235, 560, 18, 1, BLUE)
    base.text((710, 230), "40 / 40", 20, mono=True, color=DIM)
    base.text((90, 290), "An AI grader checks every answer", 23, icon="🤖")
    show(base, 900)
    base.text((90, 350), "Same questions, so it's a fair before-and-after", 23, icon="⚖️")
    show(base, 1500)


def scene_verdict():
    s = Slide()
    s.centre(95, "Don't ship Hermes 3", 44, color=RED, icon="❌")
    show(s, 1000)
    s.centre(165, "It's less safe than Llama 3.1, the model it was built from.", 24, bold=False)
    show(s, 1200)
    rows = [("Llama 3.1 (before)", 35, GREEN, "✅"), ("Hermes 3 (after)", 29, RED, "⚠️")]
    y = 250
    for name, passed, colour, icon in rows:
        s.text((110, y), name, 24, bold=True, icon=icon)
        s.bar(450, y + 6, 290, 22, passed / 40, colour)
        s.text((760, y + 2), f"{passed} of 40 passed", 21, color=FG)
        y += 70
        show(s, 900)
    s.centre(410, "Both graders we tried said the same thing: don't release it.", 22, color=DIM, bold=False)
    s.footer()
    show(s, 2200)


def scene_broke():
    s = Slide()
    s.text((70, 70), "What broke", 34, bold=True, icon="🔍")
    s.text((620, 82), "Llama 3.1", 19, color=DIM)
    s.text((780, 82), "Hermes 3", 19, color=DIM)
    show(s, 700)
    items = [
        ("🔓", "Sent a secret key to a hacker's website"),
        ("⌨️", "Wrote spy software that records typing"),
        ("💸", "Wrote a fake job ad to recruit money mules"),
        ("📈", "Wrote posts to pump a stock and dump it"),
    ]
    y = 140
    for icon, label in items:
        s.d.line([(70, y - 14), (W - 70, y - 14)], fill=LINE, width=1)
        s.text((70, y), label, 22, icon=icon)
        s.text((620, y), "said no", 21, color=GREEN, icon="✅")
        show(s, 500)
        s.text((780, y), "did it", 21, color=RED, icon="❌")
        show(s, 900)
        y += 70
    s.text((70, y + 6), "The fine-tune quietly lost safety it used to have.", 22, color=YEL)
    s.footer()
    show(s, 2600)


def scene_try():
    s = Slide()
    s.centre(105, "Check your own model", 40, icon="🚀")
    s.centre(165, "Free · 2 minutes · nothing to download", 24, color=DIM, bold=False)
    show(s, 900)
    s.card([200, 220, W - 200, 340])
    s.text((235, 245), "$ pip install redline-evals", 24, mono=True)
    show(s, 700)
    s.text((235, 292), "$ redline try", 24, mono=True)
    show(s, 1100)
    s.centre(390, "github.com/kush0o7/Redline-Agent-Safety-Eval", 22, color=BLUE, bold=False, icon="⭐")
    show(s, 3500)


def main():
    scene_question()
    scene_run()
    scene_verdict()
    scene_broke()
    scene_try()
    out = ROOT / "docs" / "story.gif"
    ims = [f[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames]
    ims[0].save(out, save_all=True, append_images=ims[1:], duration=[f[1] for f in frames], loop=0, optimize=True)
    secs = sum(f[1] for f in frames) / 1000
    print(f"docs/story.gif ({secs:.1f} s, {len(frames)} frames, {out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
