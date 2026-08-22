import json
from pathlib import Path
import unittest

from engine.step_executor import SequenceExecutor


class _Backend:
    def all_outputs_off(self): pass
    def close(self): pass


class RecipeCompatibilityTests(unittest.TestCase):
    def test_all_saved_recipes_validate_for_pendant_executor(self):
        recipe_dir = Path(__file__).resolve().parents[1] / "recipes"
        for path in recipe_dir.glob("*.json"):
            with self.subTest(recipe=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                executor = SequenceExecutor(
                    _Backend(), safe_off_on_stop=False,
                    position_points=data.get("position_points", {}),
                )
                executor.validate_sequences(data.get("sequence", {}))


if __name__ == "__main__":
    unittest.main()
