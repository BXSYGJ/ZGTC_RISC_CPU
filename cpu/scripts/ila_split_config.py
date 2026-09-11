import re

from ila_analyze import header_for


DATA_NAMES = tuple(header_for("Target132Kept")[1:])
TRIGGER_NAMES = DATA_NAMES[:32] + ("board/soc/core/ex_fire",)
CORE_PROPERTIES = {
    "clockChannel": "cpu_clk", "clockEdge": "Rising", "ramType": "1",
    "dataDepth": "1024", "dataEqualsTrigger": "false", "dataPortWidth": "109",
    "enablePowerOnInitData": "false", "enableStorageQualification": "false",
    "triggerSequencerLevels": "1", "enableMultiWindow": "false", "triggerPortCount": "1",
    "triggerMatchCount<0>": "1", "triggerMatchCountWidth<0>": "0",
    "triggerMatchType<0>": "0", "triggerPortIsData<0>": "true", "triggerPortWidth<0>": "33",
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
            raise ValueError("Split ILA property mismatch: " + name)
    expected_data = {f"Project.unit<0>.dataChannel<{index}>": name for index, name in enumerate(DATA_NAMES)}
    expected_trigger = {f"Project.unit<0>.triggerChannel<0><{index}>": name for index, name in enumerate(TRIGGER_NAMES)}
    actual_data = {key: value for key, value in properties.items() if ".dataChannel<" in key}
    actual_trigger = {key: value for key, value in properties.items() if ".triggerChannel<" in key}
    if actual_data != expected_data:
        raise ValueError("Split ILA 109-channel data map mismatch")
    if actual_trigger != expected_trigger:
        raise ValueError("Split ILA 33-channel trigger map mismatch")
    if verified_output is not None:
        normalized = verified_output.replace("\r\n", "\n")
        for label, names in (("Data", DATA_NAMES), ("Trigger", TRIGGER_NAMES)):
            matches = re.findall(r"^" + label + r" Channel (\d+):[^\S\n]*([^\n]+)$", normalized, re.MULTILINE)
            actual = [(int(index), name.strip()) for index, name in matches]
            expected = list(enumerate(names)) * (2 if label == "Trigger" else 1)
            if actual != expected:
                raise ValueError("Actual Inserter " + label + " map mismatch")
        for label, value in (("Clock Port channel", "cpu_clk"), ("Data Same As Trigger", "0"),
                             ("Data Max Depth", "1024"), ("Trigger At Clock Edge", "1")):
            matches = re.findall(r"^" + re.escape(label) + r":[^\S\n]*([^\n]+)$", normalized, re.MULTILINE)
            if [match.strip() for match in matches] != [value]:
                raise ValueError("Actual Inserter configuration mismatch: " + label)
        if re.search(r"^\s*(?:E:|Error:)", normalized, re.MULTILINE):
            raise ValueError("Actual Inserter error output")
    return {"data_channels": 109, "trigger_channels": 33, "depth": 1024,
            "clock": "cpu_clk", "trigger": "full_EX_PC_and_ex_fire_basic_match",
            "data_map_unchanged": True, "hardware_validated": False}
