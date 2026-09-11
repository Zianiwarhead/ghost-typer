"""Generate a simple Ghost Typer icon (ghost + keys) into assets/."""
import os

from PIL import Image, ImageDraw

SIZE = 256
BG = (24, 24, 32, 255)
GHOST = (240, 240, 245, 255)
ACCENT = (124, 93, 250, 255)

out_dir = os.path.join(os.path.dirname(__file__), "..", "assets")
os.makedirs(out_dir, exist_ok=True)

img = Image.new("RGBA", (SIZE, SIZE), BG)
d = ImageDraw.Draw(img)

# Ghost body: rounded top + wavy bottom
d.ellipse([48, 36, 208, 170], fill=GHOST)
d.rectangle([48, 100, 208, 190], fill=GHOST)
for i, x in enumerate(range(48, 209, 32)):
    d.ellipse([x, 160, x + 32, 196], fill=BG if i % 2 == 0 else GHOST)
# Eyes + mouth
d.ellipse([92, 96, 116, 124], fill=(20, 20, 28, 255))
d.ellipse([140, 96, 164, 124], fill=(20, 20, 28, 255))
d.ellipse([118, 132, 138, 150], fill=(20, 20, 28, 255))
# Keyboard hint bar
d.rounded_rectangle([70, 200, 186, 228], radius=8, fill=ACCENT)

img.save(os.path.join(out_dir, "icon.png"))
# Multi-size ICO for Windows / PyInstaller
ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(os.path.join(out_dir, "icon.ico"), sizes=ico_sizes)
print("Wrote assets/icon.png + assets/icon.ico")
