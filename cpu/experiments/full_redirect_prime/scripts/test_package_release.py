import json
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from package_release import MANIFEST, safe_name, source_file, verify_package, write_package


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.archive = self.root / "snapshot.zip"

    def test_roundtrip_and_no_overwrite(self):
        result = write_package({"cpu/docs/中文.md": "中文证据".encode(), "cpu/rtl/top.sv": b"module top; endmodule"}, self.archive)
        self.assertEqual(result["files"], 2)
        self.assertEqual(verify_package(self.archive), result)
        with self.assertRaises(FileExistsError):
            write_package({"different": b"data"}, self.archive)

    def test_unsafe_names(self):
        for name in ("../outside", "/outside", "C:/outside", "a\\b", "a/../b", "a//b", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_name(name)

    def test_mutations(self):
        write_package({"cpu/source": b"original"}, self.archive)
        with zipfile.ZipFile(self.archive) as archive:
            original = {name: archive.read(name) for name in archive.namelist()}
        for mutation in ("payload", "size", "missing", "extra", "duplicate_manifest_list", "status"):
            with self.subTest(mutation=mutation):
                changed = dict(original)
                manifest = json.loads(changed[MANIFEST])
                if mutation == "payload":
                    changed["cpu/source"] = b"modified"
                elif mutation == "size":
                    manifest["files"][0]["bytes"] += 1
                elif mutation == "missing":
                    del changed["cpu/source"]
                elif mutation == "extra":
                    changed["unlisted"] = b"extra"
                elif mutation == "duplicate_manifest_list":
                    manifest["files"].append(manifest["files"][0])
                else:
                    manifest["status"] = "fully_accepted"
                changed[MANIFEST] = json.dumps(manifest).encode()
                target = self.root / (mutation + ".zip")
                with zipfile.ZipFile(target, "x") as archive:
                    for name, data in changed.items():
                        archive.writestr(name, data)
                with self.assertRaises(ValueError):
                    verify_package(target)

    def test_duplicate_archive_entry(self):
        write_package({"cpu/source": b"original"}, self.archive)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.archive, "a") as archive:
                archive.writestr("cpu/source", b"replacement")
        with self.assertRaises(ValueError):
            verify_package(self.archive)

    def test_symlink_and_missing_source(self):
        (self.root / "real").write_bytes(b"data")
        (self.root / "link").symlink_to(self.root / "real")
        with self.assertRaises(ValueError):
            source_file(self.root, "link")
        with self.assertRaises(ValueError):
            source_file(self.root, "missing")

    def test_reserved_manifest(self):
        with self.assertRaises(ValueError):
            write_package({MANIFEST: b"forged"}, self.archive)


if __name__ == "__main__":
    unittest.main()
