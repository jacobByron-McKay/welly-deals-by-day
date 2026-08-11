"""
Burn a photo credit into the bottom-right corner of a burger image.

Why in the image rather than in the page: Two Grey's permission is conditional on being credited as
the owner of the photo ("just credit Two Grey as the owner of this image please"). The leaderboard
reuses the same <img> in a row thumbnail, an expanded card and a static page, so a caption in one
place would not travel with the picture. Burning it in means the credit is present everywhere the
photo appears, including if someone saves or shares it.

Usage:
    python tools/add_photo_credit.py <in> <out> "Photo: Two Grey"
"""
import sys
from PIL import Image, ImageDraw, ImageFont

PAD_RATIO = 0.022          # padding from the edges, relative to image width
FONT_RATIO = 0.030         # cap height target, relative to image width
MIN_FONT = 13


def load_font(px):
    # Windows ships these; fall back to PIL's bitmap default if none resolve.
    for name in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def add_credit(src, dst, text):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    size = max(MIN_FONT, int(w * FONT_RATIO))
    font = load_font(size)

    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    tw, th = r - l, b - t
    pad = int(w * PAD_RATIO)
    x, y = w - tw - pad, h - th - pad

    # A soft dark plate behind the text so the credit stays legible on a light plate or a bright
    # bun, which is exactly where a plain white overlay disappears.
    box = int(size * 0.45)
    d.rounded_rectangle(
        [x - box, y - box * 0.7, x + tw + box, y + th + box * 0.7],
        radius=int(size * 0.35), fill=(0, 0, 0, 130),
    )
    d.text((x - l, y - t), text, font=font, fill=(255, 255, 255, 235))

    out = Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")
    out.save(dst, quality=90, optimize=True)
    return out.size, (tw, th)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    size, tsize = add_credit(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"wrote {sys.argv[2]}  image={size[0]}x{size[1]}  credit={tsize[0]}x{tsize[1]}px")
