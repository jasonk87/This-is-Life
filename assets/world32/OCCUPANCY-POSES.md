# Occupied-furniture pose atlas provenance

Generated 2026-09-12 with the built-in image-generation tool. No external pack, purchase, API fallback, or model switch. The imagegen skill guided identity-preserving edits and the required alpha verification.

All originals remain under `C:/Users/Owner/.codex/generated_images/01a070e9-0377-7c90-b524-08cb52e3d170/`. Final PNGs were copied unchanged into this directory. Each is RGBA with alpha extrema 0–255 and 16 isolated silhouettes. Runtime normalization/compositing happens in the renderer, not by rewriting source artwork.

The existing male/base atlas includes mixed-gender base outfits; that original row-major identity order is preserved. Female variants retain the corresponding 16-outfit order. Each source supplies 16 seated or reclining poses; the renderer chooses the same outfit index as standing art.

## people-male-seated-v1.png

Mode: edit, identity-preserve, followed by edit, background-extraction.

Reference: `people-atlas-v1.png`.

Initial output (rejected RGB / baked checkerboard): `exec-6413f437-0a09-41c6-a808-c19ba3096e8f.png`.

Final original copied unchanged: `exec-865714ca-8d09-432d-8c7c-c262ad68ad55.png`.

Full pose prompt:

```text
Use case: identity-preserve game sprite-sheet edit.
Image 1 is the EDIT TARGET and outfit/face identity reference. Change ONLY the physical pose of all 16 people. Keep every individual's face, hairstyle, headwear, skin tone, outfit, gender presentation, colors, row-major order and pixel-art style of the reference exactly recognizable.
Output: a production game sprite atlas with exactly 4 columns and 4 rows, one complete isolated person centered in each equal cell, generous transparent separation. Maintain uniform character scale across cells and the original 16-person order. Genuine transparent alpha background, not a painted checkerboard, not black or white. No ground shadows, no text, no props or furniture, no tools, no grid lines.
Pose for ALL 16: sitting upright, facing south toward the viewer in the existing slightly overhead village-game perspective. Clearly bent hips and knees, thighs foreshortened toward viewer, lower legs down, feet forward. Relaxed hands resting empty on lap/thighs, eyes open. This is a seated body WITHOUT any chair; the game draws the real chair separately. Keep normal head and torso proportions; bent seated legs must make the whole body naturally shorter than standing.
Crisp warm muted pixel-art materials and dark outlines matching the reference. No new characters, weapons, objects, or accessories. Never merge neighboring silhouettes. Do not redesign outfits or replace them with nightclothes.
```

Full alpha-correction prompt (input: the initial output above):

```text
Use case: background-extraction. Image 1 is the edit target: a 4 by 4 pixel-art sprite atlas. Remove ONLY its baked gray-and-white checkerboard background, replacing it with genuine alpha transparency in an RGBA PNG. Preserve all 16 character silhouettes, their exact pose, placement, sizes, faces, skin tones, clothes, outlines, colors and row-major order. Keep the original full canvas and spacing; no cropping, no new background, no black fill, no shadows. Do not redraw or restyle the people. The spaces around and between all characters must be alpha=0, including the small spaces between arms/legs. No checkerboard pixels left in the image.
```

## people-male-reclining-v1.png

Mode: edit, identity-preserve, followed by edit, background-extraction.

Reference: `people-atlas-v1.png`.

Initial output (rejected RGB / baked checkerboard): `exec-157f3780-7b86-4284-bcf9-b59092764ee6.png`.

Final original copied unchanged: `exec-3bb1ff15-aa7e-42f2-955c-dcfccafa49df.png`.

Full pose prompt:

```text
Use case: identity-preserve game sprite-sheet edit.
Image 1 is the EDIT TARGET and outfit/face identity reference. Change ONLY the physical pose of all 16 people. Keep every individual's face, hairstyle, headwear, skin tone, outfit, gender presentation, colors, row-major order and pixel-art style of the reference exactly recognizable.
Output: a production game sprite atlas with exactly 4 columns and 4 rows, one complete isolated person centered in each equal cell, generous transparent separation. Maintain uniform character scale across cells and the original 16-person order. Genuine transparent alpha background, not a painted checkerboard, not black or white. No ground shadows, no text, no props or furniture, no tools, no grid lines.
Pose for ALL 16: lying supine flat on the back, head at the TOP of each cell, feet toward the BOTTOM. Viewed from above, eyes CLOSED, relaxed arms close to body with empty hands resting over abdomen, full clothed body visible. They are sleeping, not standing and not rotated sideways. No bed, pillow, blanket or furniture; the engine draws actual bed and covers separately.
Crisp warm muted pixel-art materials and dark outlines matching the reference. No new characters, weapons, objects, or accessories. Never merge neighboring silhouettes. Do not redesign outfits or replace them with nightclothes.
```

Full alpha-correction prompt (input: the initial output above):

```text
Use case: background-extraction. Image 1 is the edit target: a 4 by 4 pixel-art sprite atlas. Remove ONLY its baked gray-and-white checkerboard background, replacing it with genuine alpha transparency in an RGBA PNG. Preserve all 16 character silhouettes, their exact pose, placement, sizes, faces, skin tones, clothes, outlines, colors and row-major order. Keep the original full canvas and spacing; no cropping, no new background, no black fill, no shadows. Do not redraw or restyle the people. The spaces around and between all characters must be alpha=0, including the small spaces between arms/legs. No checkerboard pixels left in the image.
```

## people-female-seated-v1.png

Mode: edit, identity-preserve, followed by edit, background-extraction.

Reference: `people-female-atlas-v1.png`.

Initial output (rejected RGB / baked checkerboard): `exec-a7f9dea6-7670-4de2-bd32-fc47cdfb9d84.png`.

Final original copied unchanged: `exec-12117ffa-2ba8-4035-8302-6cafdcc414da.png`.

Full pose prompt:

```text
Use case: identity-preserve game sprite-sheet edit.
Image 1 is the EDIT TARGET and outfit/face identity reference. Change ONLY the physical pose of all 16 people. Keep every individual's face, hairstyle, headwear, skin tone, outfit, gender presentation, colors, row-major order and pixel-art style of the reference exactly recognizable.
Output: a production game sprite atlas with exactly 4 columns and 4 rows, one complete isolated person centered in each equal cell, generous transparent separation. Maintain uniform character scale across cells and the original 16-person order. Genuine transparent alpha background, not a painted checkerboard, not black or white. No ground shadows, no text, no props or furniture, no tools, no grid lines.
Pose for ALL 16: sitting upright, facing south toward the viewer in the existing slightly overhead village-game perspective. Clearly bent hips and knees, thighs foreshortened toward viewer, lower legs down, feet forward. Relaxed hands resting empty on lap/thighs, eyes open. This is a seated body WITHOUT any chair; the game draws the real chair separately. Keep normal head and torso proportions; bent seated legs must make the whole body naturally shorter than standing.
Crisp warm muted pixel-art materials and dark outlines matching the reference. No new characters, weapons, objects, or accessories. Never merge neighboring silhouettes. Do not redesign outfits or replace them with nightclothes.
```

Full alpha-correction prompt (input: the initial output above):

```text
Use case: background-extraction. Image 1 is the edit target: a 4 by 4 pixel-art sprite atlas. Remove ONLY its baked gray-and-white checkerboard background, replacing it with genuine alpha transparency in an RGBA PNG. Preserve all 16 character silhouettes, their exact pose, placement, sizes, faces, skin tones, clothes, outlines, colors and row-major order. Keep the original full canvas and spacing; no cropping, no new background, no black fill, no shadows. Do not redraw or restyle the people. The spaces around and between all characters must be alpha=0, including the small spaces between arms/legs. No checkerboard pixels left in the image.
```

## people-female-reclining-v1.png

Mode: edit, identity-preserve, followed by edit, background-extraction.

Reference: `people-female-atlas-v1.png`.

Initial output (rejected RGB / baked checkerboard): `exec-d1b29285-c629-49ad-9a3f-df1424010754.png`.

Final original copied unchanged: `exec-985ff052-03bb-45f4-a711-9bffff85879f.png`.

Full pose prompt:

```text
Use case: identity-preserve game sprite-sheet edit.
Image 1 is the EDIT TARGET and outfit/face identity reference. Change ONLY the physical pose of all 16 people. Keep every individual's face, hairstyle, headwear, skin tone, outfit, gender presentation, colors, row-major order and pixel-art style of the reference exactly recognizable.
Output: a production game sprite atlas with exactly 4 columns and 4 rows, one complete isolated person centered in each equal cell, generous transparent separation. Maintain uniform character scale across cells and the original 16-person order. Genuine transparent alpha background, not a painted checkerboard, not black or white. No ground shadows, no text, no props or furniture, no tools, no grid lines.
Pose for ALL 16: lying supine flat on the back, head at the TOP of each cell, feet toward the BOTTOM. Viewed from above, eyes CLOSED, relaxed arms close to body with empty hands resting over abdomen, full clothed body visible. They are sleeping, not standing and not rotated sideways. No bed, pillow, blanket or furniture; the engine draws actual bed and covers separately.
Crisp warm muted pixel-art materials and dark outlines matching the reference. No new characters, weapons, objects, or accessories. Never merge neighboring silhouettes. Do not redesign outfits or replace them with nightclothes.
```

Full alpha-correction prompt (input: the initial output above):

```text
Use case: background-extraction. Image 1 is the edit target: a 4 by 4 pixel-art sprite atlas. Remove ONLY its baked gray-and-white checkerboard background, replacing it with genuine alpha transparency in an RGBA PNG. Preserve all 16 character silhouettes, their exact pose, placement, sizes, faces, skin tones, clothes, outlines, colors and row-major order. Keep the original full canvas and spacing; no cropping, no new background, no black fill, no shadows. Do not redraw or restyle the people. The spaces around and between all characters must be alpha=0, including the small spaces between arms/legs. No checkerboard pixels left in the image.
```

## Runtime contract

Seated sheets contain bodies only, never invented chairs. Reclining sheets contain bodies only, never new beds or blankets. The renderer requires actual sitting/sleep state and valid real furniture, then composites the original fixture foreground over the body. The illustration does not create or relocate simulation objects, change equipment, occupy tiles, or alter schedules. The shipped furniture faces south; directional furniture placement is a future extension.

Player sleep currently advances time synchronously and ends before the next frame; this art pass deliberately does not change that gameplay. NPC sustained sleep can show a bed pose. Macro-suspended NPCs marked render_disabled are hidden, not drawn asleep.
