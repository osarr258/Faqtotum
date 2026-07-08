"""One-shot script: Generate 3 cinematic hero images for Auxora onboarding."""
import asyncio
import base64
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent / ".env")

from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: E402

OUT = Path("/app/frontend/assets/images")
OUT.mkdir(parents=True, exist_ok=True)

STYLE = (
    "Ultra-premium cinematic advertising still, dark matte black atmosphere with "
    "warm champagne gold accents (#C8A96B), soft volumetric light rays, subtle "
    "golden dust particles in the air, luxury Apple/Tesla/Revolut aesthetic, "
    "shot on ARRI Alexa, 35mm lens, shallow depth of field, glossy reflections, "
    "editorial lighting, hyper-detailed, 8K, vertical 9:16 composition suitable "
    "for a mobile phone screen background, cinematic color grading, no text, no logo."
)

SCENES = [
    (
        "auxora_hero_1.png",
        "Scene: A luxurious modern Parisian apartment interior at dusk, warm ambient "
        "lighting from designer lamps, tall windows revealing a rainy city night, "
        "a hand holds a floating premium smartphone in the foreground with a soft "
        "golden glow emanating from its screen, hints of AI interface bokeh, a very "
        "subtle single water droplet suspended in mid-air catches the light, "
        "conveying tension and a problem about to be solved. Deep blacks, champagne "
        "gold highlights, moody but sophisticated. " + STYLE,
    ),
    (
        "auxora_hero_2.png",
        "Scene: An elegant verified professional artisan (French craftsman, mid-30s, "
        "neat modern uniform) standing confidently in a beautifully lit workshop, "
        "surrounded by floating holographic UI cards displaying verification badges "
        "(shield icons, 4.9 stars, 18 min availability), golden AI particles swirling "
        "around them, sharp precision tools reflect champagne gold light, futuristic "
        "yet human, matte black background gradient, sense of trust and premium quality. "
        + STYLE,
    ),
    (
        "auxora_hero_3.png",
        "Scene: The same luxurious apartment interior from Scene 1, but now completely "
        "serene, everything perfectly restored, a homeowner silhouette relaxed with a "
        "warm drink, golden hour sunlight streaming through the tall windows, floating "
        "translucent 'Digital Home Passport' hologram softly glowing in the foreground, "
        "sense of peace, security, effortless luxury, calm after the storm. Deep "
        "cinematic tones, champagne gold and off-white palette. " + STYLE,
    ),
]


async def generate_one(fname: str, prompt: str):
    api_key = os.getenv("EMERGENT_LLM_KEY")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"auxora-hero-{fname}",
        system_message="You are a premium visual generation assistant.",
    )
    chat.with_model("gemini", "gemini-3-pro-image-preview").with_params(modalities=["image", "text"])
    msg = UserMessage(text=prompt)
    text, images = await chat.send_message_multimodal_response(msg)
    if not images:
        print(f"[FAIL] {fname} — no images returned. Text: {text[:120]}")
        return False
    img = images[0]
    out_path = OUT / fname
    out_path.write_bytes(base64.b64decode(img["data"]))
    size_kb = out_path.stat().st_size // 1024
    print(f"[OK]   {fname} ({size_kb} KB)")
    return True


async def main():
    for fname, prompt in SCENES:
        try:
            await generate_one(fname, prompt)
        except Exception as e:
            print(f"[ERR]  {fname}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
