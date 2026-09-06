"""Who is allowed to be handed a world out of the cache.

tests/world_cache.py keys its worlds by seed. That is the right key only while
every caller asking for a given seed wants the same world. A test that builds its
world inside `patch('engine.WorldGenerator')` does not: it wants a world made of
mocks, and it must not be given one made of the real thing - nor may its mocked
world be handed to anyone else.

This was not hypothetical. Three suites built their worlds under exactly those
patches and were moved onto `fresh_world(seed=1, ...)`, a key three unmocked
suites also use. Whichever ran first won the cache, so the full run failed with
a TypeError while each file passed on its own - and which files failed depended
on collection order.

The rule: build the world yourself when you have patched what it is made of.
This checks that nobody quietly stops following it.
"""

import ast
import glob
import unittest

# Patch targets that change what a world is *made of*. Patching `World._call_llm`
# is fine - it swaps a method on the class, leaves no mock in the world, and the
# world a cache hit returns is the same one the test would have built. Patching
# the generator, the chunk grid or the map dimensions is not.
CONSTRUCTION_TARGETS = (
    "WorldGenerator",
    "_initialize_chunks",
    "WORLD_WIDTH",
    "WORLD_HEIGHT",
    "CHUNK_SIZE",
)


def _patches_construction(text: str) -> bool:
    return "patch" in text and any(t in text for t in CONSTRUCTION_TARGETS)


def _calls_fresh_world(node) -> list[int]:
    return [n.lineno for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "fresh_world"]


def _violations(path: str) -> list[tuple[int, str]]:
    source = open(path, "rb").read().decode("utf-8-sig")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            items = " ".join(ast.unparse(i.context_expr) for i in node.items)
            if _patches_construction(items):
                for lineno in _calls_fresh_world(node):
                    found.append((lineno, items[:80]))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            decorators = " ".join(ast.unparse(d) for d in node.decorator_list)
            if _patches_construction(decorators):
                for lineno in _calls_fresh_world(node):
                    found.append((lineno, decorators[:80]))
    return found


class TestNobodyCachesAMockedWorld(unittest.TestCase):
    def test_no_test_builds_a_cached_world_under_construction_patches(self):
        offenders = []
        for path in sorted(glob.glob("tests/test_*.py")):
            for lineno, why in _violations(path):
                offenders.append(f"{path}:{lineno} builds fresh_world under {why}")

        self.assertEqual(
            offenders, [],
            "These call World(...) directly instead - a world built under patches "
            "of how a world is built cannot be shared by seed:\n  "
            + "\n  ".join(offenders),
        )


class TestTheCheckItselfWorks(unittest.TestCase):
    """A guard that cannot fail is not a guard."""

    def test_a_patched_construction_block_is_caught(self):
        import tempfile, os, textwrap
        source = textwrap.dedent("""
            from unittest.mock import patch
            from tests.world_cache import fresh_world

            def setUp(self):
                with patch('engine.WorldGenerator'):
                    self.world = fresh_world(seed=1, pre_simulate=False)
        """)
        handle, path = tempfile.mkstemp(suffix=".py", text=True)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                f.write(source)
            self.assertEqual(len(_violations(path)), 1)
        finally:
            os.unlink(path)

    def test_an_unrelated_patch_is_left_alone(self):
        import tempfile, os, textwrap
        source = textwrap.dedent("""
            from unittest.mock import patch
            from tests.world_cache import fresh_world

            def setUp(self):
                with patch('engine.World._call_llm'):
                    self.world = fresh_world(seed=1, pre_simulate=False)
        """)
        handle, path = tempfile.mkstemp(suffix=".py", text=True)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                f.write(source)
            self.assertEqual(_violations(path), [])
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
