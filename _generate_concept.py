import base64
import json
import os
import urllib.request

ENV_PATH = os.path.expanduser("~/.config/claw-studio/env")
MODEL = "google/gemini-2.5-flash-image"


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


def generate(prompt: str, path: str) -> None:
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

    message = data["choices"][0]["message"]
    print("message keys:", sorted(message.keys()))
    text = message.get("content")
    if isinstance(text, str) and text.strip():
        print("text:", text.strip()[:500])
    images = message.get("images") or []
    print("images:", len(images))
    for index, image in enumerate(images):
        url = ""
        if isinstance(image, dict):
            url = (image.get("image_url") or {}).get("url", "")
        if not url.startswith("data:image/"):
            print("unexpected image payload:", type(image), str(image)[:200])
            continue
        header, encoded = url.split(",", 1)
        extension = "png" if "png" in header else "jpg"
        output = f"{path}.{extension}"
        with open(output, "wb") as handle:
            handle.write(base64.b64decode(encoded))
        print("saved:", output)


if __name__ == "__main__":
    prompt = (
        "Photorealistic product design render of a DIY live-streaming cassette deck "
        "named CASTCORDER. Landscape tabletop tape deck, approximately 220 mm "
        "wide, 140 mm deep and 60 mm tall, lying flat on a workbench. Warm walnut "
        "wood body with a matte black anodized aluminum top panel. Top panel layout: "
        "a large recessed cassette window with two visible reel hubs and a tape path; "
        "below it a horizontal seven-segment VU ladder of warm amber LEDs; to the left "
        "of the VU ladder one round illuminated LIVE pushbutton with a red LED ring "
        "and an engraved 'LIVE' legend; upper right a small 'ON AIR' indicator and a "
        "laser-engraved 'radio zukka' logo. Back: two gold-plated RCA/Cinch panel "
        "jacks labeled L and R, a USB-C power jack and subtle ventilation slots. "
        "Studio product photography, three-quarter view from above, warm workshop "
        "lighting, shallow depth of field, realistic materials, soft shadows, concrete "
        "workbench, one coiled RCA cable. No hands, no watermark. All lettering is "
        "crisp, correctly spelled and appears exactly once; no repeated, mirrored or "
        "gibberish text anywhere in the image."
    )
    generate(prompt, "docs/casing/concepts/10-castcorder-walnut")
