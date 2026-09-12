"""Presentation-only joint poses and textured limbs for the modular character.

Coordinates are in one shared rig space. Clothes follow the same bones as the
body; hand sockets also place carried/held objects. No simulation writes here.
"""

from dataclasses import dataclass
from functools import lru_cache
import math

from runtime_compat import np


@dataclass(frozen=True)
class Pose:
    size: tuple
    head: tuple
    chest: tuple
    waist: tuple
    shoulders: tuple
    elbows: tuple
    hands: tuple
    hips: tuple
    knees: tuple
    ankles: tuple
    seated: bool = False
    reclined: bool = False


@lru_cache(maxsize=256)
def layout(direction, kind="idle", phase=0, posture=None, moving=False):
    phase %= 4
    side = direction in {"east", "west"}
    sign = -1 if direction == "west" else 1
    seated = posture == "seated"
    reclined = posture == "reclining" or kind in {"sleep", "dead", "unconscious"}
    if reclined:
        return Pose((64, 62), (32, 2), (32, 25), (32, 38),
                    ((22, 26), (42, 26)), ((19, 34), (45, 34)), ((26, 38), (38, 38)),
                    ((27, 38), (37, 38)), ((26, 45), (38, 45)), ((25, 54), (39, 54)),
                    reclined=True)
    bob = int(not seated and phase in (1, 3) and (moving or kind == "idle"))
    head = (32, 0 if seated else 3+bob)
    chest, waist = (32, 26 if seated else 29+bob), (32, 44 if seated else 50+bob)
    shoulders = ((22, chest[1]+3), (42, chest[1]+3))
    elbows = ((18, chest[1]+13), (46, chest[1]+13))
    hands = ((18, chest[1]+22), (46, chest[1]+22))
    hips = ((26, waist[1]), (38, waist[1]))
    knees = ((20, 51), (44, 51)) if seated else ((26, 62), (38, 62))
    ankles = ((20, 60), (44, 60)) if seated else ((26, 74), (38, 74))
    if seated:
        elbows, hands = ((18, 39), (46, 39)), ((24, 46), (40, 46))
    if side:
        shoulders = ((29, chest[1]+3), (35, chest[1]+3))
        elbows = ((28+sign*2, chest[1]+13), (35+sign*2, chest[1]+13))
        hands = ((28+sign*3, chest[1]+22), (35+sign*3, chest[1]+22))
        hips = ((30, waist[1]), (34, waist[1]))
        knees = ((30+sign*12, 48), (34+sign*12, 50)) if seated else ((30, 62), (34, 62))
        ankles = ((30+sign*12, 60), (34+sign*12, 61)) if seated else ((30, 73), (34, 75))
        if seated:
            elbows = ((28+sign*3, 39), (35+sign*3, 39))
            hands = ((30+sign*10, 44), (34+sign*10, 45))
    if moving and not seated:
        stride = (0, 4, 0, -4)[phase]
        if side:
            knees = ((30+stride, 62), (34-stride, 62))
            ankles = ((30+stride*2, 74-abs(stride)//2), (34-stride*2, 74))
        else:
            knees = ((26, 62+stride//2), (38, 62-stride//2))
            ankles = ((26, 74+stride//2), (38, 74-stride//2))
        hands = ((hands[0][0],hands[0][1]-stride), (hands[1][0],hands[1][1]+stride))
    # Intent is independent of gait: carrying while walking keeps a real grip.
    if kind == "carry":
        hands = ((24, chest[1]+12), (40, chest[1]+12))
        elbows = ((17, chest[1]+12), (47, chest[1]+12))
        if side:
            hands = ((32+sign*14, chest[1]+11), (32+sign*15, chest[1]+16))
            elbows = ((29+sign*4, chest[1]+14), (35+sign*5, chest[1]+18))
    elif kind in {"hammer", "chop", "fight"}:
        heights = (chest[1]+9, chest[1]-13, chest[1]+10, chest[1]+17)
        target = (32+sign*18, heights[phase])
        hands = (hands[0], target)
        elbows = (elbows[0], (32+sign*13, (chest[1]+target[1])//2))
        if kind == "chop":
            hands = ((target[0]-sign*3,target[1]+5), target)
            elbows = ((32+sign*5,chest[1]+4),elbows[1])
    elif kind == "prepare":
        hands = ((26, chest[1]+14+phase%2*3), (39, chest[1]+14+(1-phase%2)*3))
        elbows = ((18, chest[1]+12), (46, chest[1]+12))
        if side:
            hands = ((32+sign*14,chest[1]+15+phase%2*3),
                     (32+sign*18,chest[1]+17+(1-phase%2)*3))
    elif kind == "eat":
        hands = (hands[0], (34 if not side else 32+sign*9, chest[1]-7 if phase%2 else chest[1]+13))
        elbows = (elbows[0],(44 if not side else 32+sign*13,chest[1]+5))
    elif kind == "talk":
        hands = (hands[0], (49 if not side else 32+sign*17, chest[1]+5+phase%2*5))
        elbows = (elbows[0], (46 if not side else 32+sign*8,chest[1]+13))
    return Pose((64,68 if seated else 80), head, chest, waist, shoulders, elbows,
                hands, hips, knees, ankles, seated=seated)


def segment(canvas, texture, start, end, width):
    """Nearest-neighbor texture skinning along a bone, with no PNG rewriting."""
    from rendering.character_layers import over
    dx,dy=end[0]-start[0],end[1]-start[1]
    length=max(1.0,math.hypot(dx,dy))
    ux,uy=dx/length,dy/length
    pad=width/2+2
    x0=max(0,int(min(start[0],end[0])-pad))
    y0=max(0,int(min(start[1],end[1])-pad))
    x1=min(canvas.shape[1],int(max(start[0],end[0])+pad+1))
    y1=min(canvas.shape[0],int(max(start[1],end[1])+pad+1))
    if x0>=x1 or y0>=y1: return
    yy,xx=np.mgrid[y0:y1,x0:x1]
    along=(xx-start[0])*ux+(yy-start[1])*uy
    across=(xx-start[0])*uy-(yy-start[1])*ux
    valid=(along>=-1)&(along<=length+1)&(np.abs(across)<width/2)
    sx=np.clip(((across/width+.5)*texture.shape[1]).astype(int),0,texture.shape[1]-1)
    sy=np.clip((along/length*(texture.shape[0]-1)).astype(int),0,texture.shape[0]-1)
    layer=texture[sy,sx].copy()
    # Near-opaque source cores must really occlude a load held behind the back;
    # preserve only genuine edge antialiasing, not a uniform 253-alpha matte.
    layer[:,:,3][layer[:,:,3]>240]=255
    layer[:,:,3][~valid]=0
    over(canvas,layer,x0,y0)


def skin_hand(canvas, point, color):
    from rendering.village_art import rect
    x,y=round(point[0]),round(point[1])
    shade=tuple(c*2//3 for c in color)
    rect(canvas,x-2,y-1,5,5,shade)
    rect(canvas,x-1,y-1,3,4,color)


def project(point, source_shape, target_shape, floor_rest=False):
    """Map a rig socket into the exact resized/rotated frame used for drawing."""
    x,y=point
    h,w=source_shape[:2]
    if floor_rest:
        x,y=y,w-1-x
        w,h=h,w
    return (round(x*target_shape[1]/w), round(y*target_shape[0]/h))


def active_tool(kind, held):
    # Exact catalog match, not a guess based on profession or an item's name.
    return held if kind == "chop" and held == "axe_stone" else None


@lru_cache(maxsize=1536)
def render(state, direction, kind, phase, posture, moving=False, item=None, held=None):
    from rendering import character_layers as layers, pixel_scene as pixels
    from rendering.village_art import rect
    pose=layout(direction,kind,phase,posture,moving)
    side=direction in {"east","west"}
    d=layers.DIRECTIONS.get(direction,0)
    image=np.zeros((pose.size[1],pose.size[0],4),dtype=np.uint8)
    skin=layers.SKIN.get(state[4],layers.SKIN["medium"])
    top,legs,feet=state[9],state[10],state[11]
    torso_w=(14 if side else 20)+{"slim":-2,"broad":2}.get(state[3],0)
    shirt=layers.part("tops",layers.TOPS.get(top,0)*4+d,29 if not side else 18,25)
    # The cloak's canonical undergarment has linen sleeves. Its baked sleeves
    # must not remain beside the torso when the articulated arms are raised.
    front=layers.part("tops",(0 if top=="fur_cloak" else layers.TOPS.get(top,0))*4,29,25)
    pants=layers.part("lower",layers.LOWER.get(legs,0)*4,22,25)
    boots=layers.part("lower",layers.FOOTWEAR[feet]*4+(d if side else 0),24,12 if feet=="leather_boots" else 7) if feet in layers.FOOTWEAR else None

    # Each thigh, shin and boot follows its own joint, not a shifted lower-body rectangle.
    for i in (0,1):
        texture=pants[:,i*11:(i+1)*11]
        segment(image,texture[3:14],pose.hips[i],pose.knees[i],10 if not side else 8)
        segment(image,texture[14:],pose.knees[i],pose.ankles[i],8 if not side else 7)
        ax,ay=pose.ankles[i]
        if boots is not None:
            foot=boots[:,i*12:(i+1)*12]
            if side: foot=pixels.resize(foot,13,foot.shape[0])
            layers.over(image,foot,ax-foot.shape[1]//2,ay+5-foot.shape[0])
        else:
            rect(image,ax-4,ay,8,4,tuple(c*2//3 for c in skin))
            rect(image,ax-3,ay,6,3,skin)
    segment(image,pants[:6],(32,pose.waist[1]-3),(32,pose.waist[1]+3),22 if not side else 14)

    def arm(i):
        sleeve=front[:,0:7] if i==0 else front[:,-7:]
        segment(image,sleeve[2:13],pose.shoulders[i],pose.elbows[i],7)
        segment(image,sleeve[13:23],pose.elbows[i],pose.hands[i],6)
        skin_hand(image,pose.hands[i],skin)

    # Far arms and north-facing carried objects belong behind the torso.
    back_carry=kind=="carry" and direction=="north"
    if side: arm(0)
    if back_carry:
        _carried(image,item,pose,kind,phase,held)
        arm(0); arm(1)
    torso=shirt[:,3:-3] if side else shirt[:,5:-5]
    segment(image,torso,pose.chest,pose.waist,torso_w)
    if top=="fur_cloak" and "cloak" in layers._parts:
        cloak=layers.part("cloak",d,32,30)
        # Body, shoulder mantle, and sleeves follow separate mounts. The rear
        # cloth strip supplies the profile drape without a second static arm.
        drape=layers.part("cloak",2 if side else d,32,30)[:,8:24]
        segment(image,drape,pose.chest,(32,pose.waist[1]+7),torso_w+2)
        collar=pixels.resize(cloak[:10],torso_w+12,10)
        layers.over(image,collar,32-collar.shape[1]//2,pose.chest[1]-3)
    if held and not active_tool(kind,held) and (pose.reclined or kind in {"carry", "hammer", "chop", "eat", "prepare"}):
        from data.dawnlike import ITEM_SPRITES
        if held in ITEM_SPRITES:
            # Occupied hands leave the actual equipped item at the belt. This
            # changes only its presentation; equipment/inventory stay untouched.
            layers.over(image,pixels.resize(pixels.tile_pixels(ITEM_SPRITES[held]),12,17),
                        pose.waist[0]+(-4 if side else 2),pose.waist[1]-4)
    rect(image,29,pose.chest[1]-5,6,6,skin)
    head=layers.identity_head(state,"south" if pose.reclined else direction,rest=pose.reclined)
    layers.over(image,head,pose.head[0]-head.shape[1]//2,pose.head[1])
    if not back_carry:
        _carried(image,item,pose,kind,phase,held)
        if not side: arm(0)
        arm(1)
    return image


def _carried(image,item,pose,kind,phase,held):
    """Item art is between body and gripping hands. Tools pivot at the wrist."""
    from rendering import character_layers as layers, pixel_scene as pixels
    from rendering.village_art import rect
    from data.dawnlike import ITEM_SPRITES
    if kind=="carry" and item in ITEM_SPRITES:
        cx=(pose.hands[0][0]+pose.hands[1][0])/2
        cy=(pose.hands[0][1]+pose.hands[1][1])/2
        source=pixels.tile_pixels(ITEM_SPRITES[item])
        layers.over(image,pixels.resize(source,20,18),cx-10,cy-13)
    elif active_tool(kind,held):
        wrist=pose.hands[1]
        source=pixels.resize(pixels.tile_pixels(ITEM_SPRITES[held]),15,20)
        if wrist[0]<32: source=source[:,::-1]
        layers.over(image,source,wrist[0]-6,wrist[1]-15)
    elif kind in {"hammer","chop"}:
        # The active action authorizes a tool cue; it never equips an item.
        wrist=pose.hands[1]
        sign=1 if wrist[0]>=32 else -1
        tip=(wrist[0]-sign*7,max(5,wrist[1]-18)) if phase==1 else (wrist[0]+sign*5,wrist[1]-11)
        handle=np.full((12,3,4),(137,93,50,255),dtype=np.uint8)
        segment(image,handle,wrist,tip,3)
        rect(image,tip[0]-5,tip[1]-2,11,5,(165,177,173))
        if kind=="chop": rect(image,tip[0]+(3 if sign>0 else -6),tip[1]-1,4,8,(197,207,194))
    elif not pose.reclined and kind not in {"eat","prepare"} and held in ITEM_SPRITES:
        wrist=pose.hands[1]
        layers.over(image,pixels.resize(pixels.tile_pixels(ITEM_SPRITES[held]),15,20),wrist[0]-6,wrist[1]-15)


def clear():
    render.cache_clear()
    layout.cache_clear()
