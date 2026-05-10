from types import SimpleNamespace

from entities.social import KnowledgeComponent
from presentation.dialogue_surface import get_contextual_dialogue_lines
from simulation.history import HistoryLedger
from simulation.social_scene import (
    PUBLIC_EVENT_SEED_TTL_TICKS,
    create_public_event_seed_from_record,
    get_active_public_event_seeds,
    update_social_scenes,
)


def _npc(entity_id, x=10, y=10, name=None):
    return SimpleNamespace(
        id=entity_id,
        name=name or f"NPC {entity_id}",
        x=x,
        y=y,
        physical=SimpleNamespace(is_dead=False),
        combat=SimpleNamespace(is_hostile_to_player=False),
        social=SimpleNamespace(recent_social_reactions=[], opinion_modifiers={}),
        knowledge=KnowledgeComponent(),
        current_activity=None,
    )


def _world(*, tick=0, npcs=(), history=None):
    entities_by_id = {npc.id: npc for npc in npcs}
    return SimpleNamespace(
        game_time=tick,
        village_npcs=list(npcs),
        npcs=[],
        player=SimpleNamespace(id=999, name="Player"),
        history=history or HistoryLedger(),
        social_scenes={},
        buildings_by_id={},
        get_entity_by_id=lambda entity_id: entities_by_id.get(entity_id),
    )


def test_death_record_creates_funeral_grieving_seed():
    history = HistoryLedger()
    death = history.record_death(
        deceased_id=1,
        description="Alda died.",
        game_time=10,
        location=(12, 12),
        settlement_id="village",
        region_id="north",
    )
    world = _world(tick=20, history=history)

    seed = create_public_event_seed_from_record(world, death)

    assert seed is not None
    assert seed.seed_type == "funeral"
    assert seed.tone == "grieving"
    assert seed.source_record_id == death.record_id
    assert seed.location == (12, 12)
    assert seed.settlement_id == "village"
    assert seed.region_id == "north"
    assert seed.participant_ids == [1]
    assert seed.topic_hints == ["death", "grief"]


def test_crime_record_creates_tense_accusation_seed():
    history = HistoryLedger()
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=2,
        victim_id=3,
        witness_ids=(4,),
        description="Rook assaulted Mira.",
        game_time=10,
        location=(15, 15),
    )
    world = _world(tick=20, history=history)

    seed = create_public_event_seed_from_record(world, crime)

    assert seed is not None
    assert seed.seed_type == "accusation"
    assert seed.tone == "tense"
    assert seed.participant_ids == [2, 3, 4]
    assert seed.topic_hints == ["crime", "fear"]


def test_celebration_seed_influences_scene_tone():
    history = HistoryLedger()
    spouse_a = _npc(10, 20, 20, "Ari")
    spouse_b = _npc(11, 21, 20, "Bea")
    guest = _npc(12, 22, 20, "Cal")
    marriage = history.record_marriage(
        spouse_ids=(spouse_a.id, spouse_b.id),
        description="Ari and Bea married.",
        game_time=5,
        location=(20, 20),
    )
    world = _world(tick=10, history=history, npcs=(spouse_a, spouse_b, guest))
    seed = create_public_event_seed_from_record(world, marriage)

    scenes = update_social_scenes(world, force=True)
    seeded_scene = next(scene for scene in scenes if seed.seed_id in scene.public_event_seed_ids)

    assert seeded_scene.scene_type == "celebration"
    assert seeded_scene.tone == "celebratory"
    assert f"marriage:{marriage.record_id}" in seeded_scene.active_topic_ids
    assert set(seeded_scene.participant_ids) >= {spouse_a.id, spouse_b.id}


def test_expired_seeds_stop_affecting_scenes():
    history = HistoryLedger()
    left = _npc(20, 30, 30)
    right = _npc(21, 31, 30)
    death = history.record_death(
        deceased_id=22,
        description="Alda died.",
        game_time=1,
        location=(30, 30),
    )
    world = _world(tick=5, history=history, npcs=(left, right))
    seed = create_public_event_seed_from_record(world, death)
    assert seed is not None

    active_scenes = update_social_scenes(world, force=True)
    assert any(scene.tone == "grieving" for scene in active_scenes)

    world.game_time = seed.expires_tick + 1
    world.social_scenes = {}
    expired_scenes = update_social_scenes(world, force=True)

    assert get_active_public_event_seeds(world) == []
    assert all(scene.scene_type != "funeral" for scene in expired_scenes)
    assert all(scene.tone != "grieving" for scene in expired_scenes)


def test_seeded_scene_biases_dialogue_topics_correctly():
    history = HistoryLedger()
    speaker = _npc(30, 40, 40, "Speaker")
    listener = _npc(31, 41, 40, "Listener")
    deceased = _npc(32, 40, 41, "Alda")
    worker = _npc(33, 42, 40, "Pella")
    death = history.record_death(
        deceased_id=deceased.id,
        description="Alda died.",
        game_time=5,
        location=(40, 40),
    )
    employment = history.record_employment_change(
        worker_id=worker.id,
        profession="baker",
        employment_action="hired",
        description="Pella found work.",
        game_time=6,
        location=(40, 40),
    )
    speaker.knowledge.learn_history_record(employment, "official_record", 1.0, 10)
    speaker.knowledge.learn_history_record(death, "official_record", 1.0, 11)
    world = _world(tick=20, history=history, npcs=(speaker, listener, deceased, worker))
    seed = create_public_event_seed_from_record(world, death)
    scene = next(scene for scene in update_social_scenes(world, force=True) if seed.seed_id in scene.public_event_seed_ids)

    line = get_contextual_dialogue_lines(speaker, listener, world, limit=1, scene=scene)[0]

    assert line.topic_type == "death"
    assert line.text.startswith("Quietly")
