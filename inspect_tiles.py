from PIL import Image

try:
    img = Image.open("assets/terminal16x16_gs_ro.png")
    print(f"Loaded terminal16x16_gs_ro.png: {img.width}x{img.height}")
except Exception as e:
    print(f"Error loading: {e}")
