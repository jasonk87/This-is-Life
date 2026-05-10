from types import SimpleNamespace

from presentation.social_feedback import (
    collect_visible_social_indicators,
    describe_social_scene,
    social_hover_summary,
    social_marker_for_entity,
    social_tags_for_entity,
)
from simulation.history import HistoryLedger
from simulation.social_scene import create_public_event_seed_from_record, update_social_scenes
from simulation.social_scene import SocialScene


def _world(*, player=None, scenes=None, npcs=(), tick=0):
    return SimpleNamespace(
        player=player or SimpleNamespace(x=10, y=10),
        social_scenes={scene.scene_id: scene for scene in (scenes or [])},
        village_npcs=list(npcs),
        npcs=[],
        game_time=tick,
        buildings_by_id={},
        get_entity_by_id=lambda entity_id: next((npc for npc in npcs if npc.id == entity_id), None),
    )


def _npc(entity_id, x=10, y=10, *, reactions=(), conversation_partner_id=None):
    return SimpleNamespace(
        id=entity_id,
        x=x,
        y=y,
        physical=SimpleNamespace(is_dead=False),
        combat=SimpleNamespace(is_hostile_to_player=False),
        current_activity=None,
        conversation_partner_id=conversation_partner_id,
        social=SimpleNamespace(recent_social_reactions=list(reactions)),
    )


def test_scene_state_extraction_uses_public_event_tone_and_density():
    scene = SocialScene(
        scene_id="scene:funeral:1",
        scene_type="funeral",
        location=(12, 13),
        participant_ids=[1, 2, 3, 4],
        tone="grieving",
    )
    scene.public_event_seed_ids.append("seed-1")

    indicator = describe_social_scene(scene)

    assert indicator is not None
    assert indicator.kind == "funeral"
    assert indicator.tone == "grieving"
    assert indicator.location == (12, 13)
    assert indicator.participant_count == 4
    assert indicator.density == "cluster"
    assert indicator.source == "public_event"
    assert "grieving" in indicator.label


def test_social_tag_generation_prioritizes_reactions_and_scene_state():
    npc = _npc(
        1,
        reactions=[{"reaction_type": "curiosity"}, {"reaction_type": "fear"}],
        conversation_partner_id=2,
    )
    scene = SocialScene(
        scene_id="scene:warning:1",
        scene_type="warning",
        location=(10, 10),
        participant_ids=[1, 2],
        tone="tense",
    )
    world = _world(scenes=[scene], npcs=(npc,))

    tags = social_tags_for_entity(npc, world, limit=3)
    marker = social_marker_for_entity(npc, world)

    assert tags[:3] == ["fearful", "tense", "gossiping"]
    assert marker == ("!", (255, 130, 100))


def test_visibility_filtering_hides_unseen_or_distant_scene_markers():
    visible_scene = SocialScene(
        scene_id="scene:celebration:near",
        scene_type="celebration",
        location=(12, 10),
        participant_ids=[1, 2, 3],
        tone="celebratory",
    )
    hidden_scene = SocialScene(
        scene_id="scene:warning:hidden",
        scene_type="warning",
        location=(13, 10),
        participant_ids=[4, 5],
        tone="tense",
    )
    far_scene = SocialScene(
        scene_id="scene:funeral:far",
        scene_type="funeral",
        location=(40, 40),
        participant_ids=[6, 7],
        tone="grieving",
    )
    world = _world(scenes=[visible_scene, hidden_scene, far_scene])

    indicators = collect_visible_social_indicators(
        world,
        visibility_fn=lambda _world, x, y: (x, y) != hidden_scene.location,
        max_distance=10,
    )

    assert [indicator.indicator_id for indicator in indicators] == [visible_scene.scene_id]


def test_hover_summary_reports_nearby_social_scene_without_raw_ids():
    scene = SocialScene(
        scene_id="scene:market:1",
        scene_type="market_concern",
        location=(15, 15),
        participant_ids=[1, 2, 3],
        tone="concerned",
    )
    world = _world(scenes=[scene])

    summary = social_hover_summary(world, (15, 14))

    assert summary == "concerned public concern (3 NPCs)"
    assert scene.scene_id not in summary


def test_marker_cleanup_after_seeded_scene_expiry():
    left = _npc(1, 20, 20)
    right = _npc(2, 21, 20)
    history = HistoryLedger()
    death = history.record_death(
        deceased_id=3,
        description="Alda died.",
        game_time=1,
        location=(20, 20),
    )
    world = _world(player=SimpleNamespace(x=20, y=20), npcs=(left, right), tick=5)
    seed = create_public_event_seed_from_record(world, death)
    assert seed is not None
    update_social_scenes(world, force=True)
    assert collect_visible_social_indicators(world)

    world.game_time = seed.expires_tick + 1
    update_social_scenes(world, force=True)

    assert all(indicator.kind != "funeral" for indicator in collect_visible_social_indicators(world))
