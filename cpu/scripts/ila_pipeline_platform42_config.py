import re
from ila_pipeline_minimal_config import DATA_NAMES

PROFILE = "RegfileFanout157500Platform42"
CORE_PROPERTIES = {
    "clockChannel": "cpu_clk", "clockEdge": "Rising", "ramType": "1",
    "dataDepth": "1024", "dataEqualsTrigger": "true",
    "enablePowerOnInitData": "false", "enableStorageQualification": "false",
    "triggerSequencerLevels": "1", "enableMultiWindow": "false", "triggerPortCount": "1",
    "triggerMatchCount<0>": "1", "triggerMatchCountWidth<0>": "0",
    "triggerMatchType<0>": "1", "triggerPortIsData<0>": "true", "triggerPortWidth<0>": "42",
}


def validate_config(text, verified_output=None):
    properties = {}
    for line in text.splitlines():
        if not line.startswith("Project."):
            continue
        key, value = line.split("=", 1)
        if key in properties:
            raise ValueError("Duplicate FIC property: " + key)
        properties[key] = value.strip()
    if properties.get("Project.unit.dimension") != "1":
        raise ValueError("Expected one debug core")
    for name, value in CORE_PROPERTIES.items():
        if properties.get("Project.unit<0>." + name) != value:
            raise ValueError("Platform42 ILA property mismatch: " + name)
    actual = {key: value for key, value in properties.items() if ".triggerChannel<" in key}
    expected = {f"Project.unit<0>.triggerChannel<0><{index}>": name for index, name in enumerate(DATA_NAMES)}
    if actual != expected:
        raise ValueError("Platform42 ILA shared 42-channel map mismatch")
    if any(".dataChannel<" in key or key.endswith(".dataPortWidth") for key in properties):
        raise ValueError("Platform42 forbids separate data map")
    if verified_output is not None:
        normalized = verified_output.replace("\r\n", "\n")
        actual = [(int(index), name.strip()) for index, name in re.findall(r"^Trigger Channel (\d+):[^\S\n]*([^\n]+)$", normalized, re.MULTILINE)]
        if actual != list(enumerate(DATA_NAMES)) * 2:
            raise ValueError("Actual Inserter shared trigger/data map mismatch")
        if re.search(r"^Data Channel \d+:", normalized, re.MULTILINE):
            raise ValueError("Unexpected separate Inserter data channel")
        for label, value in (("Clock Port channel", "cpu_clk"), ("Data Same As Trigger", "1"),
                             ("Data Max Depth", "1024"), ("Trigger At Clock Edge", "1")):
            matches = re.findall(r"^" + re.escape(label) + r":[^\S\n]*([^\n]+)$", normalized, re.MULTILINE)
            if [match.strip() for match in matches] != [value]:
                raise ValueError("Actual Inserter configuration mismatch: " + label)
        if re.search(r"^\s*(?:E:|Error:)", normalized, re.MULTILINE):
            raise ValueError("Actual Inserter error output")
    return dict(data_channels=42, trigger_channels=42, depth=1024, clock="cpu_clk",
                trigger="shared_data_and_basic_with_edges_42_bit_match", full_ex_pc_preserved=True,
                hardware_validated=False, platform_capture_verified=False)

