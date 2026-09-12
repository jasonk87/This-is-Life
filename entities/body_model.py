"""Persistent anatomy rules, in game units (not a medical/physics model).

The state lives on the existing Anatomy component. Wounds are the authority;
HP is only a compatibility projection. These functions do not call the world,
draw sprites, roll random numbers, or manufacture inventory.
"""

from dataclasses import dataclass, field
import math

from config import DAY_LENGTH_TICKS as DAY
from entities.pickle_compat import dataclass_setstate


@dataclass
class Scar:
    source_wound_id: int
    part: str
    kind: str
    severity: float
    formed_tick: int
    weapon: str | None = None

    def __setstate__(self, state):
        dataclass_setstate(self, state)


@dataclass
class Wound:
    id: int
    part: str
    kind: str
    damage: dict
    created_tick: int
    attacker_id: int | str | None = None
    weapon: str | None = None
    healing: float = 0.0
    bleeding: float = 0.0
    dressed: bool = False
    splinted: bool = False
    fracture: bool = False
    permanent: dict = field(default_factory=dict)
    dressing_quality: float = 0.5
    splint_quality: float = 0.5
    treated_by: int | str | None = None

    def __setstate__(self, state):
        dataclass_setstate(self, state)


def plan_nodes(plan):
    """name -> (parent, coverage slot, hit weight, function). Shared tissue rules."""
    nodes = {
        "torso": (None,"body",6,"breathing"),
        "neck": ("torso",None,1,"consciousness"),
        "head": ("neck","head",2,"sight"),
    }
    if plan == "wolf":
        nodes["jaws"] = ("head",None,1,"bite")
        nodes["tail"] = ("torso",None,1,None)
        for side in ("left","right"):
            for end in ("front","hind"):
                root = f"{side}_{end}_leg"
                lower,paw = f"{side}_{end}_lower_leg",f"{side}_{end}_paw"
                nodes[root] = ("torso",None,2,"movement")
                nodes[lower] = (root,None,2,"movement")
                nodes[paw] = (lower,None,1,"movement")
    else:
        for side in ("left","right"):
            # Preserve existing upper-limb IDs for old saves and API consumers.
            nodes[f"{side}_arm"] = ("torso","body",2,"grip")
            nodes[f"{side}_forearm"] = (f"{side}_arm","body",2,"grip")
            nodes[f"{side}_hand"] = (f"{side}_forearm","hands",1,"grip")
            nodes[f"{side}_leg"] = ("torso","legs",3,"movement")
            nodes[f"{side}_lower_leg"] = (f"{side}_leg","legs",2,"movement")
            nodes[f"{side}_foot"] = (f"{side}_lower_leg","feet",1,"movement")
    return nodes


def upgrade(body, plan="human", now=0):
    """Idempotent migration of the old six HP pools, without healing or RNG."""
    if body.body_plan == plan:
        return body
    from entities.anatomy import BodyPart
    old = {key:(part.hp,part.max_hp,list(part.status_effects)) for key,part in body.parts.items()}
    total_max = body.get_total_max_hp()
    total_hp = body.get_total_hp()
    body.display_max_hp = max(1,total_max)
    body.systemic_loss = max(0.0,1-total_hp/body.display_max_hp)
    body.body_plan = plan
    body.parts = {}
    for name,(parent,coverage,weight,function) in plan_nodes(plan).items():
        previous = old.get(name)
        capacity = previous[1] if previous else max(1,weight)
        part = BodyPart(name,capacity,capacity,parent=parent,coverage=coverage,
                        hit_weight=weight,function=function,
                        tissues=("skin","muscle","bone","vital") if name in {"head","neck","torso"}
                        else ("skin","muscle","bone"))
        body.parts[name] = part
        if previous and (previous[0]<previous[1] or "broken" in previous[2]):
            severity = max(0,1-previous[0]/max(1,previous[1]))
            # Preserve known legacy impairment, but don't invent a severed
            # artery/brain wound that instantly kills an otherwise living save.
            broken = "broken" in previous[2] or (previous[0] <= 0 and function == "movement")
            damage = {"skin":severity*.2,"muscle":severity*.6,"bone":.65 if broken else 0}
            body.wounds.append(Wound(body.next_wound_id,name,"legacy injury",damage,now,fracture=broken))
            body.next_wound_id += 1
    body.last_body_tick = now
    return body


def tissue_damage(body, name):
    result = {layer:0.0 for layer in body.parts[name].tissues}
    for wound in body.wounds:
        if wound.part != name:
            continue
        for layer,severity in wound.damage.items():
            result[layer] = min(1.0,result.get(layer,0)+severity*(1-wound.healing)
                                +wound.permanent.get(layer,0)*wound.healing)
    return result


def part_function(body, name):
    if name not in body.parts:
        return 0.0
    if not body.wounds:
        return 1.0
    damage = tissue_damage(body,name)
    muscle,bone = damage.get("muscle",0),damage.get("bone",0)
    own = max(0,1-muscle*.75-bone*.9)
    if muscle>=.98 or bone>=.95:
        own = 0.0
    elif bone>=.45:
        own = min(own,.35)
    parent = body.parts[name].parent
    return min(own,part_function(body,parent)) if parent else own


def pain(body):
    return min(1.0,sum((w.damage.get("skin",0)*.08+w.damage.get("muscle",0)*.22
                       +w.damage.get("bone",0)*.30)*(1-w.healing) for w in body.wounds))


def capabilities(body):
    if not body.body_plan:
        return dict(movement=1.0,grip=1.0,sight=1.0,breathing=1.0,consciousness=1.0,bite=1.0)
    if not body.wounds and body.blood == 1 and body.systemic_loss == 0 and not body.death_cause:
        return dict(movement=1.0, grip=1.0 if body.body_plan == "human" else 0.0,
                    sight=1.0, breathing=1.0, consciousness=1.0, bite=1.0 if body.body_plan == "wolf" else 0.0)
    blood = body.blood
    consciousness = min(max(0,(blood-.30)/.45),
                        1-tissue_damage(body,"head").get("vital",0),
                        1-tissue_damage(body,"neck").get("vital",0),
                        1-body.systemic_loss)
    if pain(body)>=.92 or body.death_cause:
        consciousness = 0.0
    feet = [name for name in body.parts if name.endswith(("_paw","_foot"))]
    hands = [name for name in body.parts if name.endswith("_hand")]
    movement = sum(part_function(body,n) for n in feet)/max(1,len(feet))
    grip = sum(part_function(body,n) for n in hands)/max(1,len(hands)) if hands else 0.0
    fatigue = max(.1,1-pain(body)*.5)*min(1,blood/.8)
    if consciousness<.2:
        movement = grip = 0.0
    return dict(movement=movement*fatigue,grip=grip*fatigue,
                sight=part_function(body,"head")*consciousness,
                breathing=1-tissue_damage(body,"torso").get("vital",0),
                consciousness=consciousness,bite=part_function(body,"jaws") if "jaws" in body.parts else 0.0)


def health_fraction(body):
    if body.death_cause:
        return 0.0
    if not body.wounds:
        return max(0, min(body.blood, 1-body.systemic_loss))
    total_weight = sum(p.hit_weight for p in body.parts.values())
    structural = sum(sum(tissue_damage(body,n).values())/len(p.tissues)*p.hit_weight
                     for n,p in body.parts.items())/max(1,total_weight)
    return max(0,min(body.blood,1-body.systemic_loss,1-structural))


def inflict(body, part, kind, force, now, attacker_id=None, weapon=None):
    """Layer-specific injury; no overflow into unrelated body regions."""
    if part not in body.parts or force<=0 or body.death_cause:
        return None
    force = min(80.0,max(0.0,float(force)))
    existing = tissue_damage(body, part)
    # Ruptured outer tissue no longer offers intact protection to every later
    # hit. A series of ordinary axe cuts can reach bone/vitals in that region.
    penetration = force + existing.get("skin", 0)*2 + existing.get("muscle", 0)*5 + existing.get("bone", 0)*3
    if kind in {"cut","puncture"}:
        sharp = kind=="cut"
        damage = dict(skin=force*(.095 if sharp else .065),
                      muscle=max(0,penetration-1)*(.048 if sharp else .040),
                      bone=max(0,penetration-6)*(.025 if sharp else .019),
                      vital=max(0,penetration-9)*(.035 if sharp else .050))
    else:
        damage = dict(skin=force*.018,muscle=penetration*.032,bone=penetration*.044,
                      vital=max(0,penetration-9)*.04)
    damage = {layer:min(1.0,damage[layer]) for layer in body.parts[part].tissues}
    bleeding = (damage.get("skin",0)*.0006+damage.get("muscle",0)*.0012
                +damage.get("vital",0)*.003) if kind in {"cut","puncture"} else damage.get("vital",0)*.002
    wound = Wound(body.next_wound_id,part,kind,damage,now,attacker_id,weapon,
                  bleeding=bleeding,
                  permanent={k:v*.18 for k,v in damage.items() if k in {"bone","vital"} and v>=.85})
    body.next_wound_id += 1
    body.wounds.append(wound)
    if tissue_damage(body, part).get("bone", 0) >= .45:
        for injury in body.wounds:
            if injury.part == part and injury.damage.get("bone", 0) > 0 and injury.healing < 1:
                injury.fracture = True
    assess_death(body)
    return wound


def assess_death(body):
    if body.death_cause:
        return body.death_cause
    if body.blood<=.18:
        body.death_cause = "blood loss"
    elif body.systemic_loss>=1:
        body.death_cause = "systemic collapse"
    else:
        for name in ("head","neck","torso"):
            damage = tissue_damage(body,name)
            if damage.get("vital",0)>=.85:
                body.death_cause = f"catastrophic {name} injury"
                break
    return body.death_cause


def dressing_multiplier(wound):
    return .025 - .020 * max(0, min(1, wound.dressing_quality)) if wound.dressed else 1.0


def bleeding_rate(body, now):
    return sum(w.bleeding*(1-w.healing)**2*dressing_multiplier(w)
               *(.35 if w.damage.get("vital",0)>.05 or w.damage.get("muscle",0)>.7
                 else math.exp(-max(0,now-w.created_tick)/180)) for w in body.wounds)


def advance(body, now, resting=False, nourishment=1.0):
    """Saved high-water clock: idempotent paused draws, safe rewinds/time jumps."""
    if body.last_body_tick is None:
        body.last_body_tick = now
        return
    if now<=body.last_body_tick or body.death_cause:
        return
    start,dt = body.last_body_tick,now-body.last_body_tick
    body.last_body_tick = now
    loss = 0.0
    for wound in body.wounds:
        deep = wound.damage.get("vital",0)>.05 or wound.damage.get("muscle",0)>.7
        interval = dt*.35 if deep else 180*(math.exp(-max(0,start-wound.created_tick)/180)
                                                -math.exp(-max(0,now-wound.created_tick)/180))
        loss += wound.bleeding*(1-wound.healing)**2*dressing_multiplier(wound)*interval
    body.blood = max(0,body.blood-loss)
    # Evaluate blood loss BEFORE regeneration; a huge sleep/time jump cannot
    # let a person bleed out and subsequently regenerate into being alive.
    if assess_death(body):
        return
    if bleeding_rate(body,now)<.00003:
        # Blood is a persistent circulating reserve, not a night's energy bar.
        # Large losses take several supplied rest days, never a 35-point refill.
        rate = .08 if resting else .04
        body.blood = min(1,body.blood+dt/DAY*rate*max(.2, min(1, nourishment)))
    for wound in body.wounds:
        fracture = wound.fracture
        days = 18 if fracture else 4 if wound.damage.get("muscle",0)>.3 else 2
        rate = (1.35 if resting else .65)*(1+.4*wound.dressing_quality if wound.dressed else 1)
        rate *= max(.2, min(1, nourishment))
        if fracture and not wound.splinted:
            rate *= .2
        elif fracture:
            rate *= .75 + .5*wound.splint_quality
        wound.healing = min(1,wound.healing+dt/(DAY*days)*rate)
        if (wound.healing >= 1 and wound.kind in {"cut", "puncture", "legacy injury"}
                and wound.damage.get("skin", 0) >= .2
                and not any(s.source_wound_id == wound.id for s in body.scars)):
            body.scars.append(Scar(wound.id, wound.part, wound.kind,
                                   wound.damage["skin"], now, wound.weapon))
    # Retain a bounded resolved history; active injuries are never discarded.
    resolved = [w for w in body.wounds if w.healing>=1 and not w.permanent]
    discard = {w.id for w in resolved[:-32]}
    body.wounds[:] = [w for w in body.wounds if w.id not in discard]


def wounds_summary(body):
    if not body.body_plan:
        return ["No detailed body examination recorded yet."]
    cap = capabilities(body)
    lines = [f"Blood {body.blood:.0%} | Pain {pain(body):.0%}",
             f"Movement {cap['movement']:.0%} | Grip {cap['grip']:.0%}",
             "Unconscious" if cap["consciousness"]<.2 else "Conscious"]
    for wound in body.wounds:
        if wound.healing>=1 and not wound.permanent:
            continue
        fracture = wound.fracture
        state = "splinted" if fracture and wound.splinted else "fracture" if fracture else wound.kind
        lines.append(f"{wound.part.replace('_',' ')}: {state}; {wound.healing:.0%} healed"
                     +(" / dressed" if wound.dressed else "")+(" / lasting damage" if wound.permanent else ""))
    return lines if len(lines)>3 else lines+["No active wounds."]
