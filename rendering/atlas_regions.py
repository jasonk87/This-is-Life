"""Read isolated atlas silhouettes, including art extending across grid gutters.

The source PNG is never modified. Row-run connected components associate each
whole silhouette with its grid cell by its center, avoiding clipped table legs
or a forge's bellows leaking into the neighboring oven sprite.
"""

from runtime_compat import np


def silhouette_bounds(alpha, columns, rows):
    mask = alpha > 32
    parent, boxes, areas = [], [], []

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    previous = []
    for y in range(mask.shape[0]):
        line = np.pad(mask[y].astype(np.int8), (1, 1))
        changes = np.diff(line)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        current = []
        previous_index = 0
        for x0, x1 in zip(starts, ends):
            x0, x1 = int(x0), int(x1)
            index = len(parent)
            parent.append(index)
            boxes.append([x0, y, x1, y + 1])
            areas.append(x1 - x0)
            while previous_index < len(previous) and previous[previous_index][1] < x0:
                previous_index += 1
            j = previous_index
            while j < len(previous) and previous[j][0] <= x1:
                other = root(previous[j][2])
                if other != index:
                    parent[other] = index
                    old = boxes[other]
                    boxes[index] = [
                        min(boxes[index][0], old[0]),
                        min(boxes[index][1], old[1]),
                        max(boxes[index][2], old[2]),
                        max(boxes[index][3], old[3]),
                    ]
                    areas[index] += areas[other]
                j += 1
            current.append((x0, x1, index))
        previous = current

    cells = [None] * (columns * rows)
    scores = [0] * len(cells)
    for index, box in enumerate(boxes):
        if parent[index] != index or areas[index] < 32:
            continue
        x0, y0, x1, y1 = box
        column = min(columns - 1, ((x0 + x1) * columns) // (2 * mask.shape[1]))
        row = min(rows - 1, ((y0 + y1) * rows) // (2 * mask.shape[0]))
        cell = row * columns + column
        if areas[index] > scores[cell]:
            cells[cell], scores[cell] = tuple(box), areas[index]
    if any(box is None for box in cells):
        raise ValueError(
            "Atlas needs one isolated silhouette per cell; missing or touching sprites"
        )
    return tuple(cells)


def read_silhouettes(path, columns=4, rows=4):
    from PIL import Image

    source = np.array(Image.open(path).convert("RGBA"))
    if not (source[:, :, 3] < 32).any():
        raise ValueError(f"Atlas requires genuine transparency: {path}")
    return tuple(
        source[y0:y1, x0:x1].copy()
        for x0, y0, x1, y1 in silhouette_bounds(source[:, :, 3], columns, rows)
    )


def read_parts(path, columns=4, rows=4):
    """Trim each modular cell as a whole, retaining disconnected paired parts.

    Unlike furniture silhouettes, both boots/sideburns belong to one part.
    These atlases require empty gutters and never borrow neighboring pixels.
    """
    from PIL import Image

    source = np.array(Image.open(path).convert("RGBA"))
    if not (source[:, :, 3] < 32).any():
        raise ValueError(f"Atlas requires genuine transparency: {path}")
    parts = []
    h, w = source.shape[:2]
    for row in range(rows):
        for col in range(columns):
            cell = source[row*h//rows:(row+1)*h//rows, col*w//columns:(col+1)*w//columns]
            yy, xx = np.nonzero(cell[:, :, 3] > 32)
            if not len(xx):
                raise ValueError(f"Empty part at {row}, {col}: {path}")
            parts.append(cell[yy.min():yy.max()+1, xx.min():xx.max()+1].copy())
    return tuple(parts)


def normalize(source, width, height):
    from rendering.pixel_scene import resize

    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    scale = min((width - 4) / source.shape[1], (height - 4) / source.shape[0])
    w, h = max(1, round(source.shape[1] * scale)), max(1, round(source.shape[0] * scale))
    canvas[height - h - 2 : height - 2, (width - w) // 2 : (width - w) // 2 + w] = resize(
        source, w, h
    )
    return canvas
