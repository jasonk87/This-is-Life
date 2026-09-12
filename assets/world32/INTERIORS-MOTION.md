# Interior and directional source assets

Generated September 12, 2026 using the **imagegen skill** and built-in image-generation tool. Furniture used generation mode; directional people and background corrections used edit mode. No external image API, CLI generation, or purchased pack was used.

All five PNGs are unchanged copies of final tool outputs. Sources remain in `C:/Users/Owner/.codex/generated_images/01a070e9-0377-7c90-b524-08cb52e3d170/`. Every final PNG was visually inspected and verified to contain real transparent alpha. The four initial direction edits had baked checkerboards and were rejected. No rejected version is shipped.

## File provenance

- `interiors-atlas-v1.png`: original `exec-89b86fb3-b271-4499-b089-3952e832f4b2.png`. New generation; no reference.
- `people-male-north-v1.png`: original `exec-27002b9e-364f-40e4-b295-ae45ec8fae20.png`. Edit of people-atlas-v1.png, then alpha correction of exec-1e058830-feec-4288-991d-312f87f5fdb3.png.
- `people-male-east-v1.png`: original `exec-552570ab-e72e-4cd0-8dc9-568c22b85a8d.png`. Edit of people-atlas-v1.png, then alpha correction of exec-4cbf09f4-31fc-4769-be35-eb5741bd7330.png.
- `people-female-north-v1.png`: original `exec-a1cc5486-bf2d-47ef-bccb-779e2a46bdb2.png`. Edit of people-female-atlas-v1.png, then alpha correction of exec-49badaa3-bf14-4e4e-9bbb-e2762b403aa1.png.
- `people-female-east-v1.png`: original `exec-0aa479fa-1767-45a0-b281-7ce4234488ac.png`. Edit of people-female-atlas-v1.png, then alpha correction of exec-c20c6f94-b5ff-4ad7-8d7a-063db5125154.png.

## Runtime use

Furniture atlas row-major indices: timber bed, straw bed, empty table, chair; closed chest, empty shelf, bookshelf, cupboard; workbench, cold forge, cold oven, anvil; cold fireplace, loom, stool, noticeboard.

The atlas is source artwork, not permission to place objects. Only recognized existing decoration definitions are drawn. Oven, cupboard and stool artwork is reserved: no matching placed decoration is invented. In particular bakery work-zone standing tiles stay clear. No simulation fixtures, stock, collision or ownership are added.

Direction sheets keep the 16 outfit indices from the front-view sheets (female offset +16). North and east supply 32 poses each; west mirrors east in memory, south retains the original art. The `male` filename names the base sheet, which already includes several women; it is not a claim about every figure's gender.

These are high-resolution generated sheets normalized in renderer memory, not hand-authored 32px sprite sources. Connected-component slicing keeps table legs/bellows crossing gutters intact. Normalized people remain 32×48; furniture uses 26–42px width and 28–48px height at a 32px logical tile. Nearest-neighbor scaling, limb offsets and four-phase poses happen only at runtime. Full bespoke directional action cycles and complete trait-accurate appearance remain future work.

## Exact furniture prompt

Use case: stylized-concept. Asset type: production medieval 2D game furniture sprite atlas, transparent RGBA PNG.
Create exactly sixteen separate furniture objects on an evenly spaced 4 by 4 grid. Each cell is an equal square, every object fully inside its own cell with generous transparent margins, no overlap. High-quality restrained pixel art matching a warm timber, muted olive, slate, cream and russet medieval village RPG. Consistent 3/4 top-down camera: see the top surface and front face, vertical sides upright, NOT isometric diamond projection. Upper-left light. Crisp dark outlines and restrained 3-tone clustered shading, readable when normalized to 32-48 pixels. No floor tiles or ground shadows. Genuine transparent alpha background; NO drawn checkerboard.
Row1 left to right: single timber bed with cream pillow and muted teal blanket, headboard at top; modest straw pallet bed with ochre blanket; sturdy empty rectangular oak table; single oak chair with clearly visible backrest and seat.
Row2: closed iron-banded wooden chest with small central latch; empty two-tier wall shelf, no stock; freestanding wooden bookshelf with books; empty waist-high wooden cupboard with paneled doors.
Row3: carpenter workbench with built-in vise but NO loose tools; cold unlit stone forge with dark open hearth and attached bellows; cold unlit brick bread oven with arched mouth and small chimney; dark iron anvil on stout oak stump.
Row4: stone fireplace with cold dark firebox and chimney surround, no flames; wooden weaving loom with neutral linen warp; round wooden stool; simple wooden noticeboard with a few blank cream parchment sheets.
All objects use the same coherent scale, camera and palette. No people, food, drink, miscellaneous inventory, flames, smoke, lettering, numbers, labels, grid lines, watermarks, logos or surrounding room. These are individual usable game sprites, NOT a scene or concept-board. No baked lighting effects outside silhouettes.

## Exact male-north edit prompt

Reference: `people-atlas-v1.png`.

Use case: identity-preserve. Edit this medieval pixel-art character atlas into a matching NORTH-facing BACK view atlas for the same 16 characters.
Preserve EXACTLY the 4 by 4 equal grid, row-major character order, clothing colors and design, age, sex, skin tone, hair color, hats, belts, apron, coat and every character's identity. Do not change anyone's job outfit. This is a production animation direction sheet, not new character designs.
Every character must face away from the viewer toward the TOP of the image: back of head and back of clothing visible, NO eyes or front of face visible. Keep the same elevated 3/4 top-down RPG camera and upper-left lighting. Full body visible, feet on exactly the same baseline in each cell, upright relaxed neutral pose, both empty hands at sides. Preserve the common scale and padding of the reference. Crisp pixel clusters and dark outlines, matching original restrained medieval palette. All sixteen isolated silhouettes, no floor or shadow. True transparent alpha background, never a drawn checkerboard. No labels, lettering, grid lines, props, weapons, sacks, extra characters or watermark. Output a square RGBA PNG.

## Exact male-east edit prompt

Reference: `people-atlas-v1.png`.

Use case: identity-preserve. Edit this medieval pixel-art character atlas into a matching EAST-facing RIGHT PROFILE view atlas for the same 16 characters.
Preserve EXACTLY the 4 by 4 equal grid, row-major character order, clothing colors and design, age, sex, skin tone, hair color, hats, belts, apron, coat and every character's identity. Do not change anyone's job outfit. This is a production animation direction sheet, not new character designs.
Every character must face to the RIGHT of the image: genuine right-facing body profile with nose, chest and toes directed RIGHT, not a horizontally flipped front pose. Keep the same elevated 3/4 top-down RPG camera and upper-left lighting. Full body visible, feet on exactly the same baseline in each cell, upright relaxed neutral pose, both empty hands at sides. Preserve the common scale and padding of the reference. Crisp pixel clusters and dark outlines, matching original restrained medieval palette. All sixteen isolated silhouettes, no floor or shadow. True transparent alpha background, never a drawn checkerboard. No labels, lettering, grid lines, props, weapons, sacks, extra characters or watermark. Output a square RGBA PNG.

## Exact female-north edit prompt

Reference: `people-female-atlas-v1.png`.

Use case: identity-preserve. Edit this medieval pixel-art character atlas into a matching NORTH-facing BACK view atlas for the same 16 characters.
Preserve EXACTLY the 4 by 4 equal grid, row-major character order, clothing colors and design, age, sex, skin tone, hair color, hats, belts, apron, coat and every character's identity. Do not change anyone's job outfit. This is a production animation direction sheet, not new character designs.
Every character must face away from the viewer toward the TOP of the image: back of head and back of clothing visible, NO eyes or front of face visible. Keep the same elevated 3/4 top-down RPG camera and upper-left lighting. Full body visible, feet on exactly the same baseline in each cell, upright relaxed neutral pose, both empty hands at sides. Preserve the common scale and padding of the reference. Crisp pixel clusters and dark outlines, matching original restrained medieval palette. All sixteen isolated silhouettes, no floor or shadow. True transparent alpha background, never a drawn checkerboard. No labels, lettering, grid lines, props, weapons, sacks, extra characters or watermark. Output a square RGBA PNG.

## Exact female-east edit prompt

Reference: `people-female-atlas-v1.png`.

Use case: identity-preserve. Edit this medieval pixel-art character atlas into a matching EAST-facing RIGHT PROFILE view atlas for the same 16 characters.
Preserve EXACTLY the 4 by 4 equal grid, row-major character order, clothing colors and design, age, sex, skin tone, hair color, hats, belts, apron, coat and every character's identity. Do not change anyone's job outfit. This is a production animation direction sheet, not new character designs.
Every character must face to the RIGHT of the image: genuine right-facing body profile with nose, chest and toes directed RIGHT, not a horizontally flipped front pose. Keep the same elevated 3/4 top-down RPG camera and upper-left lighting. Full body visible, feet on exactly the same baseline in each cell, upright relaxed neutral pose, both empty hands at sides. Preserve the common scale and padding of the reference. Crisp pixel clusters and dark outlines, matching original restrained medieval palette. All sixteen isolated silhouettes, no floor or shadow. True transparent alpha background, never a drawn checkerboard. No labels, lettering, grid lines, props, weapons, sacks, extra characters or watermark. Output a square RGBA PNG.

## Exact alpha-correction prompt (all four direction sheets)

Reference: corresponding rejected opaque direction sheet listed above.

Use case: background-extraction. Remove the baked checkerboard background completely from this 4x4 character sprite atlas. Keep all 16 characters exactly unchanged: preserve pixels, poses, facing direction, clothes, colors, sizes, positions and grid layout. Change ONLY the background into real transparent alpha, including gaps between arms and legs. Output an RGBA PNG with alpha=0 outside the figures. Do not draw a checkerboard or replace it with a solid color. No shadows, text or added details. This is a production transparent game sprite sheet.
