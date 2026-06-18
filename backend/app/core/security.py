from PIL import Image


def is_image_file(filename: str) -> bool:
    lower = filename.lower()
    return lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"))


def open_image(path: str) -> Image.Image:
    image = Image.open(path)
    image.load()
    return image
