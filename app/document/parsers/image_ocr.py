import pytesseract
from PIL import Image


def parse_image(file_path: str) -> str:
    img = Image.open(file_path)
    text = pytesseract.image_to_string(img, lang="chi_sim+eng")
    return text
