import json
import shutil
import tempfile
import unittest
from pathlib import Path

from audit_scope_firmware import EXPERIMENT, EXPECTED_SOURCES, NAME, audit


class ScopeFirmwareTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="scope-firmware-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative in EXPECTED_SOURCES | {"build/" + NAME + ".hex", "build/" + NAME + ".build.json"}:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(EXPERIMENT / relative, target)
        self.firmware = self.root / "build" / (NAME + ".hex")
        self.manifest_path = self.firmware.with_suffix(".build.json")
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8-sig"))
        self.manifest["Hex"] = str(self.firmware)
        self.save()

    def save(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_current_firmware_accepted_without_hardware_claim(self):
        result = audit(self.firmware, self.root)
        self.assertEqual(result["application"], "scope")
        self.assertFalse(result["hardware_validated"])

    def test_wrong_configuration_rejected(self):
        for field in ("ClockHz", "SampleCycles", "TimeoutCycles", "ConsoleDelayCycles", "EnableM"):
            with self.subTest(field=field):
                original = self.manifest[field]
                self.manifest[field] = original + 1
                self.save()
                with self.assertRaisesRegex(ValueError, "Wrong scope configuration"):
                    audit(self.firmware, self.root)
                self.manifest[field] = original

    def test_omitted_source_rejected(self):
        self.manifest["SourceHashes"].pop("sw/scope.c")
        self.save()
        with self.assertRaisesRegex(ValueError, "Incomplete scope source"):
            audit(self.firmware, self.root)

    def test_changed_source_rejected(self):
        (self.root / "sw/scope.c").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Scope source changed"):
            audit(self.firmware, self.root)

    def test_different_image_rejected(self):
        image = self.root / "other.hex"
        image.write_bytes(b"not the tested application")
        with self.assertRaisesRegex(ValueError, "Wrong scope firmware hash"):
            audit(image, self.root)

    def test_wrong_manifest_path_rejected(self):
        self.manifest["Hex"] = str(self.root / "other.hex")
        self.save()
        with self.assertRaisesRegex(ValueError, "Wrong scope firmware path"):
            audit(self.firmware, self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)

