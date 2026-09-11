import re




DATA_NAMES = (
    "board/soc/core/ex_pc[0]",
    "board/soc/core/ex_pc[1]",
    "board/soc/core/ex_pc[2]",
    "board/soc/core/ex_pc[3]",
    "board/soc/core/ex_pc[4]",
    "board/soc/core/ex_pc[5]",
    "board/soc/core/ex_pc[6]",
    "board/soc/core/ex_pc[7]",
    "board/soc/core/ex_pc[8]",
    "board/soc/core/ex_pc[9]",
    "board/soc/core/ex_pc[10]",
    "board/soc/core/ex_pc[11]",
    "board/soc/core/ex_pc[12]",
    "board/soc/core/ex_pc[13]",
    "board/soc/core/ex_pc[14]",
    "board/soc/core/ex_pc[15]",
    "board/soc/core/ex_pc[16]",
    "board/soc/core/ex_pc[17]",
    "board/soc/core/ex_pc[18]",
    "board/soc/core/ex_pc[19]",
    "board/soc/core/ex_pc[20]",
    "board/soc/core/ex_pc[21]",
    "board/soc/core/ex_pc[22]",
    "board/soc/core/ex_pc[23]",
    "board/soc/core/ex_pc[24]",
    "board/soc/core/ex_pc[25]",
    "board/soc/core/ex_pc[26]",
    "board/soc/core/ex_pc[27]",
    "board/soc/core/ex_pc[28]",
    "board/soc/core/ex_pc[29]",
    "board/soc/core/ex_pc[30]",
    "board/soc/core/ex_pc[31]",
    "board/soc/core/pipeline_valid[0]",
    "board/soc/core/pipeline_valid[1]",
    "board/soc/core/pipeline_valid[2]",
    "board/soc/unused_pipeline_valid[3]",
    "board/soc/core/board/unused_trace_valid",
    "board/soc/core/id_fire",
    "board/soc/core/ex_fire",
    "board/soc/core/mem_flush",
    "board/soc/core/fetch_complete",
    "board/soc/core/mem_fire"
)
TRIGGER_NAMES = DATA_NAMES[:32] + ("board/soc/core/ex_fire",)
CORE_PROPERTIES = {
    "clockChannel": "cpu_clk", "clockEdge": "Rising", "ramType": "1",
    "dataDepth": "1024", "dataEqualsTrigger": "false", "dataPortWidth": "42",
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
            raise ValueError("Minimal ILA property mismatch: " + name)
    expected_data = {f"Project.unit<0>.dataChannel<{index}>": name for index, name in enumerate(DATA_NAMES)}
    expected_trigger = {f"Project.unit<0>.triggerChannel<0><{index}>": name for index, name in enumerate(TRIGGER_NAMES)}
    actual_data = {key: value for key, value in properties.items() if ".dataChannel<" in key}
    actual_trigger = {key: value for key, value in properties.items() if ".triggerChannel<" in key}
    if actual_data != expected_data:
        raise ValueError("Minimal ILA 42-channel data map mismatch")
    if actual_trigger != expected_trigger:
        raise ValueError("Minimal ILA 33-channel trigger map mismatch")
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
    return {"data_channels": 42, "trigger_channels": 33, "depth": 1024,
            "clock": "cpu_clk", "trigger": "full_EX_PC_and_ex_fire_basic_match",
            "full_ex_pc_preserved": True, "hardware_validated": False}
