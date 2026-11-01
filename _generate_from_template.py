"""Generate a photoreal Castcorder render from the hand-drawn template."""

import base64
import json
import os
import urllib.error
import urllib.request

ENV_PATH = os.path.expanduser("~/.config/claw-studio/env")
TEMPLATE = "docs/casing/template.png"
OUTPUT = "docs/casing/concepts/19-castcorder-realistic.png"
MODEL = "google/gemini-2.5-flash-image"

PROMPT = (
    "Use the attached hand-drawn sketch as the exact design template. Generate a "
    "photorealistic product render of the Castcorder, an old-school 1970s/80s "
    "cassette deck recorder built for live streaming. Preserve the sketch's layout "
    "and proportions: a wedge-shaped oiled walnut wooden case, a sloped top panel, "
    "an upper framed panel with 'radio zukka' lettering, a cassette window with two "
    "visible reel hubs and an 'ON AIR' label, a horizontal VU meter scale below it, "
    "five cream-colored piano keys on the front, and a red illuminated LIVE button "
    "on the left. Add realistic details: brushed aluminum top panel, brass screws, "
    "warm amber VU LEDs, a real cassette shell behind the window, RCA jacks on the "
    "back, rubber feet. Studio product photography, three-quarter view from above, "
    "warm workshop lighting, shallow depth of field, realistic wood grain and "
    "reflections, soft shadows, concrete workbench. No hands, no watermark. All "
    "lettering is crisp, correctly spelled and appears exactly once; no repeated, "
    "mirrored or gibberish text anywhere in the image."
)


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


def main() -> None:
    with open(TEMPLATE, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    },
                ],
            }
        ],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": "4:3"},
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {load_key()}",
            "Content-Type": "application/json",
            "X-Title": "Castcorder Template Render",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        print("HTTP", error.code)
        print(error.read().decode("utf-8", "replace")[:2000])
        return

    message = data["choices"][0]["message"]
    text = message.get("content")
    if isinstance(text, str) and text.strip():
        print("text:", text.strip()[:500])
    images = message.get("images") or []
    print("images:", len(images))
    for image in images:
        url = (
            (image.get("image_url") or {}).get("url", "")
            if isinstance(image, dict)
            else ""
        )
        if not url.startswith("data:image/"):
            print("unexpected payload:", str(image)[:200])
            continue
        header, encoded_image = url.split(",", 1)
        extension = "png" if "png" in header else "jpg"
        output = OUTPUT if extension == "png" else OUTPUT.rsplit(".", 1)[0] + ".jpg"
        with open(output, "wb") as handle:
            handle.write(base64.b64decode(encoded_image))
        print("saved:", output)


if __name__ == "__main__":
    main()
