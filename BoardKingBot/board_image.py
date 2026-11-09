"""Draws the game board as a PNG with Pillow: tiles, owner bars, houses/hotels, mortgages,
player tokens and the last dice."""
import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from board import BOARD

CORNER, TW = 100, 90
SIZE = 2 * CORNER + 9 * TW            # 1010 px
PLAYER_COLORS = [(220, 50, 47), (38, 139, 210), (46, 160, 67), (240, 190, 20)]
PLAYER_EMOJI = ["🟥", "🟦", "🟩", "🟨"]
BG, PAPER, INK = (205, 230, 208), (250, 247, 235), (30, 30, 30)
FONT_PATHS = ["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf",
              "C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"]
BOLD_PATHS = ["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf",
              "C:/Windows/Fonts/arialbd.ttf"]
SHORT = {"property": "", "railway": "RAIL", "utility": "UTILITY", "chance": "CHANCE", "community": "EVENT",
         "tax": "TAX", "start": "START", "jail": "JAIL", "free_parking": "FREE PARKING", "go_to_jail": "GO TO JAIL"}


@lru_cache(maxsize=32)
def font(size: int, bold: bool = False):
    for path in (BOLD_PATHS if bold else FONT_PATHS) + FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def tile_rect(pos: int) -> tuple:
    if pos == 0:
        return SIZE - CORNER, SIZE - CORNER, SIZE, SIZE
    if pos < 10:
        x = SIZE - CORNER - pos * TW
        return x, SIZE - CORNER, x + TW, SIZE
    if pos == 10:
        return 0, SIZE - CORNER, CORNER, SIZE
    if pos < 20:
        y2 = SIZE - CORNER - (pos - 11) * TW
        return 0, y2 - TW, CORNER, y2
    if pos == 20:
        return 0, 0, CORNER, CORNER
    if pos < 30:
        x = CORNER + (pos - 21) * TW
        return x, 0, x + TW, CORNER
    if pos == 30:
        return SIZE - CORNER, 0, SIZE, CORNER
    y = CORNER + (pos - 31) * TW
    return SIZE - CORNER, y, SIZE, y + TW


def side(pos: int) -> str:
    return "bottom" if pos < 10 else "left" if pos < 20 else "top" if pos < 30 else "right"


def clean(text: str) -> str:
    """Remove emoji/unsupported symbols (the board font cannot draw them)."""
    out = "".join(ch for ch in text if ord(ch) < 0x2000 or 0x2100 <= ord(ch) < 0x2190)
    return out.strip() or "Player"


def _hex(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _wrap(d, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _center_text(d, box, text, f, fill=INK):
    x1, y1, x2, y2 = box
    lines = _wrap(d, text, f, x2 - x1 - 6)
    lh = f.size + 2
    y = (y1 + y2) / 2 - lh * len(lines) / 2
    for ln in lines:
        w = d.textlength(ln, font=f)
        d.text(((x1 + x2) / 2 - w / 2, y), ln, font=f, fill=fill)
        y += lh


def _stripe_rect(pos, thickness=24):
    x1, y1, x2, y2 = tile_rect(pos)
    s = side(pos)
    return {"bottom": (x1, y1, x2, y1 + thickness), "top": (x1, y2 - thickness, x2, y2),
            "left": (x2 - thickness, y1, x2, y2), "right": (x1, y1, x1 + thickness, y2)}[s]


def _outer_bar(pos, thickness=9):
    x1, y1, x2, y2 = tile_rect(pos)
    s = side(pos)
    return {"bottom": (x1, y2 - thickness, x2, y2), "top": (x1, y1, x2, y1 + thickness),
            "left": (x1, y1, x1 + thickness, y2), "right": (x2 - thickness, y1, x2, y2)}[s]


_BASE = {"rev": None, "img": None}


def base_board() -> Image.Image:
    if _BASE["rev"] == BOARD.revision:
        return _BASE["img"]
    img = Image.new("RGB", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(img)
    for t in BOARD.tiles:
        r = tile_rect(t.id)
        d.rectangle(r, fill=PAPER, outline=INK, width=2)
        if t.type == "property":
            d.rectangle(_stripe_rect(t.id), fill=_hex(t.color), outline=INK)
        label = t.name
        body = list(r)
        s = side(t.id)
        if t.type == "property":
            sr = _stripe_rect(t.id)
            if s == "bottom": body[1] = sr[3]
            elif s == "top": body[3] = sr[1]
            elif s == "left": body[2] = sr[0]
            else: body[0] = sr[2]
        if t.id in (0, 10, 20, 30):
            f = font(17, True)
            _center_text(d, (r[0], r[1], r[2], r[3] - 22), SHORT[t.type] if t.type != "jail" else "JAIL", f)
            small = {"start": "Collect salary", "jail": "Just visiting", "free_parking": "Rest", "go_to_jail": "Arrest!"}[t.type]
            _center_text(d, (r[0], r[3] - 38, r[2], r[3] - 4), small, font(11))
            continue
        top = body[1] + 4 if s != "top" or t.type != "property" else body[1] + 4
        label_font = font(12, True)
        if t.type in ("chance", "community", "tax", "railway", "utility"):
            _center_text(d, (body[0], body[1], body[2], body[1] + 52), t.name, label_font)
            if t.type == "tax":
                _center_text(d, (body[0], body[1] + 50, body[2], body[3] - 4), f"Pay {t.amount}", font(12))
            elif t.price:
                _center_text(d, (body[0], body[3] - 30, body[2], body[3] - 8), str(t.price), font(12))
        else:
            _center_text(d, (body[0], body[1], body[2], body[1] + (body[3] - body[1]) * 0.6), t.name, label_font)
            _center_text(d, (body[0], body[3] - 32, body[2], body[3] - 8), str(t.price), font(12))
    # centre panel
    c = (CORNER + 14, CORNER + 14, SIZE - CORNER - 14, SIZE - CORNER - 14)
    d.rectangle(c, fill=(238, 224, 180), outline=INK, width=3)
    _center_text(d, (c[0], c[1] + 60, c[2], c[1] + 150), "BOARDKING", font(64, True), (120, 60, 20))
    _center_text(d, (c[0], c[1] + 150, c[2], c[1] + 200), "BUSINESS GAME", font(26, True), (120, 60, 20))
    _BASE.update(rev=BOARD.revision, img=img)
    return img


def _draw_die(d, x, y, n, s=70):
    d.rounded_rectangle((x, y, x + s, y + s), 12, fill="white", outline=INK, width=3)
    g = s / 4
    pips = {1: [(2, 2)], 2: [(1, 1), (3, 3)], 3: [(1, 1), (2, 2), (3, 3)], 4: [(1, 1), (3, 1), (1, 3), (3, 3)],
            5: [(1, 1), (3, 1), (2, 2), (1, 3), (3, 3)], 6: [(1, 1), (3, 1), (1, 2), (3, 2), (1, 3), (3, 3)]}[n]
    for px, py in pips:
        cx, cy = x + px * g, y + py * g
        d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=INK)


def render_board(game) -> bytes:
    """Return PNG bytes of the board for the current game state."""
    img = base_board().copy()
    d = ImageDraw.Draw(img)
    order = {p.id: i for i, p in enumerate(game.players)}
    for tid, owner in game.tile_owner.items():
        t = BOARD[tid]
        col = PLAYER_COLORS[order.get(owner, 0) % 4]
        d.rectangle(_outer_bar(tid), fill=col)
        r = tile_rect(tid)
        if tid in game.mortgaged:
            d.line((r[0] + 6, r[1] + 6, r[2] - 6, r[3] - 6), fill=(120, 120, 120), width=5)
            d.line((r[0] + 6, r[3] - 6, r[2] - 6, r[1] + 6), fill=(120, 120, 120), width=5)
        h = game.houses.get(tid, 0)
        if h:
            sr = _stripe_rect(tid)
            cx, cy = (sr[0] + sr[2]) / 2, (sr[1] + sr[3]) / 2
            if h == 5:
                d.rectangle((cx - 14, cy - 9, cx + 14, cy + 9), fill=(200, 30, 30), outline=INK)
            else:
                horizontal = side(tid) in ("bottom", "top")
                for i in range(h):
                    off = (i - (h - 1) / 2) * 16
                    x, y = (cx + off, cy) if horizontal else (cx, cy + off)
                    d.rectangle((x - 6, y - 6, x + 6, y + 6), fill=(30, 160, 60), outline=INK)
    # tokens
    by_pos: dict[int, list] = {}
    for p in game.players:
        if not p.bankrupt:
            by_pos.setdefault(p.pos, []).append(p)
    for pos, plist in by_pos.items():
        x1, y1, x2, y2 = tile_rect(pos)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 + 8
        for k, p in enumerate(plist):
            ox = (k % 2) * 28 - 14
            oy = (k // 2) * 28 - 8
            col = PLAYER_COLORS[order[p.id] % 4]
            r = 13
            d.ellipse((cx + ox - r, cy + oy - r, cx + ox + r, cy + oy + r), fill=col, outline=INK, width=3)
            if p.in_jail:
                d.rectangle((cx + ox - 5, cy + oy - 9, cx + ox + 5, cy + oy + 9), outline=INK, width=2)
    # centre info: dice, room, round
    c0 = CORNER + 14
    _center_text(d, (c0, 400, SIZE - c0, 440), f"Room {game.room_id}   Round {game.round}", font(24, True))
    if game.dice:
        _draw_die(d, SIZE / 2 - 85, 470, game.dice[0])
        _draw_die(d, SIZE / 2 + 15, 470, game.dice[1])
    if game.state.value != "WAITING_FOR_PLAYERS" and not game.finished:
        cur = game.current
        col = PLAYER_COLORS[order[cur.id] % 4]
        d.ellipse((SIZE / 2 - 190, 575, SIZE / 2 - 168, 597), fill=col, outline=INK, width=2)
        d.text((SIZE / 2 - 155, 570), f"Turn: {clean(cur.name)}"[:28], font=font(24, True), fill=INK)
    # legend
    y = 640
    for i, p in enumerate(game.players):
        col = PLAYER_COLORS[i % 4]
        d.ellipse((c0 + 60, y + 4, c0 + 78, y + 22), fill=col, outline=INK, width=2)
        label = f"{clean(p.name)[:16]}  {'OUT' if p.bankrupt else p.cash}"
        d.text((c0 + 90, y), label, font=font(20), fill=(120, 120, 120) if p.bankrupt else INK)
        y += 30
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=False)
    return out.getvalue()
