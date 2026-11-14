import test from "node:test";
import assert from "node:assert/strict";
import { CLASS8, GROUPS, LIMITS, normalizeSession, deriveSegments, querySegments, parseTelemetry, exportSegmentsCSV, exportSessionJSON, createDemoSession, formatTime } from "../model.mjs";

const vector = (value = 0) => [value, 0, 0, 0, 0];
const frame = (id, start, end, score, dominant = 0.7) => ({ id, start, end, activity: vector(score), dominance: vector(dominant) });
const session = (frames = [frame("f1", 0, 1, 0.8)]) => ({ schema_version: 1, source: { kind: "import", label: "测试" }, track: { id: "track-1", title: "测试曲目", duration: 10, sample_rate: 44100 }, frames, annotations: [] });
const segment = (id, group, start, end, extra = {}) => ({ id, group, groups: [group], start, end, dominance: 0.8, mean: 0.75, peak: 0.9, label: id, ...extra });

test("schema v1 round-trip preserves provenance, metadata and annotation bounds", () => {
  const raw = session();
  raw.annotations = [{ id: "note1", start: 0.2, end: 0.8, label: "主题", groups: ["strings"], notes: "保留注释" }];
  const normalized = normalizeSession(raw);
  assert.deepEqual(normalizeSession(JSON.parse(exportSessionJSON(normalized))), normalized);
  assert.equal(normalized.frames[0].window_end, 1);
  normalized.frames[0].activity[0] = 0;
  assert.equal(raw.frames[0].activity[0], 0.8, "normalization copies arrays");
  assert.equal(GROUPS.length, 5);
  assert.equal(CLASS8.length, 8);
});

test("schema rejects malformed scores, times, ordering, duplicate IDs and coercion", () => {
  for (const mutate of [
    (raw) => { raw.schema_version = 2; },
    (raw) => { raw.frames[0].activity = [0.7]; },
    (raw) => { raw.frames[0].activity[0] = Number.NaN; },
    (raw) => { raw.frames[0].dominance[0] = 1.1; },
    (raw) => { raw.frames[0].end = 0; },
    (raw) => { raw.frames[0].start = -1; },
    (raw) => { raw.frames[0].end = 11; },
    (raw) => { raw.frames[0].start = "0"; },
    (raw) => { raw.frames.push(frame("f1", 1, 2, 0.8)); },
    (raw) => { raw.frames.push(frame("f2", 0, 1.5, 0.8)); },
    (raw) => { raw.frames[0].extra = 1; },
    (raw) => { raw.annotations = [{ id: "n", start: 0, end: 1, label: "x", groups: ["voice"] }]; },
    (raw) => { raw.sample_rate = 48000; },
    (raw) => { raw.track.duration = Infinity; },
    (raw) => { raw.frames[0].activity = Array(5); },
    (raw) => { raw.frames = Array(1); },
  ]) {
    const raw = session(); mutate(raw); assert.throws(() => normalizeSession(raw), TypeError);
  }
  assert.throws(() => normalizeSession(session(Array.from({ length: LIMITS.frames + 1 }, (_, i) => frame(`f${i}`, 0, 1, 1)))), /at most/);
});

test("overlapping analysis windows use latest-start decisions without double counting or resurrecting old windows", () => {
  const frames = [frame("old", 0, 8, 0.8, 0.8), frame("middle", 1, 3, 0.5, 0.4), frame("new", 2, 2.5, 0.7, 0.6), frame("last", 4, 5, 0.8, 0.9)];
  const normalized = normalizeSession(session(frames));
  assert.equal(normalized.frames[0].end, 8, "original overlapping spans survive import");
  const derived = deriveSegments(normalized.frames);
  assert.deepEqual(derived.map(({ start, end }) => [start, end]), [[0, 2.5], [4, 5]]);
  assert.ok(Math.abs(derived[0].mean - (0.8 + 0.5 + 0.7 * 0.5) / 2.5) < 1e-12);
  assert.equal(derived[0].duration, 2.5);
  const silence = [frame("held", 0, 5, 0.9), frame("stop", 1, 2, 0), frame("resume", 2, 3, 0.9)];
  assert.deepEqual(deriveSegments(silence).map(({ start, end }) => [start, end]), [[0, 1], [2, 3]]);
});

test("timestamp/window_end aliases are explicit and cannot disagree", () => {
  const raw = session();
  raw.frames = [{ id: "stamp", timestamp: 2, window_end: 2.4, activity: vector(0.8), dominance: vector(0.9) }];
  const normalized = normalizeSession(raw);
  assert.equal(normalized.frames[0].start, 2);
  assert.equal(normalized.frames[0].end, 2.4);
  raw.frames[0].end = 3;
  assert.throws(() => normalizeSession(raw), /disagree/);
});

test("hysteresis retains middle scores, cuts silence and requires re-entry threshold", () => {
  const frames = [frame("a", 0, 1, 0.59), frame("b", 1, 2, 0.6), frame("c", 2, 3, 0.45), frame("d", 3, 4, 0.39), frame("e", 4, 5, 0.5), frame("f", 5, 6, 0.8)];
  const derived = deriveSegments(frames);
  assert.deepEqual(derived.map(({ start, end }) => [start, end]), [[1, 3], [5, 6]]);
  assert.equal(derived[0].mean, 0.525);
  assert.deepEqual(derived[0].frameIds, ["b", "c"]);
  assert.throws(() => deriveSegments(frames, { on: 0.3, off: 0.5 }), /off/);
});

test("missing observations and explicit silence never bridge or extend past last validity", () => {
  const frames = [frame("a", 0, 1, 0.8), frame("b", 2, 3, 0.9), frame("c", 3, 3.2, 0), frame("d", 3.2, 3.4, 0.9)];
  assert.deepEqual(deriveSegments(frames, { minDuration: 0, maxGap: 20 }).map(({ start, end }) => [start, end]), [[0, 1], [2, 3], [3.2, 3.4]]);
  assert.deepEqual(deriveSegments(frames).map(({ start, end }) => [start, end]), [[0, 1], [2, 3]]);
  assert.deepEqual(deriveSegments(frames, { selectedGroups: [] }), []);
  assert.deepEqual(deriveSegments([frame("zero", 0, 2, 0)], { on: 0, off: 0 }), []);
  assert.deepEqual(deriveSegments([frame("on", 0, 1, 0.8), frame("silence", 1, 2, 0), frame("on2", 2, 3, 0.8)], { off: 0 }).map(({ start, end }) => [start, end]), [[0, 1], [2, 3]]);
});

test("segment means weight explicit duration and dominance is separate", () => {
  const frames = [frame("a", 0, 1, 0.9, 0.2), frame("b", 1, 4, 0.5, 0.6)];
  const [result] = deriveSegments(frames);
  assert.equal(result.mean, 0.6);
  assert.ok(Math.abs(result.dominance - 0.5) < 1e-12);
  assert.equal(result.dominant, true);
});

test("all queries calculate true overlaps, preserve gaps, and filter overlap duration", () => {
  const segments = [segment("s1", "strings", 0, 5), segment("s2", "strings", 8, 10), segment("w1", "woodwinds", 3, 9), segment("b1", "brass", 4, 8.5)];
  const both = querySegments(segments, { groups: ["strings", "woodwinds"], mode: "all" });
  assert.deepEqual(both.map(({ start, end, group }) => [start, end, group]), [[3, 5, null], [8, 9, null]]);
  const triple = querySegments(segments, { groups: ["strings", "woodwinds", "brass"], mode: "all" });
  assert.deepEqual(triple.map(({ start, end }) => [start, end]), [[4, 5], [8, 8.5]]);
  assert.deepEqual(querySegments(segments, { groups: ["strings", "woodwinds"], mode: "all", minDuration: 1.5 }).map(({ start, end }) => [start, end]), [[3, 5]]);
  assert.equal(querySegments(segments, { groups: ["keys", "woodwinds"], mode: "all" }).length, 0);
  assert.equal(querySegments([segment("s", "strings", 0, 1), segment("w", "woodwinds", 1, 2)], { groups: ["strings", "woodwinds"], mode: "all" }).length, 0);
});

test("union handles nested same-group observations without duplicate intersections", () => {
  const segments = [segment("s", "strings", 0, 10), segment("s2", "strings", 2, 3), segment("w", "woodwinds", 1, 4)];
  assert.deepEqual(querySegments(segments, { mode: "all", groups: ["strings", "woodwinds"] }).map(({ start, end }) => [start, end]), [[1, 4]]);
  assert.deepEqual(querySegments(segments, { text: "弦乐", groups: ["strings"] }).map((s) => s.id), ["s", "s2"]);
  assert.equal(querySegments(segments, { groups: ["strings"], dominantOnly: true }).length, 2);
  assert.equal(querySegments([segment("quiet", "keys", 0, 2, { dominance: 0.2 })], { dominantOnly: true }).length, 0);
  assert.throws(() => querySegments(segments, { mode: "some" }), /mode/);
});

test("untagged manual annotations remain searchable and exportable and group filters exclude them", () => {
  const manual = { id: "pause", start: 2, end: 4, duration: 99, label: "短暂停顿", notes: "一般注释", groups: [], kind: "manual" };
  const tagged = segment("strings", "strings", 0, 5);
  const results = querySegments([tagged, manual], {});
  assert.equal(results.length, 2);
  assert.equal(results.find((item) => item.id === "pause").duration, 2);
  assert.deepEqual(querySegments([tagged, manual], { text: "停顿" }).map((item) => item.id), ["pause"]);
  for (const mode of ["any", "all"]) assert.deepEqual(querySegments([tagged, manual], { groups: ["strings"], mode }).map((item) => item.id), ["strings"]);
  const csv = exportSegmentsCSV([manual], { session: session() });
  assert.ok(csv.includes('"短暂停顿"'));
  assert.ok(csv.includes('"一般注释"'));
  assert.throws(() => querySegments([{ ...manual, kind: "generated" }]), /kind:manual/);
  assert.equal(GROUPS.find((group) => group.id === "keys").nameZh, "键盘/拨弦");
});

test("multi-group intersections agree with an independent midpoint coverage oracle", () => {
  let seed = 123456789;
  const random = (max) => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed % max; };
  for (let trial = 0; trial < 100; trial += 1) {
    const groups = ["strings", "woodwinds", "brass"];
    const input = groups.flatMap((group) => Array.from({ length: 5 }, (_, index) => {
      const start = random(20);
      return segment(`${group}-${index}`, group, start, start + 1 + random(5));
    }));
    const result = querySegments(input, { groups, mode: "all" });
    for (let unit = 0; unit < 25; unit += 1) {
      const time = unit + 0.5;
      const expected = groups.every((group) => input.some((item) => item.group === group && item.start <= time && time < item.end));
      const actual = result.some((item) => item.start <= time && time < item.end);
      assert.equal(actual, expected, `trial ${trial}, t=${time}`);
    }
    assert.ok(result.every((item, index) => item.end > item.start && (!index || item.start >= result[index - 1].end)));
  }
});

test("current UART fields stay eight-class events with last-channel percentage intact", () => {
  const raw = "RTOS IMC OK\r\nRTOS NPU top1=5 last_class=3 last_p=87 c=12345 seq=1 tick=250\r\nRTOS NPU TIMEOUT seq=2 tick=253\r\nRTOS HEARTBEAT tick=300 results=1\r\nRTOS NPU top1=0 last_class=7 last_p=0 c=31152090 seq=3 tick=500\r\n";
  const parsed = parseTelemetry(raw);
  assert.equal(parsed.kind, "uart-eight-class");
  assert.equal(parsed.observations.length, 2);
  assert.equal(parsed.observations[0].top1, 5);
  assert.equal(parsed.observations[0].last_class, 3);
  assert.equal(parsed.observations[0].last_p, 87);
  assert.equal(parsed.observations[0].last_class_label, "长笛");
  assert.equal(parsed.observations[0].c, 12345);
  assert.equal(parsed.timeouts.length, 1);
  assert.equal(parsed.heartbeats[0].tick, 300);
  assert.equal(parsed.unknownLines.length, 1);
  for (const event of parsed.observations) for (const forbidden of ["confidence", "activity", "dominance", "frames", "groups", "start", "end"]) assert.equal(forbidden in event, false);
  assert.equal("frames" in parsed, false);
});

test("malformed UART lines stay invalid and uint32 wrap values retain literal fields", () => {
  const parsed = parseTelemetry("RTOS NPU top1=8 last_class=3 last_p=87 c=1 seq=1 tick=2\nRTOS NPU top1=1 last_class=3 last_p=101 c=1 seq=1 tick=2\nRTOS HEARTBEAT tick=0 results=4294967295\nRTOS NPU TIMEOUT seq=1 seq=2 tick=3\nRTOS HEARTBEAT tick=4\nRTOS NPU TIMEOUT seq=4294967296 tick=0");
  assert.equal(parsed.invalidLines.length, 5);
  assert.equal(parsed.heartbeats.length, 1);
  assert.equal(parsed.heartbeats[0].results, 0xffffffff);
  assert.throws(() => parseTelemetry("x".repeat(LIMITS.telemetryBytes + 1)), /telemetry/);
});

test("CSV quotes labels, neutralizes formulas and retains demo provenance", () => {
  const demo = createDemoSession();
  const segments = [segment("csv", "strings", 1, 2, { label: '=HYPERLINK("https://example.test","x")', notes: ' @SUM(1,2)\n中文,"文本"' })];
  const csv = exportSegmentsCSV(segments, { session: demo });
  assert.equal(csv.charCodeAt(0), 0xfeff);
  assert.ok(csv.includes('"\'=HYPERLINK(""https://example.test"",""x"")"'));
  assert.ok(csv.includes('"\' @SUM(1,2)\n中文,""文本"""'));
  assert.ok(csv.includes('"demo"'));
  assert.ok(csv.includes('"90 秒交互演示 · 人工构造数据"'));
  assert.ok(exportSegmentsCSV(segments).includes('"unverified"'));
  assert.throws(() => exportSegmentsCSV([segment("past-end", "strings", 89, 91)], { session: demo }), /beyond/);
});

test("deterministic demo has bounded frames, explicit silence, and provenance on JSON export", () => {
  const demo = createDemoSession();
  assert.deepEqual(demo, createDemoSession());
  assert.equal(demo.source.kind, "demo");
  assert.equal(demo.track.duration, 90);
  assert.equal(demo.frames.length, 180);
  assert.equal(demo.frames.at(-1).end, 90);
  const segments = deriveSegments(demo.frames);
  assert.ok(segments.every((segment) => segment.start >= 0 && segment.end <= 90));
  assert.ok(segments.every((segment) => segment.end <= 42 || segment.start >= 45));
  const tutti = querySegments(segments, { mode: "all", groups: GROUPS.map((g) => g.id) });
  assert.deepEqual(tutti.map(({ start, end }) => [start, end]), [[72, 86]]);
  assert.equal(JSON.parse(exportSessionJSON(demo)).source.kind, "demo");
  assert.equal(formatTime(89.95), "01:29.9");
  assert.equal(formatTime(0), "00:00.0");
  assert.throws(() => formatTime(-1), /seconds/);
});
