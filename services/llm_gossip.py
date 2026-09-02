"""Asynchronous Ollama-backed presentation helpers for gossip and chronicles."""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import os
import queue
import threading
import time

from runtime_compat import requests

DEFAULT_GOSSIP_OLLAMA_ENDPOINT = os.environ.get("OLLAMA_GOSSIP_ENDPOINT", "http://localhost:11434")
DEFAULT_GOSSIP_OLLAMA_MODEL = os.environ.get("OLLAMA_GOSSIP_MODEL", "llama3.2:latest")
GOSSIP_SYSTEM_PROMPT = (
    "You are a medieval villager. Write a single, short sentence of dialogue gossiping "
    "about the provided event. Do not use quotes. Keep it under 15 words."
)
CHRONICLE_SYSTEM_PROMPT = (
    "You are a medieval historian. Write a single, dramatic paragraph (max 3 sentences) "
    "summarizing the following historical events for a town chronicle."
)


@dataclass(frozen=True)
class GossipRequest:
    request_id: int
    request_key: tuple
    request_type: str
    speaker_id: int
    speaker_position: tuple[int, int]
    event_id: str
    event_type: str
    prompt: str
    system_prompt: str
    subject_name: str
    target_name: str
    fallback_text: str
    submitted_at: float
    # The game tick this was queued on, when the caller knows it. Optional so
    # that anything constructing a request without a world still works.
    submitted_at_tick: int | None = None
    metadata: dict | None = None


@dataclass(frozen=True)
class GossipResult:
    request_id: int
    request_key: tuple
    request_type: str
    speaker_id: int
    speaker_position: tuple[int, int]
    text: str
    used_fallback: bool = False
    metadata: dict | None = None


class AsyncLLMGossipService:
    """Generates gossip flavor text on a background thread without blocking the game loop."""

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_GOSSIP_OLLAMA_ENDPOINT,
        model: str = DEFAULT_GOSSIP_OLLAMA_MODEL,
        response_timeout_seconds: float = 0.75,
        response_timeout_ticks: int = 20,
        request_timeout_seconds: float = 3.0,
        max_pending: int = 32,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.response_timeout_seconds = max(0.05, float(response_timeout_seconds))
        # How long to wait in game ticks, when the caller tells us what the game
        # clock says. Waiting on the wall clock made the whole simulation
        # unreproducible: whether a pending line of gossip fell back on this tick
        # or the next depended on how fast the machine was running, and that
        # changed how much of the random stream each tick consumed. It also tied
        # how chatty the village is to the frame rate. The wall clock stays as
        # the default for any caller that does not pass a tick.
        self.response_timeout_ticks = max(1, int(response_timeout_ticks))
        self.request_timeout_seconds = max(0.1, float(request_timeout_seconds))
        self.max_pending = max(1, int(max_pending))
        self._request_ids = itertools.count(1)
        self._lock = threading.Lock()
        self._pending: dict[int, GossipRequest] = {}
        self._pending_keys: dict[tuple, int] = {}
        self._expired_request_ids: set[int] = set()
        self._request_queue: queue.Queue[GossipRequest | None] = queue.Queue(maxsize=self.max_pending)
        self._completed_queue: queue.Queue[GossipResult] = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, name="llm-gossip", daemon=True)
        self._worker.start()

    def submit(self, *, speaker, memory_event, subject_name: str, target_name: str = "", now_ticks: int | None = None) -> bool:
        request_key = (getattr(speaker, "id", None), getattr(memory_event, "id", None))
        if request_key[0] is None or request_key[1] is None:
            return False

        fallback_text = self._build_fallback_text(subject_name=subject_name, target_name=target_name, event_type=getattr(memory_event, "event_type", ""))
        request = GossipRequest(
            request_id=next(self._request_ids),
            request_key=request_key,
            request_type="gossip",
            speaker_id=int(speaker.id),
            speaker_position=(int(getattr(speaker, "x", 0)), int(getattr(speaker, "y", 0))),
            event_id=str(memory_event.id),
            event_type=str(getattr(memory_event, "event_type", "rumor") or "rumor"),
            prompt=f"Event: {getattr(memory_event, 'event_type', 'rumor')}, Subject: {subject_name or 'Someone'}.",
            system_prompt=GOSSIP_SYSTEM_PROMPT,
            subject_name=str(subject_name or "Someone"),
            target_name=str(target_name or ""),
            fallback_text=fallback_text,
            submitted_at=time.monotonic(),
            submitted_at_tick=None if now_ticks is None else int(now_ticks),
            metadata=None,
        )

        with self._lock:
            if request.request_key in self._pending_keys:
                return False
            if len(self._pending) >= self.max_pending:
                self._completed_queue.put(self._make_result(request, request.fallback_text, used_fallback=True))
                return False
            self._pending[request.request_id] = request
            self._pending_keys[request.request_key] = request.request_id

        try:
            self._request_queue.put_nowait(request)
        except queue.Full:
            with self._lock:
                self._pending.pop(request.request_id, None)
                self._pending_keys.pop(request.request_key, None)
            self._completed_queue.put(self._make_result(request, request.fallback_text, used_fallback=True))
            return False
        return True

    def submit_chronicle(self, *, scribe, memory_events, building_id, title_hint: str = "", now_ticks: int | None = None) -> bool:
        event_ids = tuple(str(getattr(event, "id", "")) for event in memory_events if getattr(event, "id", ""))
        if getattr(scribe, "id", None) is None or len(event_ids) < 2:
            return False

        prompt_lines = []
        for index, event in enumerate(memory_events[:4], start=1):
            headline = str(getattr(event, "headline", "") or "").strip() or f"{getattr(event, 'event_type', 'event')}"
            prompt_lines.append(f"{index}. {headline}")
        prompt = "Historical Events:\n" + "\n".join(prompt_lines)
        fallback_text = "The town remembers bloodshed, toil, and turning fortunes through troubled days."
        request = GossipRequest(
            request_id=next(self._request_ids),
            request_key=("chronicle", int(scribe.id), event_ids),
            request_type="chronicle",
            speaker_id=int(scribe.id),
            speaker_position=(int(getattr(scribe, "x", 0)), int(getattr(scribe, "y", 0))),
            event_id="|".join(event_ids),
            event_type="chronicle",
            prompt=prompt,
            system_prompt=CHRONICLE_SYSTEM_PROMPT,
            subject_name=str(getattr(scribe, "name", "Scribe")),
            target_name="",
            fallback_text=fallback_text,
            submitted_at=time.monotonic(),
            submitted_at_tick=None if now_ticks is None else int(now_ticks),
            metadata={
                "building_id": building_id,
                "memory_ids": list(event_ids),
                "scribe_name": str(getattr(scribe, "name", "Scribe")),
                "title_hint": str(title_hint or "Town Chronicle"),
            },
        )

        with self._lock:
            if request.request_key in self._pending_keys:
                return False
            if len(self._pending) >= self.max_pending:
                self._completed_queue.put(self._make_result(request, request.fallback_text, used_fallback=True))
                return False
            self._pending[request.request_id] = request
            self._pending_keys[request.request_key] = request.request_id

        try:
            self._request_queue.put_nowait(request)
        except queue.Full:
            with self._lock:
                self._pending.pop(request.request_id, None)
                self._pending_keys.pop(request.request_key, None)
            self._completed_queue.put(self._make_result(request, request.fallback_text, used_fallback=True))
            return False
        return True

    def poll_completed(self, now_ticks: int | None = None) -> list[GossipResult]:
        results: list[GossipResult] = []
        now = time.monotonic()
        expired_results: list[GossipResult] = []

        with self._lock:
            for request_id, request in list(self._pending.items()):
                if request.submitted_at_tick is not None and now_ticks is not None:
                    if int(now_ticks) - request.submitted_at_tick < self.response_timeout_ticks:
                        continue
                elif now - request.submitted_at < self.response_timeout_seconds:
                    continue
                expired_results.append(self._make_result(request, request.fallback_text, used_fallback=True))
                self._pending.pop(request_id, None)
                self._pending_keys.pop(request.request_key, None)
                self._expired_request_ids.add(request_id)

        results.extend(expired_results)

        while True:
            try:
                result = self._completed_queue.get_nowait()
            except queue.Empty:
                break

            with self._lock:
                if result.request_id in self._expired_request_ids:
                    self._expired_request_ids.discard(result.request_id)
                    continue
                request = self._pending.pop(result.request_id, None)
                if request is None:
                    continue
                self._pending_keys.pop(request.request_key, None)
            results.append(result)

        return results

    def shutdown(self) -> None:
        try:
            self._request_queue.put_nowait(None)
        except queue.Full:
            pass

    def _worker_loop(self) -> None:
        while True:
            request = self._request_queue.get()
            if request is None:
                return
            text = self._generate_text(request)
            used_fallback = not bool(text)
            response_text = text or request.fallback_text
            self._completed_queue.put(self._make_result(request, response_text, used_fallback=used_fallback))

    def _generate_text(self, request: GossipRequest) -> str:
        try:
            response = requests.post(
                self.endpoint + "/api/generate",
                json={
                    "model": self.model,
                    "system": request.system_prompt,
                    "prompt": request.prompt,
                    "stream": False,
                },
                timeout=self.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException:
            return ""
        except Exception:
            return ""

        text = str(payload.get("response", "") or "").strip()
        return self._sanitize_response(text, request.request_type)

    def _sanitize_response(self, text: str, request_type: str = "gossip") -> str:
        cleaned = " ".join(str(text or "").replace('"', '').replace("'", "").split())
        if not cleaned:
            return ""
        if request_type == "chronicle":
            sentence_count = 0
            trimmed_chars: list[str] = []
            for char in cleaned:
                trimmed_chars.append(char)
                if char in ".!?":
                    sentence_count += 1
                    if sentence_count >= 3:
                        break
            cleaned = "".join(trimmed_chars).strip()
            if cleaned and cleaned[-1] not in ".!?":
                cleaned += "."
            return cleaned

        words = cleaned.split()
        if len(words) > 15:
            cleaned = " ".join(words[:15]).rstrip(" ,;:-")
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
        return cleaned

    def _make_result(self, request: GossipRequest, text: str, *, used_fallback: bool) -> GossipResult:
        return GossipResult(
            request_id=request.request_id,
            request_key=request.request_key,
            request_type=request.request_type,
            speaker_id=request.speaker_id,
            speaker_position=request.speaker_position,
            text=str(text or request.fallback_text).strip(),
            used_fallback=used_fallback,
            metadata=dict(request.metadata or {}),
        )

    def _build_fallback_text(self, *, subject_name: str, target_name: str, event_type: str) -> str:
        focus_name = str(target_name or subject_name or "that trouble").strip() or "that trouble"
        if focus_name.lower() in {"none", "unknown"}:
            focus_name = "that trouble"
        event_label = str(event_type or "rumor").replace("_", " ").strip()
        if focus_name == "that trouble":
            return f"Did you hear about the {event_label}?"
        return f"Did you hear about {focus_name}?"
