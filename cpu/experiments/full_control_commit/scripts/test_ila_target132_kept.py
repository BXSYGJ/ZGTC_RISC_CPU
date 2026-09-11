import json
import unittest

import test_ila_target132_carry
from ila_analyze import header_for, validate_manifest


class KeptIlaTests(test_ila_target132_carry.CarryIlaTests):
    profile = "Target132Kept"
    source_lock = "ila_target132_kept_sources.json"
    fic_template = "cpu_ila_target132_kept.fic.in"

    def test_same_channels_do_not_authorize_old_source(self):
        self.assertEqual(header_for(self.profile), header_for("Target132Carry"))
        with self.assertRaisesRegex(ValueError, "Profile"):
            validate_manifest(self.manifest_path, "Target132Carry")
        self.manifest["Profile"] = "Target132Carry"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "source revision"):
            validate_manifest(self.manifest_path, "Target132Carry")

    def test_old_lock_cannot_be_relabelled_as_kept(self):
        old_lock = json.loads((test_ila_target132_carry.PROJECT / "scripts" /
                               "ila_target132_carry_sources.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(set(old_lock), set(self.source["SourceSnapshot"]["Files"]))
        self.assertEqual(sorted(name for name in old_lock
                                if old_lock[name] != self.source["SourceSnapshot"]["Files"][name]),
                         ["rtl/rv32_alu.sv", "rtl/rv32_cache.sv"])
        self.source["SourceSnapshot"]["Files"] = old_lock
        (self.root / "source-manifest.json").write_text(json.dumps(self.source), encoding="utf-8")
        self.rehash("SourceManifestSha256")
        with self.assertRaisesRegex(ValueError, "source revision"):
            validate_manifest(self.manifest_path, self.profile)


if __name__ == "__main__":
    unittest.main()
