import json
import unittest

from src.schema_registry import load_schema


class ConfigRowsJsonSerializationTests(unittest.TestCase):
    def test_schema_specs_do_not_contain_none_keys(self):
        schema = load_schema()
        bad = []
        for key, spec in schema.items():
            if any(k is None for k in spec.keys()):
                bad.append(key)
            json.dumps(spec, sort_keys=True)
        self.assertEqual(bad, [])

    def test_medicare_irmaa_descriptions_are_single_schema_field(self):
        schema = load_schema()
        for label in ("part_b_base_premium_monthly", "part_d_base_premium_monthly"):
            spec = schema[("Wellness", "Medicare", label)]
            self.assertIn("prior to IRMAA", spec.get("description", ""))
            self.assertNotIn(None, spec)


if __name__ == "__main__":
    unittest.main()
