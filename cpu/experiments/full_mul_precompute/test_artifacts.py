import json
from pathlib import Path
import shutil
import tempfile
import unittest

from audit_short import ROOT, read_run


class ArtifactTests(unittest.TestCase):
    def test_artifact_tampering_rejected(self):
        source = ROOT / "build/compiled/20260910-182155-21b1a5a3"
        names = ("firmware.hex", "coremark.sim.uart", "result.json", "objects/Vrv32_soc", "source/rtl/rv32_core.sv")
        with tempfile.TemporaryDirectory(prefix="precompute-artifact-") as temporary:
            work = Path(temporary)
            for name in ("manifest.json", "firmware.hex", "coremark.sim.uart", "result.json", "objects/Vrv32_soc"):
                destination = work / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, destination)
            shutil.copytree(source / "source", work / "source")
            read_run(work)
            for name in names:
                with self.subTest(name=name):
                    destination = work / name
                    contents = destination.read_bytes()
                    destination.write_bytes(contents + b"tampered")
                    with self.assertRaises(ValueError):
                        read_run(work)
                    destination.write_bytes(contents)
            manifest_path = work / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["SimulationPassed"] = False
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                read_run(work)


if __name__ == "__main__":
    unittest.main(verbosity=2)

