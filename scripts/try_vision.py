"""Manual test: send ONE photo to the real model and print what it sees.

It spends API quota (one call). Run it from the repo root with a photo path:

    python scripts/try_vision.py path/to/photo.jpg

It reads the model and the key from config/settings.py, which reads your .env.
This is step 5a: just to see how a model receives an image. The real tool,
with checks and a fixed answer format, comes in the next steps.
"""

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]  # to import config/ and tertulia/

from config.settings import settings  # noqa: E402
from tertulia.crew.crew import llm_from_settings  # noqa: E402

MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

if len(sys.argv) != 2:
    sys.exit("Usage: python scripts/try_vision.py path/to/photo.jpg")
photo = Path(sys.argv[1])
if photo.suffix.lower() not in MIME_TYPES:
    sys.exit("Only .jpg, .jpeg and .png photos.")
if not settings.LLM_API_KEY.get_secret_value():
    sys.exit("LLM_API_KEY is missing in your .env file (at the repo root).")

# 1. The photo becomes text (base64), because a message can only carry text.
image_b64 = base64.b64encode(photo.read_bytes()).decode("ascii")

# 2. One message with two parts: the question and the image.
#    "inlineData" is the format Gemini expects for an image inside a message.
message = {
    "role": "user",
    "content": [
        {
            "text": (
                "Describe en español, en 3-5 frases, lo que se ve en esta foto de un "
                "local. Solo lo que se ve con claridad. Si hay texto (precios, "
                "carteles), cópialo tal cual."
            )
        },
        {"inlineData": {"mimeType": MIME_TYPES[photo.suffix.lower()], "data": image_b64}},
    ],
}

print(f"Model: {settings.LLM_PROVIDER}/{settings.LLM_MODEL_NAME}")  # never the key
print(f"Photo: {photo.name} ({photo.stat().st_size // 1024} KB)\n")
answer = llm_from_settings().call(messages=[message])
print(answer)