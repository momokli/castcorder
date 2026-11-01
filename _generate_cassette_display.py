"""KI-Konzepte: Kassette von radio.zukkafabrik.de auf E-Ink im Castcorder.

Der Web-Player zeigt eine handgezeichnete Kassette (Teal/Weiß) mit Track,
Artist und Hörerzahl. Diese Renderings übertragen das Motiv auf ein oder
mehrere E-Ink-Displays im Deck-Panel und kombinieren es mit der
siebensegmentigen VU-Leiter und einem EAO-Series-22-LIVE-Taster.

Aufruf:
    python3 _generate_cassette_display.py            # alle Konzepte
    python3 _generate_cassette_display.py 15 17      # nur ausgewählte
"""

import base64
import json
import os
import sys
import urllib.request

ENV_PATH = os.path.expanduser("~/.config/claw-studio/env")
MODEL = "google/gemini-3-pro-image"

COMMON = (
    "Photorealistic product render of a DIY live-streaming cassette deck named "
    "CASTCORDER. Landscape tabletop tape deck, approximately 220 mm wide, "
    "140 mm deep and 60 mm tall, lying flat on a workbench. Warm walnut wood body "
    "with a matte black anodized aluminum top panel. The top panel has a horizontal "
    "seven-segment VU ladder of warm amber LEDs and one EAO Series 22 industrial "
    "illuminated pushbutton, 22.5 mm round, black plastic front bezel, flush "
    "translucent lens, warm amber LED ring glowing, with an engraved 'LIVE' legend "
    "on the panel beside it. Upper right: a small 'ON AIR' indicator and a "
    "laser-engraved 'radio zukka' logo. Back: two gold-plated RCA/Cinch panel jacks "
    "labeled L and R, a USB-C power jack and subtle ventilation slots. Studio "
    "product photography, three-quarter view from above, warm workshop lighting, "
    "shallow depth of field, realistic materials, soft shadows, concrete workbench, "
    "one coiled RCA cable. No hands, no watermark. All lettering is crisp, correctly "
    "spelled and appears exactly once; no repeated, mirrored or gibberish text "
    "anywhere in the image."
)

PROMPTS = {
    "15-castcorder-eink-single": (
        COMMON + " The top panel is dominated by one large 4.2 inch three-color e-ink "
        "display (black, white, red) with a paper-white background, recessed flush "
        "behind a thin black bezel. On the e-ink, a hand-drawn comic-style cassette "
        "tape is shown in black ink with light gray shading: rounded cassette shell, "
        "two reel hubs, a white label area. In the label area: a small solid red badge "
        "reading 'LIVE', a hand-lettered track title 'MIDNIGHT TAPE', the artist "
        "'VIDLINGS & TAPEHEADS', and a headphone icon with '7 LISTENERS'. Printed on "
        "the cassette: 'LOW NOISE' and '120 MIN'. The VU ladder sits below the "
        "display. No PLAY button anywhere."
    ),
    "16-castcorder-eink-dual": (
        COMMON + " The top panel carries two separate recessed e-ink displays side by "
        "side. Left: a large 4.2 inch monochrome e-ink display with paper-white "
        "background showing a hand-drawn comic-style cassette tape in black ink with "
        "light gray shading, two reel hubs, and a white label area with a "
        "hand-lettered track title 'MIDNIGHT TAPE' and the artist 'VIDLINGS & "
        "TAPEHEADS'. Right: a narrow 2.9 inch three-color e-ink strip (black, white, "
        "red) showing a solid red 'LIVE' badge, a headphone icon with '7 LISTENERS', "
        "'ON AIR 00:42' and '192 kbps' in clean monospace. The VU ladder sits below "
        "the displays. No PLAY button anywhere."
    ),
    "17-castcorder-eink-color": (
        COMMON + " The top panel is almost entirely one large 7-color electrophoretic "
        "e-ink display with a paper-white background and a thin recessed black bezel. "
        "The e-ink shows the hand-drawn comic-style cassette from radio zukka in muted "
        "teal, white and black: rounded cassette shell, two reel hubs, a teal-and-white "
        "label area, small printed 'LOW NOISE' and '120 MIN' lettering. In the label "
        "area: a solid red 'LIVE' badge, a hand-lettered track title 'MIDNIGHT TAPE', "
        "the artist 'VIDLINGS & TAPEHEADS', and a headphone icon with '7 LISTENERS'. "
        "The e-ink colors are soft and paper-like, not glowing. The VU ladder sits "
        "below the display. No PLAY button anywhere."
    ),
}


def load_key() -> str:
    values = {}
    with open(ENV_PATH, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            values[key] = value.strip().strip('"').strip("'")
    return values["OPENROUTER_API_KEY"]


def generate(name: str, prompt: str) -> None:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": "4:3"},
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {load_key()}",
            "Content-Type": "application/json",
            "X-Title": "Castcorder Cassette E-Ink",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.load(response)
    message = data["choices"][0]["message"]
    images = message.get("images") or []
    if not images:
        print("NO IMAGE FOR", name, message.get("refusal"))
        return
    url = (images[0].get("image_url") or {}).get("url", "")
    header, encoded = url.split(",", 1)
    path = f"docs/casing/concepts/{name}.png"
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(encoded))
    print("saved:", path)


if __name__ == "__main__":
    wanted = sys.argv[1:]
    for name, prompt in PROMPTS.items():
        if wanted and not any(name.startswith(prefix) for prefix in wanted):
            continue
        generate(name, prompt)
