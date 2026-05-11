# Simulation Doctrine

This document is implementation guidance for This-is-Life. It is not lore, marketing copy, or a feature wish list. Read this before adding systems that affect NPC behavior, resources, construction, ownership, territory, animals, ecology, economy, or settlement growth.

The project direction is simple: simulate a living world deeply, then present it with lightweight, readable tools.

## Core Doctrine

### 1. The Player Is Not Special

The player and NPCs should obey the same world rules wherever practical.

Do not create a privileged player-only pathway if the same action could be represented as a system that NPCs can also use. If the player can buy land, request work, post a contract, build a structure, haul goods, hunt animals, sell products, hire labor, or break laws, NPCs should eventually be able to interact with the same underlying rules.

Player convenience UI is fine. Player-only physics, economy, or resource exceptions are not.

### 2. World-First Gameplay

Avoid traditional quest design as the default content model.

Prefer:

- contracts
- opportunities
- shortages
- rumors
- emergencies
- social pressure
- political requests
- economic incentives
- visible local problems
- systemic events caused by the simulation

A “quest” should usually be a structured view of a real world condition, not a hand-authored bubble disconnected from the world. If a tavern needs venison, that need should come from food demand, inventory, hunters, butchers, trade distance, or failed supply—not from a static quest marker.

### 3. Embodied Local Simulation

In active or nearby areas, work should happen through actors doing the work.

NPCs should physically move, haul, build, hunt, clean, eat, trade, patrol, flee, fail, recover, and ask for help. Active simulation should not teleport outcomes just because a task exists.

For local systems, the expected chain is:

1. Need or intent appears.
2. A real actor is selected or volunteers.
3. The actor travels to the relevant place.
4. The actor performs the action using actual tools, materials, animals, inventory, or terrain.
5. The world state changes only when the action physically succeeds.
6. Failure leaves recoverable state, not silent magic.

Examples:

- Supplies move because people haul them.
- Construction advances because builders deliver materials and work at the site.
- Hunting succeeds because hunters find animals, kill them, and bring carcasses or meat home.
- Guards patrol actual territory, not an abstract “guard coverage” number in active areas.

### 4. Honest Offscreen Simulation

Offscreen simulation may be abstract. It must still obey the same underlying truth and resource constraints.

Offscreen abstraction is for performance and scope, not cheating. It may compress travel, labor, logistics, and time, but it should not invent resources, ignore ownership, bypass risk, or violate active-world rules.

If an offscreen mine produces ore, the ore should come from a deposit, labor, tools, and time. If offscreen trade brings grain, it should come from a region that plausibly exports grain and should involve cost, distance, risk, and availability.

### 5. No Magical Resource Spawning

Buildings do not create resources from nothing.

Non-negotiable examples:

- Stables do not spawn horses.
- Hunting lodges do not spawn animals.
- Mines do not create infinite ore.
- Farms do not create crops without land, seed, labor, season, water, and time.
- Taverns do not create meals without ingredients, cooks, fuel, tools, or trade.
- Construction sites do not create buildings without land, materials, labor, and time.

Resources should originate from one or more of:

- ecology
- animal populations
- labor
- harvesting
- farming
- hunting
- fishing
- mining deposits
- crafting and production chains
- storage
- trade
- regional imports
- salvage or ruin recovery

If a system needs resources and none exist, it should create demand, contracts, shortages, migration pressure, trade pressure, theft pressure, or failure—not free resources.

### 6. Modular Causality

Prefer small systems that compose into emergent outcomes over scripted events.

A town growing should be the result of population pressure, available land, construction labor, supplies, wealth, permissions, and roads. A food crisis should emerge from crop failure, hunting pressure, trade disruption, spoilage, population growth, or poor storage.

Build systems as reusable causal parts:

- need detection
- task creation
- actor assignment
- travel
- material transfer
- work execution
- payment
- failure recovery
- social memory
- local feedback

Avoid one-off scripts that fake the result while bypassing the causes.

### 7. Ownership Is Influence, Not Total Control

Ownership should create rights, incentives, and authority. It should not grant absolute control over the world.

Workers can quit. Animals can escape. Citizens can disobey. Dangerous animals remain dangerous. Officials can deny requests. Thieves can steal. Workers can be sick, afraid, underpaid, blocked, or unwilling.

Owners and managers should influence behavior through wages, contracts, authority, reputation, access, tools, land rights, and social pressure. They should not mind-control actors.

### 8. Settlements Are Living Territories

Towns are not just collections of buildings.

Settlements should have:

- land claims
- city limits
- urban/core areas
- rural/periphery areas
- farms
- ranches
- roads
- patrol areas
- hunting territories
- logging territories
- reserved expansion land
- jurisdiction and authority
- expansion pressure

Buildings should exist inside territory. Construction should reserve land. Farms, ranches, hunting lodges, logging camps, workshops, and estates should use land differently.

Future systems such as law, taxation, patrols, permits, migration, and zoning should build on this territorial foundation.

### 9. Economy Is Incentive-Based

NPC and player behavior should be guided by incentives.

Important incentives include:

- prices
- wages
- shortages
- contracts
- risk
- distance
- scarcity
- ownership
- reputation
- safety
- access to tools
- available labor
- market demand

Avoid making NPCs do economically significant work just because a script says so. Give them a reason: hunger, pay, duty, debt, fear, profit, loyalty, law, family, ambition, or survival.

### 10. Animals Are Autonomous Actors

Animals are not item generators or building attachments.

Animals should exist as autonomous actors that can:

- roam
- flee
- herd
- hunt
- breed
- age
- become stressed
- trust or distrust handlers
- escape poor containment
- injure people
- die
- migrate
- be captured, tamed, trained, traded, stolen, or slaughtered

Human use of animals should be a relationship between human systems and animal autonomy, not a static production slot.

### 11. Ecology Has Abstract and Physical Layers

Regional populations are the truth. Visible animals and fish are local manifestations of that truth.

The world can track abstract regional populations for performance, but active areas should instantiate local actors from that underlying population. Killing visible animals should affect the regional truth. Regional depletion should reduce local sightings. Migration, breeding, habitat, season, and hunting pressure should matter.

The same principle applies to fish, wildlife, forests, and other ecological resources.

### 12. Construction Changes the World

Construction should alter the physical world through systems, not instant placement.

Buildings, ponds, farms, mines, roads, fences, estates, workshops, and civic structures should require some combination of:

- land claims
- permits or approval where appropriate
- blueprints
- materials
- tools
- labor
- hauling
- time
- money
- maintenance
- inspection

Active construction should be visible through construction sites, staged progress, material piles, workers, labels, and hover summaries. Offscreen construction may be abstract, but it must remain constrained by materials, labor, land, and time.

### 13. Professions Are Real Work

Professions should create responsibilities, tasks, and outputs.

Managers manage. Laborers labor. Hunters hunt. Butchers butcher. Farmers farm. Guards patrol. Officials administer. Traders trade. Builders build. Cleaners clean. Animal handlers handle animals.

A profession should not be just a title or shop inventory modifier. It should influence daily schedules, task eligibility, skills, social status, wages, tools, risks, outputs, and obligations.

### 14. Management and Delegation Matter

The player and NPC owners should be able to delegate real tasks to real actors.

Delegated work should travel through the same causal pipeline as other work:

1. Request or need is created.
2. A capable actor accepts or is assigned.
3. The actor travels.
4. The actor performs the work.
5. The actor succeeds, fails, stalls, or calls for help.
6. Payment, reputation, ownership, inventory, and world state update.

Delegation should not be a menu that instantly converts money into outcomes. It should create accountable work in the world.

### 15. Simulate Deeply, Present Simply

Do not require advanced visuals for deep systems.

Use lightweight presentation:

- activity labels
- hover summaries
- map markers
- simple overlays
- existing tile sprites
- floating text
- ambient chatter
- noticeboards
- contracts
- status strings
- visible actors moving through the world

The simulation should be deep. The presentation can be simple and readable.

Do not block systemic work on complex art, animation, cinematic sequences, or city-builder UI.

### 16. Avoid Cookie-Cutter Growth

Towns and properties should not grow as identical grids.

Use:

- blueprints
- variants
- land suitability
- roads
- geography
- wealth
- culture
- region identity
- local resources
- ownership
- settlement pressure
- political decisions
- historical accidents

Two villages with the same population should still differ if one is wealthy, forested, mountainous, river-adjacent, politically strict, or trade-connected.

### 17. Territorial Approval and Bureaucracy

Land expansion, zoning, permits, grants, taxes, roads, city limits, and jurisdiction should eventually involve real political offices with duties and decision power.

Officials should not be decorative. A mayor, council, sheriff, tax collector, land officer, or captain should eventually be able to approve, deny, delay, inspect, tax, patrol, or enforce territory decisions according to law, personality, incentives, corruption, reputation, and public pressure.

### 18. Future Direction

Future systems should follow this doctrine, especially:

- food production chains
- hunting lodges and butcher shops
- farms, ranches, and livestock
- animal taming, training, breeding, containment, escape, and trade
- fish and aquatic ecology
- regional trade and imports
- property upgrades and estate growth
- cleaning, repair, decay, and maintenance
- political offices with real duties
- patrol and jurisdiction systems
- mining and resource geography
- building blueprints and variants
- personal goals and aspirations
- delegated player and NPC tasks
- contracts, rumors, emergencies, and social pressure
- roads, access, and travel costs
- taxation, permits, zoning, and land grants

## Implementation Rules of Thumb

When adding or changing a system, ask these questions:

1. What is the real-world source of this resource, object, task, or authority?
2. Who knows about it?
3. Who wants it, and why?
4. Who can act on it?
5. What physical action happens in active simulation?
6. What abstract action happens offscreen?
7. What inventory, land, animal, ecology, building, or social state changes?
8. What happens if the actor fails, dies, refuses, cannot path, lacks tools, or lacks materials?
9. What does the player see without needing a new UI panel?
10. Can NPCs and the player use the same underlying rules?

If a proposed implementation skips these questions and directly grants the outcome, it probably violates the doctrine.
