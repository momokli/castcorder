import base64
import json
import os
import urllib.request

ENV_PATH = os.path.expanduser("~/.config/claw-studio/env")
MODEL = "google/gemini-2.5-flash-image"

COMMON = (
    "Photorealistic product render of a DIY live-streaming cassette deck named "
    "CASTCORDER. Landscape tabletop tape deck, approximately 220 mm wide, "
    "140 mm deep and 60 mm tall, lying flat on a workbench. "
)

LAYOUT = (
    "Top panel layout: a large recessed cassette window with two visible reel hubs "
    "and a tape path; below it a horizontal seven-segment VU ladder of warm amber "
    "LEDs; to the left of the VU ladder one illuminated LIVE pushbutton with a red "
    "LED ring and an engraved 'LIVE' legend; upper right a small 'ON AIR' indicator "
    "and a laser-engraved 'radio zukka' logo. Back: two gold-plated RCA/Cinch panel "
    "jacks labeled L and R, a USB-C power jack and subtle ventilation slots. "
)

STYLE = (
    "Studio product photography, three-quarter view from above, warm workshop "
    "lighting, shallow depth of field, realistic materials, soft shadows, concrete "
    "workbench, one coiled RCA cable. No hands, no watermark. All lettering is "
    "crisp, correctly spelled and appears exactly once; no repeated, mirrored or "
    "gibberish text anywhere in the image."
)

PROMPTS = {
    "11-castcorder-birch": (
        COMMON
        + "Light birch plywood body with a brushed aluminum top panel. "
        + LAYOUT
        + "The LIVE pushbutton is a large 60 mm translucent arcade button with a warm "
        "amber LED glow. " + STYLE
    ),
    "12-castcorder-black": (
        COMMON
        + "Matte black anodized aluminum body with a solid walnut wood top panel. "
        + LAYOUT
        + "The LIVE pushbutton is a massive 100 mm translucent arcade button with a "
        "deep red LED glow. " + STYLE
    ),
    "13-castcorder-printed": (
        COMMON + "Charcoal gray 3D-printed enclosure with visible layer texture, "
        "copper-colored accents and exposed hex screws; matte black top panel. "
        + LAYOUT
        + "The LIVE pushbutton is a premium 22 mm stainless-steel EAO-style "
        "illuminated ring button with a green LED ring. " + STYLE
    ),
    "14-castcorder-walnut-corrected": (
        COMMON
        + "Warm walnut wood body with a matte black anodized aluminum top panel. "
        + LAYOUT
        + "The LIVE pushbutton is a premium 22 mm stainless-steel EAO-style "
        "illuminated pushbutton with a warm-white LED ring. " + STYLE
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
            "X-Title": "Castcorder Concept",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        data = json.load(response)
    images = data["choices"][0]["message"].get("images") or []
    if not images:
        print("NO IMAGE FOR", name, data["choices"][0]["message"].get("refusal"))
        return
    url = (images[0].get("image_url") or {}).get("url", "")
    header, encoded = url.split(",", 1)
    path = f"docs/casing/concepts/{name}.png"
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(encoded))
    print("saved:", path)


if __name__ == "__main__":
    for name, prompt in PROMPTS.items():
        generate(name, prompt)
