import urllib.request

urls = [
    ("https://raw.githubusercontent.com/libtcod/python-tcod/main/fonts/libtcod/Bisasam_20x20.png", "Bisasam_20x20.png"),
    ("https://raw.githubusercontent.com/libtcod/python-tcod/main/fonts/libtcod/CGA8x8thin.png", "CGA8x8thin.png"),
    ("https://raw.githubusercontent.com/libtcod/python-tcod/main/fonts/libtcod/curses_640x300.png", "curses_640x300.png")
]

for url, filename in urls:
    try:
        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req)
        with open("assets/" + filename, "wb") as f:
            f.write(response.read())
        print(f"Downloaded {filename}")
    except Exception as e:
        print(f"Failed {filename}: {e}")
