from types import SimpleNamespace

from presentation.ambient_speech import (
    MAX_ACTIVE_AMBIENT_SPEECH,
    add_ambient_speech,
    add_dialogue_line_as_ambient_speech,
    cleanup_ambient_speech,
    format_ambient_speech_for_player,
    visible_ambient_speech_lines,
)
from presentation.dialogue_surface import DialogueLine


def _actor(entity_id, x, y, *, hearing_radius=12, speech_volume=10):
    return SimpleNamespace(
        id=entity_id,
        x=x,
        y=y,
        speech_volume=speech_volume,
        physical=SimpleNamespace(hearing_radius=hearing_radius),
    )


def _world(*, player=None, tick=0):
    return SimpleNamespace(
        player=player or _actor(100, 10, 10, hearing_radius=12),
        game_time=tick,
    )


def test_nearby_speech_becomes_visible_to_player():
    player = _actor(100, 10, 10, hearing_radius=12)
    speaker = _actor(1, 12, 10)
    world = _world(player=player, tick=5)

    line = add_ambient_speech(world, speaker=speaker, text="The mill is busy today.", audible_radius=8)

    assert line is not None
    assert visible_ambient_speech_lines(world) == [line]


def test_distant_speech_is_filtered_out():
    player = _actor(100, 10, 10, hearing_radius=12)
    speaker = _actor(1, 30, 10)
    world = _world(player=player)
    add_ambient_speech(world, speaker=speaker, text="Too far away.", audible_radius=8)

    assert visible_ambient_speech_lines(world) == []


def test_expired_speech_cleans_up():
    world = _world(tick=10)
    speaker = _actor(1, 10, 11)
    line = add_ambient_speech(world, speaker=speaker, text="This will fade.", ttl_ticks=3)
    assert line is not None

    world.game_time = 13
    cleanup_ambient_speech(world)

    assert world.active_ambient_speech == []


def test_clutter_cap_limits_visible_lines():
    world = _world()
    for index in range(8):
        add_ambient_speech(
            world,
            speaker=_actor(index, 10 + (index % 2), 10),
            text=f"Line {index}",
            audible_radius=8,
            priority=index,
        )

    visible = visible_ambient_speech_lines(world, max_lines=3)

    assert len(visible) == 3
    assert [line.text for line in visible] == ["Line 7", "Line 6", "Line 5"]


def test_important_speech_outranks_small_talk():
    world = _world()
    add_ambient_speech(world, speaker=_actor(1, 10, 10), text="Nice weather.", source_type="small_talk")
    warning = add_ambient_speech(world, speaker=_actor(2, 11, 10), text="Fire near the granary!", source_type="warning")

    visible = visible_ambient_speech_lines(world, max_lines=1)

    assert visible == [warning]


def test_distance_based_readability_uses_full_shortened_and_murmurs():
    player = _actor(100, 10, 10, hearing_radius=20)
    close = add_ambient_speech(_world(player=player), speaker=_actor(1, 12, 10), text="Full words here.", audible_radius=12)
    medium = add_ambient_speech(_world(player=player), speaker=_actor(2, 15, 10), text="This sentence is deliberately long enough to shorten at medium range.", audible_radius=12)
    far = add_ambient_speech(_world(player=player), speaker=_actor(3, 21, 10), text="You should not read this at the edge.", audible_radius=12)

    assert format_ambient_speech_for_player(close, player) == "Full words here."
    assert format_ambient_speech_for_player(medium, player).endswith("…")
    assert format_ambient_speech_for_player(far, player) == "murmuring"


def test_repeated_identical_chatter_is_deduped():
    world = _world()
    speaker = _actor(1, 10, 10)

    first = add_ambient_speech(world, speaker=speaker, text="Same rumor.")
    second = add_ambient_speech(world, speaker=speaker, text="Same rumor.")

    assert first is not None
    assert second is None
    assert visible_ambient_speech_lines(world) == [first]


def test_scene_tone_and_dialogue_source_shape_ambient_line():
    world = _world()
    speaker = _actor(1, 10, 10)
    listener = _actor(2, 11, 10)
    scene = SimpleNamespace(scene_type="celebration", tone="celebratory")
    dialogue = DialogueLine("We did it!", "small_talk", "happy", "topic-1")

    line = add_dialogue_line_as_ambient_speech(world, speaker, listener, dialogue, scene=scene)

    assert line is not None
    assert line.source_type == "celebration"
    assert line.scene_type == "celebration"
    assert format_ambient_speech_for_player(line, world.player).startswith("♪")


def test_active_speech_state_is_kept_small_by_priority():
    world = _world()
    for index in range(MAX_ACTIVE_AMBIENT_SPEECH + 5):
        add_ambient_speech(
            world,
            speaker=_actor(index, 10, 10),
            text=f"Chatter {index}",
            priority=index,
        )

    assert len(world.active_ambient_speech) == MAX_ACTIVE_AMBIENT_SPEECH
    assert world.active_ambient_speech[0].text == f"Chatter {MAX_ACTIVE_AMBIENT_SPEECH + 4}"
