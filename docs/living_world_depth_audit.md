# "This is Life" — Living-World Depth Audit (6 New Areas)

Scope: children, aging, item repair, weather/season, multi-village trade/diplomacy, festivals. Everything below is grounded in the actual code on branch `codex/fix-activeinteraction-runtime-advancement-22s3mw`. This is research only — nothing implemented.

---

## 1. Children — REAL entity, ABSENT behavior

A child is a genuine simulated NPC (`profession="Child"`, `age` tracked, ages into `"Unemployed"` at 18 via `_update_npc_ages`, engine.py ~15491), but tick-to-tick it does *nothing* distinct.

- `entities/human_behaviors.py` `build_job_behavior()` (~197-208) groups `"Child"` with `"Unemployed"`/`"Creature"` → returns bare `IdleBehavior()`, which is a no-op (`return False`).
- `_update_npc_schedules` has zero `"Child"`-specific branches — same hunger/sleep/wander loop as a jobless adult.
- No school building exists anywhere (`data/buildings.py`/`construction.py` — zero "school" hits).
- No follow-parent movement coupling. `family_ties` (mother_id/father_id/sibling_ids) is set once at birth and only ever read for relationship labels, inheritance, and migration eligibility — never for co-location or movement.
- The *only* place childhood produces any observable divergence: `simulation/systems/ambient_info.py` `_age_group()` (~545-559) biases ambient gossip topic-preference scoring by a raw age bracket (child/youth/adult/elder) — separate, uncoordinated from the profession-based 18-cutoff.

**Verdict:** you have families and births, and the kids just stand there. This is the most visible "living world" gap if a player has/sees children at all.

---

## 2. Aging effects on adults — mostly ABSENT beyond death

- Old-age death (already known, confirmed): `engine.py` ~17301-17320, elderly = `age > 70`, daily roll `random.random() < (age-70)/100`.
- Work performance/productivity: **absent**. `CareerState` advancement is purely `tenure_days`-based; zero `age` references in `simulation/careers.py`, `simulation/systems/work.py`, `simulation/systems/economy.py`.
- Retirement: **absent**. No `"retire"` keyword anywhere; NPCs work until death or existing hire/fire logic.
- Combat/physical stats: **absent**. `entities/base.py` `age` is set once at NPC init (`random.randint(18,65)`) purely to pick initial sprite — never read again for HP, stamina, or combat.
- Skill learning rate/caps: **absent**. `SkillTracker` has no age parameter.
- "Elderly" status: **shallow/binary only**. `get_human_sprite()` branches child (<18) vs adult sprite — no distinct elderly sprite or behavior; `age > 18` elsewhere is just an adult-eligibility gate for romance, not an aging effect.

**Verdict:** age is a single scalar read in exactly two places (death roll, child/adult sprite split). No graduated "elderly" experience exists at all.

---

## 3. Item durability/repair — ABSENT, not shallow

- Whole-repo search for "repair": only doc/flavor-text hits (`SIMULATION_DOCTRINE.md` design-goal wishlist; Carpenter's profession *description* says "repairs wooden structures," but Carpenter's actual sub_tasks are pure construction, no repair verb) and one unrelated building-tile-integrity check.
- Blacksmith (`data/professions.py` ~103-119, `blacksmith_shop`) and `workbench` decoration are **craft-new-item only** (smelt ingot → forge sword) — no code path ever passes an existing degraded `ItemReference` into a blacksmith/workbench interaction.
- `Player.use_item()` (engine.py ~17652) has zero repair/fix/restore branch.
- `current_durability` is only ever set at creation or reset-on-transform (food spoilage becoming a new item key) — never incremented as a repair action anywhere in the codebase.
- Only adjacent mechanic: when a player's axe breaks from chopping, it's replaced with a `"broken_tool_handle"` salvage item (engine.py ~8725) — a one-off consolation drop, not repair.

**Verdict:** gear only ever degrades toward breaking, full stop. Given this session just made player armor degrade too, durability loss is now universal with zero recourse anywhere in the game.

---

## 4. Weather/season — genuinely REAL in one deep chain, ABSENT/dead elsewhere

More real than expected, concentrated entirely in the survival system:

- State: `seasons = [Spring, Summer, Autumn, Winter]` (28 days each), `weather` = only `clear`/`rain`/`snow` really exist (`storm`/`heatwave` are referenced in dead, unreachable branches in `_update_weather`, engine.py ~11327/11341 — never in `WEATHER_DEFINITIONS`).
- **Real chain**: `simulation/systems/survival.py` — season → `SEASON_TEMPERATURE_MODIFIERS` → ambient/entity temperature → `Freezing`/`Overheating` status → HP damage, AND separately `update_npc_environmental_tasks` makes NPCs actually pathfind to shelter/heat sources when freezing or when it's raining/snowing and they're unsheltered (`"seeking_warmth"`, `"seeking_shelter"` tasks). Also gates animal mating season (`entities/behaviors.py` ~536).
- Farming yield by season: confirmed, engine.py ~16928-16942.
- Combat: **absent** — zero weather/season reads in any attack/damage function.
- Travel speed: **dead flag**. `WEATHER_DEFINITIONS["snow"]["slows_movement"] = True` is declared in data but never consumed by `calculate_path`/`_get_pathfinding_tile_cost` anywhere — an easy, low-risk win sitting right there.
- Building storm damage: **absent** (only unreachable dead code, and even if reachable it's terrain not buildings).
- NPC dialogue "weather" topic: **shallow** — the topic *label* exists but its content is built from time-of-day, not actual `world.weather` state; LLM prompts get real weather but it only colors flavor text, no guaranteed effect.

**Verdict:** the survival/shelter-seeking chain is legitimately well-built and already ties season+weather to real NPC behavior — this is the strongest system of the six investigated. The visible gaps (dead `slows_movement` flag, no combat/building effects) are more "finish what's started" than "build from scratch."

---

## 5. Multi-village trade/diplomacy — the biggest surprise: REAL and deep, likely underexposed

This is not an isolated bubble — there's substantially more here than the earlier "distant-village abstraction" review suggested:

- `Village.village_relationships` (dict, -100..100 per other village) and `Village.at_war_with` (set) are **live-updated daily** in `_update_abstract_simulation` (engine.py ~16872-17085): trading nudges relations +2/+2, a 5% daily chance of -5 decay if not trading, war auto-declares below -50, auto-peace above -10.
- At war: `_spawn_raiding_party` (~16057-16114) spawns real armed NPCs with `faction_id`/`enemy_faction_id` that path to and fight in the enemy town square. Player hook: `player_attempt_mercenary_contract` lets the player take contracts against `at_war_with` factions.
- Dynamic, **village-specific** pricing: `get_dynamic_price` (~17575-17596) computes price from each village's own supply/demand — prices genuinely diverge between villages, so manual buy-low-sell-high arbitrage is already possible (emergent, not an explicit built feature — no fast travel/brokering system assists it).
- Traveling merchants exist (`_spawn_traveling_merchants`, ~13385) and trade against local village supply/demand, though the visible trace doesn't show explicit cross-map walking logic — worth a closer look if caravans specifically matter to Jason.
- Typically 3-4 villages per generated world (`world_generation.py` ~68-79).
- Distant villages (beyond 3 chunks) get a simulated (not static) abstract economy: seasonal production, consumption, abstract trade-with-random-partner, and this same diplomacy/war system — "a deliberate simplification" per code comments, not a fully static bubble.

**Verdict:** village-to-village war, alliance, raiding, and price divergence are all real and running today. The gap isn't depth — it's that a player may never *notice* any of this unless they specifically visit multiple villages, take a mercenary contract, or get caught in a raid. This is closer to a "surface it more" opportunity than a "build it" one.

---

## 6. Festivals/cultural events — ABSENT beyond elections

- Elections (`_run_daily_governance`, engine.py ~2066) remain the *only* genuine calendar-scheduled world event with unique mechanical consequences — confirmed as the template for "what a real recurring event looks like here."
- `"festival"`/`"holiday"`/`"market_day"`/`"harvest_festival"`: zero production-code hits. `"festival"` appears only as an arbitrary example string in two test files exercising the generic history-ledger API — no generator, no trigger, ever calls it.
- `"celebration"` is real but purely *reactive* — `simulation/social_scene.py` (~413-429) tags a scene "celebration" *after* a birth/marriage/migration already happened, purely to style dialogue/VFX. No calendar link, doesn't gather NPCs, doesn't create an event.
- No generic scheduled-world-event dispatcher exists at all — elections are bespoke, not an instance of a reusable "world event" system other content could plug into.
- NPC leisure-time gathering (tavern/town-square socializing, `simulation/systems/scheduling.py` ~957-971) is real but happens *every single day* identically — it doesn't distinguish a special day from an ordinary one.

**Verdict:** literally true that every day is mechanically identical except for the periodic election/tax tick. No economic spikes, no unique gathering days, no market days.

---

## Prioritization for "living breathing world" believability

Ranked by (visibility of the gap × how broken/incomplete it currently feels × implementation leverage):

1. **Children being fully inert** — highest priority. You built births and families; a child NPC that never plays, learns, or interacts is the single most jarring "wait, is this even simulated?" moment for anyone who has or observes a family in-game. Also currently the *cheapest* fix relative to impact — could start with something as small as a "follow parent" behavior or a simple play/wander-near-home task before reaching for a school building.

2. **Item repair being totally absent** — high priority, arguably urgent given this session just made *player* armor degrade too. Right now every piece of gear in the game is on a one-way countdown to uselessness with zero recourse, and there's a thematically obvious, already-half-built hook for it: the Blacksmith profession/`blacksmith_shop` building already exists and already reads "repairs wooden structures" in its own flavor text — it just doesn't do it. Low architectural risk since `ItemReference.degrade()`/`current_durability` already exist; repair is the same mechanism in reverse.

3. **Multi-village diplomacy/trade — surface, don't build.** This is the most interesting finding of the six: real wars, raids, alliances, and price divergence already run in the background, but a typical player may never encounter any of it. Before building anything new here, worth checking with Jason whether this is a "the game doesn't tell you" problem (e.g., no UI/notification when a war starts, no easy way to discover price divergence) rather than a missing-mechanic problem. Potentially very high leverage for low implementation cost if the fix is mostly visibility/UI rather than new simulation.

4. **Weather/season polish** — medium priority, low risk. The `slows_movement` dead flag is a nearly-free win (data already declared, just needs a read in the pathfinding cost function scoped carefully like the fix-4 pathfinding cache work this session). Combat/building-storm-damage effects would add flavor but aren't gaps players are likely to consciously notice are missing.

5. **Aging effects on adults** — medium-low priority. Nice depth (elderly work slower, a retirement transition) but the old-age death mechanic already delivers the core "life has stakes" beat; this is enrichment, not a broken/missing experience.

6. **Festivals/cultural events** — lowest priority of the six, but highest "atmosphere per line of code" if Jason wants one thing that makes the world feel alive on a specific day. Since there's no reusable scheduled-event system at all, this would likely want to be designed as a small generic dispatcher (not just one bespoke festival) so it's not another one-off like elections — worth flagging as a design decision, not just an implementation one, if it's picked up.
