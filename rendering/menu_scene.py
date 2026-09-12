"""Title-screen diorama composed from the game's own pixel art."""
from types import SimpleNamespace
from data.dawnlike import WORLD_TILE_SPRITES, HUMAN_SPRITES, TREE_SPRITES
from rendering.terrain_art import terrain_codepoint


def draw_village_vignette(console):
    from rendering.console_renderer import _draw_zoomed_sprite
    world = SimpleNamespace(zoom_levels=(2.0,), zoom_index=0)
    left = (console.width-72)//2
    top = console.height-18

    def tile(x,y,cp,tint=(204,216,184)):
        if cp is not None:
            sx,sy=left+x*2,top+y*2
            _draw_zoomed_sprite(console,world,(sx,sy,sx+1,sy+1),cp,fg=tint)

    for y in range(6):
        for x in range(36):
            material="road" if y==4 else "plains"
            tile(x,y,terrain_codepoint(material,x,y),(140,163,138))
    for x,y in [(0,1),(2,2),(3,0),(5,2),(29,0),(32,1),(34,2),(35,0),(30,5)]:
        tile(x,y,TREE_SPRITES["oak_tree"])
    for start in (8,19):
        for y in range(4):
            for x in range(start,start+7):
                wall = y in (0,3) or x in (start,start+6)
                cp=terrain_codepoint("wood_wall" if wall else "wood_floor",x,y)
                if y==3 and x==start+3:
                    cp=WORLD_TILE_SPRITES["door"]
                tile(x,y,cp)
    for x,y,role in [(12,4,"farmer"),(17,3,"merchant"),(24,4,"woodcutter"),(28,4,"female_commoner")]:
        tile(x,y,HUMAN_SPRITES[role],(235,228,203))
