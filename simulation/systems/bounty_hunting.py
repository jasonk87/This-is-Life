"""Public alive-only contracts, treasury escrow and physical prisoner escorts.

No omniscient target markers: notices retain the last reported crime location.
An unconscious person cannot walk an escort; carrying is a separate future action.
"""
from dataclasses import dataclass
from simulation.systems import settlements
from simulation.systems.body_combat import can_act, functions_for


@dataclass
class BountyContract:
    id: str
    settlement_id: str
    target_id: int
    target_name: str
    reward: int
    last_seen: tuple | None
    status: str = "open"
    escrow: int = 0
    treasury_id: str | None = None


def contracts(world):
    if not hasattr(world, "bounty_contracts"):
        world.bounty_contracts = {}
    return world.bounty_contracts


def get_contract(world, contract_id):
    return contracts(world).get(contract_id)


def _wanted(target):
    from engine import NPC_ARREST_BOUNTY_THRESHOLD
    return (target is not None and not target.physical.is_dead
            and not target.schedule.is_jailed and target.economic.bounty >= NPC_ARREST_BOUNTY_THRESHOLD)


def _close(world, contract, status):
    if contract.escrow:
        treasury = world.buildings_by_id.get(contract.treasury_id)
        if treasury is None:
            return False  # Retain the escrow until its owner can receive it.
        world._set_trade_money_balance(treasury, world._get_trade_money_balance(treasury) + contract.escrow)
        contract.escrow = 0
    target = world.get_entity_by_id(contract.target_id)
    if target is not None and getattr(target.schedule, "bounty_contract_id", None) == contract.id:
        target.schedule.bounty_contract_id = None
        if target.schedule.current_task == "bounty_escort":
            target.schedule.current_task = "idle"
            target.schedule.current_path = []
            target.task_target_entity_id = None
    contract.status = status
    return True


def refresh(world):
    for contract in list(contracts(world).values()):
        if contract.status in {"open", "accepted", "escorting"} and not _wanted(world.get_entity_by_id(contract.target_id)):
            _close(world, contract, "closed")


def notices(world):
    village = settlements.current(world)
    if village is None:
        return []
    refresh(world)
    # Only a report with an actual witness can become a public notice.
    latest = {}
    for record in [*getattr(world.history, "events", []), *getattr(world, "bounty_reports", {}).values()]:
        if (getattr(record, "settlement_id", None) == village.id
                and getattr(record, "witness_ids", ()) and hasattr(record, "suspect_id")):
            latest[record.suspect_id] = record
    ledger = contracts(world)
    for target_id, record in latest.items():
        target = world.get_entity_by_id(target_id)
        if target is world.player or not _wanted(target):
            continue
        existing = next((c for c in ledger.values() if c.target_id == target_id
                         and c.settlement_id == village.id and c.status in {"open", "accepted", "escorting"}), None)
        key = f"wanted-{village.id}-{record.id}"
        if existing is None and key not in ledger:
            ledger[key] = BountyContract(key, village.id, target_id, target.name,
                                        min(300, int(target.economic.bounty)), record.location)
    return [c for c in ledger.values() if c.settlement_id == village.id and c.status in {"open", "accepted", "escorting"}]


def accept_or_turn_in(world, contract_id):
    contract = get_contract(world, contract_id)
    village = settlements.current(world)
    if not contract or not village or contract.settlement_id != village.id or not can_act(world.player) or world.player.state.is_jailed:
        return False
    refresh(world)
    if contract.status == "escorting":
        return turn_in(world, contract)
    if contract.status == "accepted":
        world.add_message_to_chat_log(f"{contract.target_name}: last reported at {contract.last_seen}. Find them, request surrender, then escort them to this town's sheriff office. Alive only.")
        return True
    if contract.status != "open":
        return False
    if any(c.target_id == contract.target_id and c.status in {"accepted", "escorting"} for c in contracts(world).values()):
        world.add_message_to_chat_log("You already hold a contract for this person.")
        return False
    hall = world.get_town_hall_building()
    if hall is None or world._get_trade_money_balance(hall) < contract.reward:
        world.add_message_to_chat_log("This town cannot currently fund that reward.")
        return False
    world._set_trade_money_balance(hall, world._get_trade_money_balance(hall) - contract.reward)
    contract.escrow, contract.treasury_id, contract.status = contract.reward, hall.id, "accepted"
    world.add_message_to_chat_log(f"Accepted: bring {contract.target_name} alive to {village.name}'s sheriff office. {contract.reward} coins reserved. Last reported: {contract.last_seen}. Adjacent interaction: Request Surrender.")
    return True


def active_for(world, target):
    return next((c for c in contracts(world).values() if c.target_id == target.id and c.status in {"accepted", "escorting"}), None)


def request_surrender(world, target):
    contract = active_for(world, target)
    if (not contract or not _wanted(target) or not can_act(world.player)
            or max(abs(world.player.x-target.x), abs(world.player.y-target.y)) > 1):
        return False
    if not can_act(target) or functions_for(target)["movement"] <= .1:
        world.add_message_to_chat_log("They cannot walk. Stabilize and let them recover before an escort; carrying is not available yet.")
        return False
    impaired = min(functions_for(target)["grip"], functions_for(target)["movement"]) < .5
    if target.combat.is_hostile_to_player and not impaired:
        world.add_message_to_chat_log(f"{target.name} refuses to surrender.")
        return False
    contract.status = "escorting"
    target.schedule.bounty_contract_id = contract.id
    target.combat.is_hostile_to_player = False
    target.schedule.current_task = "bounty_escort"
    target.schedule.current_path = []
    target.schedule.current_destination_coords = None
    target.task_target_entity_id = world.player.id
    world.add_message_to_chat_log(f"{target.name} surrenders and agrees to accompany you to the sheriff. Stay close; deliver at the issuing town's sheriff office.")
    return True


def maintain_escort(world, target):
    contract_id = getattr(target.schedule, "bounty_contract_id", None)
    if not contract_id:
        return False
    contract = get_contract(world, contract_id)
    if not contract or contract.status != "escorting":
        target.schedule.bounty_contract_id = None
        return False
    if not _wanted(target):
        _close(world, contract, "closed")
        return False
    if (world.player.physical.is_dead or world.player.state.is_jailed
            or max(abs(target.x-world.player.x), abs(target.y-world.player.y)) > 16):
        _close(world, contract, "abandoned")
        world.add_message_to_chat_log(f"You lost the escort of {target.name}; the reserved reward returns to the town.")
        return False
    target.schedule.current_task = "bounty_escort"
    target.task_target_entity_id = world.player.id
    return True


def turn_in(world, contract):
    if contract is None:
        return False
    target = world.get_entity_by_id(contract.target_id)
    village = settlements.current(world)
    if (contract.status != "escorting" or not _wanted(target) or village is None
            or village.id != contract.settlement_id or not can_act(world.player)):
        return False
    def nearby(entity, building):
        return (building.global_origin_x-2 <= entity.x <= building.global_origin_x+building.width+1
                and building.global_origin_y-2 <= entity.y <= building.global_origin_y+building.height+1)
    jail = next((b for b in village.buildings if b.building_type == "sheriff_office"
                 and nearby(world.player, b) and nearby(target, b)), None)
    if jail is None or max(abs(target.x-world.player.x), abs(target.y-world.player.y)) > 3:
        world.add_message_to_chat_log("Bring the living suspect with you to the issuing town's sheriff office, then Deliver Prisoner.")
        return False
    world._serve_npc_jail_time(target, jail_building=jail)
    if not target.schedule.is_jailed:
        return False
    paid = contract.escrow
    world.player.economic.money += paid
    contract.escrow = 0
    contract.status = "completed"
    target.schedule.bounty_contract_id = None
    world.player.social.fame += 2
    world.log_event(event_type="bounty_completed", description=f"{{subject}} delivered {contract.target_name} alive to {village.name}'s sheriff and received {paid} coins.", subject_id=world.player.id, target_id=target.id, location=(target.x, target.y))
    world.add_message_to_chat_log(f"{contract.target_name} is in custody. {paid} coins paid; contract complete.")
    return True
