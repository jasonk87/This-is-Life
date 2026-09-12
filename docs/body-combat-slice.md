# Persistent bodies: first human / wolf slice

## Play it

Restart the game to load the code/configuration changes. Models are disabled by
default in `config.py`, including the independent gossip/chronicle transport.
World generation, combat and background simulation make no model requests.
Optional model prose is replaced by the existing local fallbacks.

- In the bag (`U`), use a melee weapon to equip its actual item instance.
  Merely carrying an axe no longer equips it implicitly.
- Beside a human or wolf, use **Attack**, **Punch**, or **Kick** in the interaction
  menu. Attack uses the held weapon, otherwise a punch; wolves use jaws.
  Recovery takes simulation ticks, so repeated clicks on one paused tick do not
  grant unlimited attacks.
- `F` opens a visible-target combat picker; `Tab` cycles people/creatures,
  arrows choose the action, and `Enter` or `F` commits it. Paused attacks advance
  real world ticks through recovery, including opponent turns. Selecting a
  target is not an attack and does not advance time.
- **Examine Wounds** opens a scrollable body panel. For yourself, press `I`, then
  `B`. It shows blood, pain, function, wound IDs, tissue damage and recovery.
- Craft bandages from cloth and splints from cloth plus a wooden plank. Use
  them from the bag on yourself, or **Treat Wounds** beside someone else.
  `T` in the body panel treats using available supplies and advances ten real
  world ticks. Bag/context treatment uses the same time cost.
- Healers can treat nearby injured people, including the player. They consume
  their supplies, can craft from owned materials, and can fetch their clinic's
  stock. Paying a healer does not manufacture medical supplies.

## Architecture

The existing `Anatomy` component remains the single body owner. It contains the
body plan, persistent wounds, blood reserve and saved simulation clocks.
`entities/body_model.py` contains pure anatomy rules; `body_combat.py` connects
them to the world, inventory, medicine, movement and social consequences.

Humans have 15 connected regions (the legacy arm/leg IDs represent upper limbs).
Wolves have 17, including jaws, four leg chains and a tail. Both use skin,
muscle and bone, with a first-pass vital layer in head, neck and torso. Damaging
a parent impairs dependent parts. Repeated attacks into ruptured tissue can
penetrate deeper; damage never spills arbitrarily into unrelated regions.

Attacks use local dice, skill, functional attacking limbs, range, terrain
occlusion and the actual equipped item. Armor absorbs force only on covered
regions; only struck armor wears. A breastplate does not protect a calf.
Compatibility ranged weapons retain their existing range, but this is not a
new projectile/ammunition simulation.

Bleeding, pain, fractures, tissue recovery and lasting impairment are persistent
state. Movement uses fractional budgets so a 40% movement capability really
moves more slowly. Timed chopping, building and workshop interactions likewise
retain fractional progress. Incapacitation stops movement, attacks, active
interactions, ordinary activity advancement, self-feeding and conversation.
Held-hand failure drops the exact weapon once, retaining durability and quality.

Wolves consider injury, hunger/aggression and the actual attacker when retreating.
Active human encounters approach and bite at combat cadence, with remembered
last-seen pursuit rather than tracking a hidden target's live position.
Wild wolves do not seek human clinics. Critical vital injury or blood loss can
kill independently of displayed HP. Finalization uses the existing death,
corpse, inheritance and quest pipeline and is guarded against duplicate events.
Human assaults retain the incident, witness attribution, grudge and law systems;
attacking wildlife does not create civilian assault accusations.

HP is a compatibility projection, not a second wound pool. Old environmental
damage uses a general systemic reserve. Setting HP higher cannot refill blood
or erase wounds. Old saves migrate without RNG draws; generic broken-leg flags
are preserved on the weaker recorded leg (left on a tie when no side was known).
The old raw BodyPart HP fields remain for migration; use capabilities or the
derived HP proxy for an upgraded body's condition.

## Treatment and scope

Bandages/salves dress one wound and sharply reduce bleeding. Splints stabilize
one fractured region. Neither resets tissue damage. Recovery uses the game
clock (roughly days for soft tissue, weeks for fractures), with rest and
treatment modifiers. Medicine skill affects dressing/splint quality; self-care
has a reach penalty. Blood replenishes by at most eight percentage points per
supplied rest day (four while active), reduced by hunger/thirst, once bleeding
is controlled. A large reserve loss no longer refills overnight.
The saved high-water clock prevents duplicate advancement
or healing during paused rendering. A large sleep jump evaluates blood loss
before regeneration, preventing death-and-resurrection artifacts.

This is a game-unit model, not a medical or Newtonian-physics simulator. It does
not yet implement organs/arteries, infection, amputation, grappling/bite holds,
surgery, bandage clothing layers, limping animations or assisted mobility.
The detailed plans currently cover humans and wolves only; other animals keep
their legacy damage model. Injury effects are connected to movement, grip,
combat and timed work, not every abstract economic calculation. Sight is
represented in body function and attack accuracy, not a new eye/FOV system.

Persistent character layers are retained in the body preview and collapsed
unconscious pose. No replacement profession sprites or new art packs are used.

## Verification

`tests/test_body_combat.py` covers connected parts, accumulated fractures,
legacy migration, blood clocks, save/load, HP independence, equipment/armor,
weapon drops, death idempotence, real treatment, fractional movement/work,
wolf retreat, no-model network boundaries, UI scrolling and collapsed identity.
Existing combat/incident tests now stage reachable local attacks rather than
forcing results through mocked model prose; social assertions are retained.

Run `python -m tools.body_review` for a deterministic **staged** encounter and
native renderer captures in `artifacts/body-combat/`. It exercises three wolf
bites, fifteen aimed axe swings, wolf death, healer treatment, save/load and
next-day recovery. Mara's movement is 40% after the fight and 67% after the
treated rest day. These are fixture outcomes, not claims of spontaneous AI.
The fourth capture is a separate forced-unconsciousness pose fixture, not an
additional event in that encounter.

A live-world smoke run also advanced 80 real ticks, round-tripped the world in
memory, then advanced 40 more: 115 living villagers, 122 detailed bodies, player
alive, zero queued model tasks.

The first pass found a mild-weather regression: warm clothing was added as
heat even beside a hearth. That is fixed in the gameplay-stabilization follow-up;
the original test is retained, with additional cold/heat/clothing controls.
See [combat-gameplay-stabilization.md](combat-gameplay-stabilization.md) for the
ordinary-input encounter, balance measurements, integration fixes and final
suite verification.
