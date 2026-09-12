# Generated world-art sources

The subsequent furniture/directional pass is documented separately in
[INTERIORS-MOTION.md](INTERIORS-MOTION.md), including exact prompts and source provenance.

Created for This is Life on 2026-09-12 using the built-in image-generation tool.
The first people and tree sheets used generation mode; the female counterparts
and transparency correction used edit mode with the indicated reference images.
No paid asset pack was purchased. These are AI-generated assets, not a licensed
third-party pack. Existing DawnLike assets and attribution remain unchanged.

Original tool outputs are retained in the local generated-images directory.
The three shipped PNGs are byte-for-byte copies. Atlas splitting, transparent
trimming, nearest-neighbor normalization and animation happen only in renderer
memory. The input sheets are 1254×1254, not exact 32-pixel source files. People
are normalized to 32×48 and trees to 64×80; UI tiles remain 16×16.

## Files

- `people-atlas-v1.png`: 4×4 atlas, row-major, 16 people.
  Original: `exec-25103c53-cef0-4518-b6b5-cdf548d5a166.png`.
- `trees-atlas-v1.png`: 2×2 atlas, row-major: oak, pine, apple, birch.
  Original: `exec-934841d4-ff02-4a14-87cf-1603f5a760a6.png`.
- `people-female-atlas-v1.png`: corresponding 4×4 female outfit variants.
  Final original: `exec-0d6efd4e-86c4-4494-9b87-b40663d2eea7.png`.

The first female edit (`exec-6963cd20-9f4e-40e3-91d7-c39c0440a034.png`)
had an opaque checkerboard and was rejected, not shipped. The correction was
checked for actual alpha transparency before being copied into this directory.

The tool's original files are under:
`C:/Users/Owner/.codex/generated_images/01a070e9-0377-7c90-b524-08cb52e3d170/`.

## Character generation prompt

Use case: stylized-concept. Asset type: production 2D game character sprite atlas, transparent PNG.
Create a square 1024x1024 sprite sheet with EXACTLY 16 isolated human sprites in an evenly spaced 4 by 4 grid, each cell 256x256. Each figure centered horizontally, feet at 88% of its cell height, full body height 78% of cell. No contact between cells. Transparent background, no floor, no cast shadow, no grid lines or labels.
Style: polished restrained medieval pixel art for a serious living-world simulation, 3/4 top-down RPG camera, south-facing front view. Draw as genuine low-resolution pixel clusters equivalent to 32x32 pixels per cell enlarged 8x nearest-neighbor. Hard pixel edges, compact readable silhouettes, 3-tone shading, dark brown outline, no painterly blending. Adult body proportions with clear faces, hands and boots, NOT exaggerated chibi. Warm ivory, muted forest green, russet, slate blue, leather brown and ochre. Empty hands on ALL figures: tools and carried inventory will be rendered from actual game state.
Row1 left to right: ordinary brown-haired man green tunic; ordinary auburn-haired woman blue dress; gray-haired older man brown coat; dark-skinned woman burgundy tunic.
Row2: baker with white cap and cream apron; blacksmith with charcoal shirt and leather apron; farmer with straw hat green tunic; carpenter with russet shirt leather waistcoat.
Row3: tavern keeper olive waistcoat cream shirt; merchant slate blue coat; guard steel helmet ochre tabard; healer sage robe and linen hood.
Row4: fisherman dark blue cap and tunic; scholar plum robe; hunter brown hood and green cloak; young adult traveler teal tunic.
All sixteen share exactly the same viewpoint, scale, light from upper left, foot baseline, disciplined pixel size and original coherent style. No lettering, weapons, sacks, handheld props, watermarks, logos, or environment.

## Tree generation prompt

Use case: stylized-concept. Asset type: transparent 2D pixel-art game vegetation atlas. Square image, exactly FOUR isolated trees arranged on a 2 by 2 equal grid with generous transparent padding. Top left a broad mature oak with a rich green layered round canopy and a thick brown visible trunk; top right a tall evergreen pine with stacked tapered branches; bottom left a smaller orchard apple tree with green canopy and subtle red fruit; bottom right a slim birch with pale bark and airy green canopy. Full trees visible, consistent three-quarter top-down RPG view, matching restrained medieval pixel art. Strong recognizable silhouettes, coherent 32x48-pixel source-art aesthetic enlarged nearest-neighbor, crisp clusters, 3-tone shade, upper-left lighting, forest/olive/ochre palette, not painterly. All trees same foot baseline within each cell. No ground islands, no circles, no text, no labels, no grid, no people, no watermark. Genuine alpha-transparent background.

## Female counterpart edit prompt

Reference: `people-atlas-v1.png`.

Edit this transparent 4x4 medieval character atlas into matching FEMALE counterparts of each figure. Preserve the exact 4 by 4 equal grid, all 16 cell positions, full-body scale, foot baselines, south-facing three-quarter top-down RPG viewpoint, hard pixel-art aesthetic, muted colors and lighting, and each character's corresponding profession outfit and headgear. Keep the three already female figures female. Change the male faces/body shapes to adult women with varied practical hairstyles, no beards or mustaches, and no exaggerated sexual features. All clothes remain practical and non-revealing. Row 1: woman in green tunic; woman in blue dress; elderly gray-haired woman in brown coat; dark-skinned woman in burgundy. Row 2: female baker in white cap and cream apron; female blacksmith charcoal shirt leather apron; female farmer straw hat green tunic; female carpenter russet waistcoat. Row 3: female tavern keeper olive waistcoat; female merchant blue coat; female guard steel helmet ochre tabard; female healer sage robe linen hood. Row 4: female fisher blue cap; female scholar plum robe; female hunter hooded green cloak; young adult female traveler teal tunic. Empty hands throughout. Genuine transparent background with no floor, shadow, grid, labels, text, or extra objects. Keep each entire figure inside its own equal square cell with padding. Output a square PNG atlas.

## Transparency correction prompt

Reference: rejected opaque female edit.

Remove the baked gray-and-white checkerboard background completely. Preserve every pixel-art woman, all 16 sprites, all details, positions, sizes, colors and the exact 4x4 grid. Change ONLY the background to true transparent alpha, including between limbs and around hair. The output must be an RGBA PNG with actual alpha=0 empty regions, not an illustration of transparency or a checker pattern. Do not add shadows, labels or a background color. Production game sprite atlas with transparent background.

## Runtime mapping and limitations

People indices: common green tunic, blue dress, elder, burgundy tunic, baker,
blacksmith, farmer, carpenter, tavern keeper, merchant, armored guard, healer,
fisher, scholar, hunter, young traveler. The second sheet adds 16 to an index.
Profession identifies an outfit, never an activity. The armored guard base
requires an actual equipped iron helmet. This is not a complete paper-doll
system: full trait-accurate faces, skin palettes and hairstyles remain work to
do. Equipment overlays still read actual slots.

Source people have empty hands. Tools, carried inventory, food and speech cues
are layered by the renderer from actual state. Trees keep transparent silhouettes.
Pear trees currently use the fruitless oak artwork rather than displaying apples.
Architecture, signs, shoulders and cues are generated by local rendering code
from world metadata, not supplied by these PNGs.
