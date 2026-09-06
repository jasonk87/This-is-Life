"""When a line of gossip comes back, as opposed to what it says.

The service does its work on a background thread, so *when* a result is ready is
a fact about the machine, not about the world. It used to be handed back on
whichever tick the thread happened to finish on, and that leaked into the
simulation: a finished chronicle rolls its item quality from `random`, so a
result landing one tick earlier moved every draw after it and two runs of one
seed came apart.

So the rule these tests pin down is: a request submitted on tick T comes back on
tick T + response_timeout_ticks, carrying the model's text if it arrived in time
and the fallback if it did not. How fast the model answers decides the words and
nothing else.

The worker thread is replaced here by a method the test calls, because "the
result arrived at this exact moment" is the whole subject and a real thread
cannot be asked to do that.
"""

import unittest
from types import SimpleNamespace

from services.llm_gossip import AsyncLLMGossipService

TIMEOUT_TICKS = 20


class _ManualService(AsyncLLMGossipService):
    """The service with its worker replaced by `finish`, called by the test."""

    def _worker_loop(self):
        return  # the test decides when work completes

    def finish(self, request_id: int, text: str) -> None:
        """Hand back the model's answer for a request, as the worker would."""
        request = self._pending[request_id]
        self._completed_queue.put(self._make_result(request, text, used_fallback=False))


def _service():
    return _ManualService(response_timeout_ticks=TIMEOUT_TICKS)


def _submit(service, speaker_id=1, event_id="ev-1", *, now_ticks):
    return service.submit(
        speaker=SimpleNamespace(id=speaker_id, x=3, y=4),
        memory_event=SimpleNamespace(id=event_id, event_type="rumor"),
        subject_name="Mara Rowan",
        now_ticks=now_ticks,
    )


class TestAResultWaitsForItsTick(unittest.TestCase):
    def test_an_answer_that_arrives_at_once_is_still_held(self):
        service = _service()
        _submit(service, now_ticks=100)
        service.finish(1, "Real gossip.")

        self.assertEqual(service.poll_completed(now_ticks=100), [])
        self.assertEqual(service.poll_completed(now_ticks=110), [])
        self.assertEqual(service.poll_completed(now_ticks=119), [])

        released = service.poll_completed(now_ticks=120)
        self.assertEqual([r.text for r in released], ["Real gossip."])
        self.assertFalse(released[0].used_fallback)

    def test_an_answer_that_never_comes_falls_back_on_the_same_tick(self):
        service = _service()
        _submit(service, now_ticks=100)

        self.assertEqual(service.poll_completed(now_ticks=119), [])

        released = service.poll_completed(now_ticks=120)
        self.assertEqual(len(released), 1)
        self.assertTrue(released[0].used_fallback)

    def test_early_and_late_answers_land_on_the_very_same_tick(self):
        """The property the determinism of the tick loop rests on."""
        ticks = []
        for arrival in (100, 105, 119):
            service = _service()
            _submit(service, now_ticks=100)
            for tick in range(100, 121):
                if tick == arrival:
                    service.finish(1, "Real gossip.")
                if service.poll_completed(now_ticks=tick):
                    ticks.append(tick)
                    break
        self.assertEqual(ticks, [120, 120, 120])

    def test_a_result_is_released_once_and_not_again(self):
        service = _service()
        _submit(service, now_ticks=100)
        service.finish(1, "Real gossip.")

        self.assertEqual(len(service.poll_completed(now_ticks=120)), 1)
        self.assertEqual(service.poll_completed(now_ticks=121), [])
        self.assertEqual(service.poll_completed(now_ticks=200), [])

    def test_a_late_answer_after_the_fallback_is_discarded(self):
        service = _service()
        _submit(service, now_ticks=100)

        released = service.poll_completed(now_ticks=120)
        self.assertTrue(released[0].used_fallback)

        # The model finally replies. That answer is stale and must not surface
        # as a second line of gossip about the same event.
        request = SimpleNamespace(
            request_id=1, request_key=(1, "ev-1"), request_type="gossip",
            speaker_id=1, speaker_position=(3, 4), fallback_text="...", metadata=None,
        )
        service._completed_queue.put(
            service._make_result(request, "Too late.", used_fallback=False))
        self.assertEqual(service.poll_completed(now_ticks=121), [])


class TestTheOrderTheyComeBackIn(unittest.TestCase):
    def test_submission_order_not_completion_order(self):
        service = _service()
        _submit(service, speaker_id=1, event_id="ev-1", now_ticks=100)
        _submit(service, speaker_id=2, event_id="ev-2", now_ticks=100)

        # Second request finishes first, as threads are free to do.
        service.finish(2, "Second speaker.")
        service.finish(1, "First speaker.")

        released = service.poll_completed(now_ticks=120)
        self.assertEqual([r.speaker_id for r in released], [1, 2])


class TestARejectedRequestStaysRejected(unittest.TestCase):
    """Turned away at the door means nothing comes back. Ever.

    The service used to queue a fallback result for requests it had just refused
    for being over capacity. Those results were dropped again on the way out,
    because a request that was never registered has nothing to be matched
    against - so the code read as graceful degradation and did nothing at all.

    Making it deliver would have been the wrong repair. queue_chronicle_draft
    only records which memories a draft covers once submit says yes, so a
    fallback arriving for a refused draft would finish a chronicle nobody
    started, hand the scribe the book and pay out the crafting experience.
    """

    def test_over_capacity_submissions_deliver_nothing(self):
        service = _ManualService(response_timeout_ticks=TIMEOUT_TICKS)
        service.max_pending = 3

        accepted = [_submit(service, speaker_id=i, event_id=f"ev-{i}", now_ticks=100)
                    for i in range(5)]
        self.assertEqual(accepted, [True, True, True, False, False])

        released = service.poll_completed(now_ticks=100 + TIMEOUT_TICKS)
        self.assertEqual(len(released), 3, "a refused request came back anyway")
        self.assertEqual(sorted(r.speaker_id for r in released), [0, 1, 2])

        # And nothing turns up later either.
        self.assertEqual(service.poll_completed(now_ticks=100 + TIMEOUT_TICKS * 5), [])

    def test_a_duplicate_of_a_pending_request_is_refused(self):
        service = _service()
        self.assertTrue(_submit(service, speaker_id=1, event_id="ev-1", now_ticks=100))
        self.assertFalse(_submit(service, speaker_id=1, event_id="ev-1", now_ticks=100))

        released = service.poll_completed(now_ticks=120)
        self.assertEqual(len(released), 1)


class TestCallersWithoutAGameClock(unittest.TestCase):
    """Nothing outside the tick loop knows what tick it is; they keep the old deal."""

    def test_a_result_arrives_as_soon_as_it_is_ready(self):
        service = _service()
        _submit(service, now_ticks=None)
        service.finish(1, "Real gossip.")

        released = service.poll_completed()
        self.assertEqual([r.text for r in released], ["Real gossip."])


if __name__ == "__main__":
    unittest.main()
