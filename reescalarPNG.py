from PIL import Image

def square_fit(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA")
    # Redimensiona manteniendo proporción
    img.thumbnail((size, size), Image.LANCZOS)
    # Lienzo cuadrado transparente y centramos
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - img.width) // 2
    y = (size - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas

src = Image.open("static/img/ATPPet-nerd.png")

for s in (16, 32, 180):
    square_fit(src.copy(), s).save(f"static/img/ATPPet-nerd-{s}.png", optimize=True)

# Opcional: favicon.ico con varios tamaños para compatibilidad legacy
square_fit(src.copy(), 256).save(
    "static/img/favicon.ico",
    format="ICO",
    sizes=[(16,16), (32,32), (48,48), (64,64)]
)
