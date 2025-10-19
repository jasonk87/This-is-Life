# Farm-to-Table Feature

This document outlines the implementation of the farm-to-table production chain, which introduces a more complex and realistic food production system into the game world.

## Overview

The farm-to-table feature adds a complete food production chain, starting from the cultivation of wheat to the baking and selling of bread. This system involves new professions, buildings, and NPC behaviors, creating a more dynamic and interactive economy.

## New Professions

### Miller

-   **Description:** The Miller is responsible for processing raw wheat into flour.
-   **Workplace:** Windmill
-   **Tasks:**
    -   Purchases wheat from nearby farms.
    -   Operates the grinding stone to produce flour.
    -   Stores flour in the windmill's inventory.

### Baker

-   **Description:** The Baker uses flour to bake bread, which is then sold to villagers.
-   **Workplace:** Bakery
-   **Tasks:**
    -   Purchases flour from windmills.
    -   Uses the oven to bake bread.
    -   Sells bread to hungry NPCs.

## New Buildings

### Windmill

-   **Description:** A new building where the Miller works. It contains a "grinding\_stone" work zone.
-   **Function:** Serves as the primary location for flour production.

### Bakery

-   **Description:** A new commercial building where the Baker works. It contains an "oven" work zone.
-   **Function:** The central hub for bread production and sales.

## Economic Integration

The farm-to-table feature is fully integrated into the existing NPC economy:

-   **Food Sourcing:** NPCs with the "seeking\_food" task will now identify and path to the nearest food vendor, which includes bakeries, to purchase bread.
-   **Production Chain:** The Miller and Baker professions are linked through the trade of wheat and flour, creating a realistic supply chain.
-   **Dynamic Economy:** The availability of bread is now dependent on the successful operation of farms, windmills, and bakeries, adding a new layer of economic simulation.

## Future Enhancements

-   **More Complex Recipes:** Introduce new food items that require multiple ingredients.
-   **Quality Tiers:** Implement different quality levels for food items, affecting their price and aatisfaction.
-   **Spoilage:** Add a spoilage mechanic to perishable goods like bread and flour.
