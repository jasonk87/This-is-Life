import urllib.request
import json
url = "https://api.github.com/repos/libtcod/python-tcod/contents/fonts/libtcod"
req = urllib.request.Request(url)
try:
    response = urllib.request.urlopen(req)
    data = json.loads(response.read())
    for item in data:
        print(item['name'])
except Exception as e:
    print(e)
