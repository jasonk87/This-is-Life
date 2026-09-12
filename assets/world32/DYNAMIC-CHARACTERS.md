# Dynamic character parts — first round

Mode: built-in image generation and background-extraction edits; no CLI or paid asset pack.

These are separate directional heads, hair, facial hair and garments, not baked profession people. Consuming code: `rendering/character_layers.py`. Originals remain unmodified; runtime cell trimming, nearest-neighbor fitting and palette transforms do not rewrite PNGs.

Four columns: south, east, north, west. Four rows per atlas except cloak (one row). Heads: four identities per face family; hair: short, long, braided, curly; beards: stubble, mustache, short, full; tops: linen, green wool, leather, iron; lower: linen trousers, wool trousers, boots, shoes; hats: cowl, straw hat (reserved art, no item yet), iron helmet, wool cap.

All selected assets verified RGBA with actual transparent pixels. Three clothing atlases required two background extraction attempts; first attempts still had baked checkerboards and were rejected. Selected files are copied unchanged into this folder. Some extraction edits slightly changed texture, so use the selected files as the canonical versions.

Style reference: `assets/world32/people-atlas-v1.png` (inspected before use). Cloak uses original generated tops atlas as its supporting style reference.

## Paths and exact prompts

### heads-male

Final: `assets/world32/dynamic-heads-male-v1.png`

Original generation: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-73916984-33ad-458c-bd28-4365448b979f.png`

Selected source: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-73916984-33ad-458c-bd28-4365448b979f.png`

Generation prompt:

```text
Use case: stylized-concept. Asset type: modular layered game-character sprite atlas.
Image 1 is STYLE REFERENCE ONLY. Generate a new atlas of separate parts, not complete people. Match its warm muted pixel-art craft, dark outlines, slightly overhead south-facing village-camera perspective, compact readable shapes and textured shading.
Exact layout: 4 columns x 4 rows, equal cells, generous transparent gutters. Each row is one identity/style/item, shown consistently in 4 directions: COLUMN1 FRONT facing viewer/south; COLUMN2 RIGHT PROFILE facing east; COLUMN3 BACK facing away/north; COLUMN4 LEFT PROFILE facing west. Row-major ordering must be exact.
Contents: Four distinct BALD CLEAN-SHAVEN male adult head identities only, no neck/body/clothing/hair/beards. Row1 broad square jaw strong nose; row2 narrow long face prominent nose; row3 round face wide cheeks small nose; row4 older angular face wrinkles pronounced cheekbones. Same warm medium skin tone throughout for runtime palette replacement. Keep all 4 identities recognizable in each direction; back views show bald scalp and ears, never eyes.
Production constraints: genuine transparent RGBA background, alpha=0 between and around parts; NO painted checkerboard, white or black background. No grid, labels, text, shadows, bodies or objects beyond the listed parts. Each part/pair centered within its cell, complete with no clipped edges. Uniform relative scale. These will be composed onto a shared character skeleton at runtime. Crisp pixels, not vector or painterly blur.
```

### heads-female

Final: `assets/world32/dynamic-heads-female-v1.png`

Original generation: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-092c50e4-ed92-4ca3-896f-5ddd1adf17e4.png`

Selected source: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-092c50e4-ed92-4ca3-896f-5ddd1adf17e4.png`

Generation prompt:

```text
Use case: stylized-concept. Asset type: modular layered game-character sprite atlas.
Image 1 is STYLE REFERENCE ONLY. Generate a new atlas of separate parts, not complete people. Match its warm muted pixel-art craft, dark outlines, slightly overhead south-facing village-camera perspective, compact readable shapes and textured shading.
Exact layout: 4 columns x 4 rows, equal cells, generous transparent gutters. Each row is one identity/style/item, shown consistently in 4 directions: COLUMN1 FRONT facing viewer/south; COLUMN2 RIGHT PROFILE facing east; COLUMN3 BACK facing away/north; COLUMN4 LEFT PROFILE facing west. Row-major ordering must be exact.
Contents: Four distinct BALD CLEAN-SHAVEN female adult head identities only, no neck/body/clothing/hair/beards. Row1 oval face straight nose; row2 broad square jaw strong brows; row3 round face wide cheeks small nose; row4 older narrow angular face wrinkles pronounced cheekbones. Same warm medium skin tone throughout for runtime palette replacement. Keep all 4 identities recognizable in each direction; back views show bald scalp and ears, never eyes.
Production constraints: genuine transparent RGBA background, alpha=0 between and around parts; NO painted checkerboard, white or black background. No grid, labels, text, shadows, bodies or objects beyond the listed parts. Each part/pair centered within its cell, complete with no clipped edges. Uniform relative scale. These will be composed onto a shared character skeleton at runtime. Crisp pixels, not vector or painterly blur.
```

### hair

Final: `assets/world32/dynamic-hair-v1.png`

Original generation: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-271c169a-efea-407d-b6af-18b9c725cd35.png`

Selected source: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-271c169a-efea-407d-b6af-18b9c725cd35.png`

Generation prompt:

```text
Use case: stylized-concept. Asset type: modular layered game-character sprite atlas.
Image 1 is STYLE REFERENCE ONLY. Generate a new atlas of separate parts, not complete people. Match its warm muted pixel-art craft, dark outlines, slightly overhead south-facing village-camera perspective, compact readable shapes and textured shading.
Exact layout: 4 columns x 4 rows, equal cells, generous transparent gutters. Each row is one identity/style/item, shown consistently in 4 directions: COLUMN1 FRONT facing viewer/south; COLUMN2 RIGHT PROFILE facing east; COLUMN3 BACK facing away/north; COLUMN4 LEFT PROFILE facing west. Row-major ordering must be exact.
Contents: Hair-only layers, no scalp/skin/face/head underneath. Four brown hair styles: row1 short side-parted cropped hair; row2 loose shoulder-length hair; row3 two braids; row4 compact curly hair. In front and profile views leave transparent openings for the forehead and face; back views show the full hair mass. The hair is worn on a head, not a wig lying on a table.
Production constraints: genuine transparent RGBA background, alpha=0 between and around parts; NO painted checkerboard, white or black background. No grid, labels, text, shadows, bodies or objects beyond the listed parts. Each part/pair centered within its cell, complete with no clipped edges. Uniform relative scale. These will be composed onto a shared character skeleton at runtime. Crisp pixels, not vector or painterly blur.
```

### beards

Final: `assets/world32/dynamic-beards-v1.png`

Original generation: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-2ee3ad0c-ccc4-4fa2-855d-b339b3fad72e.png`

Selected source: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-2ee3ad0c-ccc4-4fa2-855d-b339b3fad72e.png`

Generation prompt:

```text
Use case: stylized-concept. Asset type: modular layered game-character sprite atlas.
Image 1 is STYLE REFERENCE ONLY. Generate a new atlas of separate parts, not complete people. Match its warm muted pixel-art craft, dark outlines, slightly overhead south-facing village-camera perspective, compact readable shapes and textured shading.
Exact layout: 4 columns x 4 rows, equal cells, generous transparent gutters. Each row is one identity/style/item, shown consistently in 4 directions: COLUMN1 FRONT facing viewer/south; COLUMN2 RIGHT PROFILE facing east; COLUMN3 BACK facing away/north; COLUMN4 LEFT PROFILE facing west. Row-major ordering must be exact.
Contents: Facial-hair-only layers, absolutely no face/head/skin underneath. Four connected brown facial hair styles: row1 close-cropped chin stubble; row2 short neat mustache; row3 short rounded beard including mustache; row4 long full rounded beard including mustache. Front/profile views show the appropriate shape to overlay a lower face; for back views show only the tiny sideburn/chin fringe visible at the sides, no mouth or face. Every cell contains one isolated hair component; disconnected small tufts are okay within cell.
Production constraints: genuine transparent RGBA background, alpha=0 between and around parts; NO painted checkerboard, white or black background. No grid, labels, text, shadows, bodies or objects beyond the listed parts. Each part/pair centered within its cell, complete with no clipped edges. Uniform relative scale. These will be composed onto a shared character skeleton at runtime. Crisp pixels, not vector or painterly blur.
```

### tops

Final: `assets/world32/dynamic-tops-v1.png`

Original generation: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-41f8bee3-bc1a-494f-a5c4-dd1528b4ec31.png`

Selected source: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-03f787fe-b5b4-4806-bbcf-4321f6ee4f53.png`

Generation prompt:

```text
Use case: stylized-concept. Asset type: modular layered game-character sprite atlas.
Image 1 is STYLE REFERENCE ONLY. Generate a new atlas of separate parts, not complete people. Match its warm muted pixel-art craft, dark outlines, slightly overhead south-facing village-camera perspective, compact readable shapes and textured shading.
Exact layout: 4 columns x 4 rows, equal cells, generous transparent gutters. Each row is one identity/style/item, shown consistently in 4 directions: COLUMN1 FRONT facing viewer/south; COLUMN2 RIGHT PROFILE facing east; COLUMN3 BACK facing away/north; COLUMN4 LEFT PROFILE facing west. Row-major ordering must be exact.
Contents: Torso clothing only, no head, skin, hands, legs or boots. Garments shown as worn on invisible body with sleeves hanging naturally, waist at bottom, not laid flat. Row1 simple undyed linen long-sleeved shirt; row2 dark green wool tunic belted at waist; row3 brown leather jerkin with matching sleeves; row4 steel breastplate over dark gambeson sleeves. Neutral standing front/east/back/west view each row. No profession signs, aprons or held tools.
Production constraints: genuine transparent RGBA background, alpha=0 between and around parts; NO painted checkerboard, white or black background. No grid, labels, text, shadows, bodies or objects beyond the listed parts. Each part/pair centered within its cell, complete with no clipped edges. Uniform relative scale. These will be composed onto a shared character skeleton at runtime. Crisp pixels, not vector or painterly blur.
```

Rejected first extraction prompt:

```text
Edit this exact modular pixel-art sprite atlas: extract the sixteen clothing parts and REMOVE the baked checkerboard everywhere including enclosed face holes and gaps between paired boots. Return the exact same art, color, pixel contours, 4-by-4 row-column layout, dimensions and spacing on genuine transparent RGBA alpha. No new objects, shadows, recoloring or redesign. This is background extraction only. Preserve BOTH boots or shoes in each cell and the openings in helmets and hoods.
```

Accepted second extraction prompt:

```text
Use case: background-extraction
Remove the background from this image. Return a transparent PNG cutout with a real alpha channel. Keep all sixteen clothing objects exactly as they are and in exactly the same places. The white/gray squares are background to REMOVE, including squares inside gaps between boots and inside face openings. They must be transparent pixels in the output, not painted squares. Do not render a checkerboard.
```

### lower

Final: `assets/world32/dynamic-lower-v1.png`

Original generation: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-cd92e817-af5a-4272-bebf-a36fe114d56a.png`

Selected source: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-d6c7084a-4c9b-4ef3-846e-10c5adf6fc03.png`

Generation prompt:

```text
Use case: stylized-concept. Asset type: modular layered game-character sprite atlas.
Image 1 is STYLE REFERENCE ONLY. Generate a new atlas of separate parts, not complete people. Match its warm muted pixel-art craft, dark outlines, slightly overhead south-facing village-camera perspective, compact readable shapes and textured shading.
Exact layout: 4 columns x 4 rows, equal cells, generous transparent gutters. Each row is one identity/style/item, shown consistently in 4 directions: COLUMN1 FRONT facing viewer/south; COLUMN2 RIGHT PROFILE facing east; COLUMN3 BACK facing away/north; COLUMN4 LEFT PROFILE facing west. Row-major ordering must be exact.
Contents: Lower-body clothing components, no upper body/head/skin. Row1 plain linen trousers as worn on invisible standing legs, waist to ankles, no shoes; row2 darker wool trousers same shape; row3 a PAIR of brown calf-high leather boots side by side as worn in standing pose, no visible legs; row4 a PAIR of simple low dark leather shoes side by side as worn standing, no visible legs. Front/east/back/west views each row. The entire pair stays grouped well inside its cell.
Production constraints: genuine transparent RGBA background, alpha=0 between and around parts; NO painted checkerboard, white or black background. No grid, labels, text, shadows, bodies or objects beyond the listed parts. Each part/pair centered within its cell, complete with no clipped edges. Uniform relative scale. These will be composed onto a shared character skeleton at runtime. Crisp pixels, not vector or painterly blur.
```

Rejected first extraction prompt:

```text
Edit this exact modular pixel-art sprite atlas: extract the sixteen clothing parts and REMOVE the baked checkerboard everywhere including enclosed face holes and gaps between paired boots. Return the exact same art, color, pixel contours, 4-by-4 row-column layout, dimensions and spacing on genuine transparent RGBA alpha. No new objects, shadows, recoloring or redesign. This is background extraction only. Preserve BOTH boots or shoes in each cell and the openings in helmets and hoods.
```

Accepted second extraction prompt:

```text
Use case: background-extraction
Remove the background from this image. Return a transparent PNG cutout with a real alpha channel. Keep all sixteen clothing objects exactly as they are and in exactly the same places. The white/gray squares are background to REMOVE, including squares inside gaps between boots and inside face openings. They must be transparent pixels in the output, not painted squares. Do not render a checkerboard.
```

### hats

Final: `assets/world32/dynamic-hats-v1.png`

Original generation: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-8ba8eb56-0109-48f4-8dd6-80e04b5bc39c.png`

Selected source: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-be138d9c-3f59-49a6-898a-ca478c0b095e.png`

Generation prompt:

```text
Use case: stylized-concept. Asset type: modular layered game-character sprite atlas.
Image 1 is STYLE REFERENCE ONLY. Generate a new atlas of separate parts, not complete people. Match its warm muted pixel-art craft, dark outlines, slightly overhead south-facing village-camera perspective, compact readable shapes and textured shading.
Exact layout: 4 columns x 4 rows, equal cells, generous transparent gutters. Each row is one identity/style/item, shown consistently in 4 directions: COLUMN1 FRONT facing viewer/south; COLUMN2 RIGHT PROFILE facing east; COLUMN3 BACK facing away/north; COLUMN4 LEFT PROFILE facing west. Row-major ordering must be exact.
Contents: Headwear-only layers, no head/hair/skin underneath. As WORN on an invisible head in a neutral standing game character, not inventory tabletop icons. Row1 deep dark green hood and neck cowl with transparent face opening; row2 broad straw hat; row3 fitted iron open-face helmet; row4 soft navy wool cap. Front/east/back/west views each row. Keep hollow face openings truly transparent. No extra decorations.
Production constraints: genuine transparent RGBA background, alpha=0 between and around parts; NO painted checkerboard, white or black background. No grid, labels, text, shadows, bodies or objects beyond the listed parts. Each part/pair centered within its cell, complete with no clipped edges. Uniform relative scale. These will be composed onto a shared character skeleton at runtime. Crisp pixels, not vector or painterly blur.
```

Rejected first extraction prompt:

```text
Edit this exact modular pixel-art sprite atlas: extract the sixteen clothing parts and REMOVE the baked checkerboard everywhere including enclosed face holes and gaps between paired boots. Return the exact same art, color, pixel contours, 4-by-4 row-column layout, dimensions and spacing on genuine transparent RGBA alpha. No new objects, shadows, recoloring or redesign. This is background extraction only. Preserve BOTH boots or shoes in each cell and the openings in helmets and hoods.
```

Accepted second extraction prompt:

```text
Use case: background-extraction
Remove the background from this image. Return a transparent PNG cutout with a real alpha channel. Keep all sixteen clothing objects exactly as they are and in exactly the same places. The white/gray squares are background to REMOVE, including squares inside gaps between boots and inside face openings. They must be transparent pixels in the output, not painted squares. Do not render a checkerboard.
```

### cloak

Final: `assets/world32/dynamic-cloak-v1.png`

Original generation: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-3a0737f3-6a43-4dc2-b567-a42799134c11.png`

Selected source: `C:\Users\Owner\.codex\generated_images\01a070e9-0377-7c90-b524-08cb52e3d170\exec-3a0737f3-6a43-4dc2-b567-a42799134c11.png`

Generation prompt:

```text
Create an isolated modular fur cloak garment atlas matching the attached muted medieval pixel-art clothing. EXACTLY FOUR sprites in one horizontal row: front/south, right/east profile, back/north, left/west profile. The very same thick dark brown fur cloak with a shaggy warm gray-tan fur collar in all four views, worn on an INVISIBLE person, open at front over an undyed linen tunic with sleeves. Garment ONLY: no body, heads, faces, hands, legs, feet or ground. All four whole silhouettes separate and centered in equally sized cells with generous blank gutters. Consistent restrained earthy palette and dark pixel outlines, upper left light. Use genuine TRANSPARENT RGBA background, not a visible checkerboard, not black. No labels, text, lines, framing or background effects. Runtime fits each garment to 29x30 pixels, so clear chunky silhouette matters more than texture.
```
