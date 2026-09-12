"""Pose-attached marks from persistent wounds, dressings and scars.

No painted assets or random decoration. Covered scars stay hidden; active
wounds can stain the garment over their actual region. Drawing changes no state.
"""
from entities import body_model
from rendering.village_art import rect


def signature(actor, now):
    body = getattr(getattr(actor, "combat", None), "anatomy", None)
    if not body or not body.body_plan:
        return ()
    result = []
    for wound in body.wounds:
        if wound.healing >= 1:
            continue
        stage = "dressed" if wound.dressed else "fresh" if wound.healing < .25 else "healing"
        if wound.kind not in {"cut", "puncture"}:
            stage = "bruise"
        if wound.splinted:
            stage = "splint"
        result.append((wound.id, wound.part, stage, round(wound.damage.get("skin", 0)*4)))
    result.extend((s.source_wound_id, s.part, "scar", max(1, round(s.severity*4))) for s in body.scars)
    for index,slot_name in enumerate(("head","body","legs","feet","hands")):
        ref = getattr(getattr(actor.equipment,slot_name,None),"item_reference",None)
        result.extend((-1-index,part,"stain",max(1,round(amount*4)))
                      for part,amount in sorted(getattr(ref,"blood_stains",{}).items()))
    return tuple(result)


def apply(image, pose, state, direction, marks):
    """Skin-space scars; clothing-space blood/dressings, using the same rig."""
    if not marks:
        return image
    image = image.copy()  # cached clean rig must never acquire somebody's wounds
    # Anatomical left is screen-right when facing the player.
    side_index = {"left": 0 if direction == "north" else 1,
                  "right": 1 if direction == "north" else 0}
    def midpoint(a, b):
        return ((a[0]+b[0])/2, (a[1]+b[1])/2)
    anchors = {"head": (pose.head[0]+4, pose.head[1]+12),
               "neck": (pose.chest[0], pose.chest[1]-3),
               "torso": midpoint(pose.chest, pose.waist)}
    coverage = {"head":state[8], "neck":state[8] in {"hooded_cowl"}, "torso":state[9]}
    for side, i in side_index.items():
        for suffix, point, covered in (
            ("arm", midpoint(pose.shoulders[i],pose.elbows[i]),state[9]),
            ("forearm", midpoint(pose.elbows[i],pose.hands[i]),state[9] not in {None,"leather_jerkin","iron_breastplate"}),
            ("hand",pose.hands[i],state[12]), ("leg",midpoint(pose.hips[i],pose.knees[i]),state[10]),
            ("lower_leg",midpoint(pose.knees[i],pose.ankles[i]),state[10]), ("foot",pose.ankles[i],state[11])):
            anchors[f"{side}_{suffix}"] = point
            coverage[f"{side}_{suffix}"] = covered
    palette = {"fresh":(158,38,32),"healing":(100,52,41),"bruise":(105,70,108),
               "dressed":(211,203,166),"splint":(172,128,75),"scar":(196,140,114),"stain":(109,35,29)}
    for ident, part, stage, severity in marks:
        if part not in anchors or (stage != "stain" and coverage.get(part)):
            continue
        if part == "head" and direction == "north":
            continue  # facial mark must not jump onto the back of the skull
        x,y = anchors[part]
        x,y = round(x)+(ident%3-1),round(y)
        width = 5 if stage in {"dressed","splint"} else 2+min(3,severity)
        h = 5 if stage == "splint" else 2
        # Respect the composed silhouette instead of marking empty space.
        alpha = image[:,:,3].copy()
        rect(image,x-width//2,y,width,h,palette[stage])
        if stage == "fresh":
            rect(image,x,y+2,2,2,(104,30,29))
        image[:,:,3] = alpha
    return image


def visible_condition(entity, now):
    body = getattr(getattr(entity,"combat",None),"anatomy",None)
    if not body or not body.body_plan or getattr(entity.physical,"is_dead",False):
        return None
    caps = body_model.capabilities(body)
    if caps["consciousness"] < .2:
        return "Unconscious"
    if body_model.bleeding_rate(body,now) > .00003:
        return "Bleeding"
    if caps["movement"] < .7:
        return "Limping"
    return None
