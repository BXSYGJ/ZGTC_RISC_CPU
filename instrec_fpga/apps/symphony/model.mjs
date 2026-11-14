/** Data and interval model shared by the two local symphony applications. */
export const GROUPS = Object.freeze([
  { id: "strings", key: "strings", index: 0, name: "弦乐", nameZh: "弦乐", color: "#d9926f", aliases: ["strings", "string", "弦乐", "提琴"] },
  { id: "woodwinds", key: "woodwinds", index: 1, name: "木管", nameZh: "木管", color: "#83bfa8", aliases: ["woodwinds", "woodwind", "木管"] },
  { id: "brass", key: "brass", index: 2, name: "铜管", nameZh: "铜管", color: "#e2bb65", aliases: ["brass", "铜管"] },
  { id: "percussion", key: "percussion", index: 3, name: "打击乐", nameZh: "打击乐", color: "#af9bd9", aliases: ["percussion", "打击", "打击乐"] },
  { id: "keys", key: "keys", index: 4, name: "键盘/拨弦", nameZh: "键盘/拨弦", color: "#7cafd4", aliases: ["keys", "keyboard", "piano", "plucked", "键盘", "拨弦", "钢琴"] },
].map((group) => Object.freeze({ ...group, aliases: Object.freeze(group.aliases) })));

export const CLASS8 = Object.freeze([
  "单簧管", "失真电吉他", "女声", "长笛", "钢琴", "次中音萨克斯", "小号", "小提琴",
]);
export const LIMITS = Object.freeze({ duration: 86400, frames: 20000, annotations: 5000, text: 2048, telemetryBytes: 2097152, telemetryLines: 30000 });
const IDS = GROUPS.map((group) => group.id);
const BY_ID = new Map(GROUPS.map((group) => [group.id, group]));
const EPS = 1e-9;
const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
const fail = (path, message) => { throw new TypeError(`${path}: ${message}`); };

function object(value, path) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail(path, "expected an object");
  return value;
}
function keys(value, allowed, path) {
  for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(`${path}.${key}`, "unknown field");
}
function number(value, path, min = 0, max = LIMITS.duration) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) fail(path, `expected a finite number in [${min}, ${max}]`);
  return value;
}
function integer(value, path, min = 0, max = 0xffffffff) {
  number(value, path, min, max);
  if (!Number.isSafeInteger(value)) fail(path, "expected an integer");
  return value;
}
function string(value, path, max = LIMITS.text, empty = true) {
  if (typeof value !== "string" || value.length > max || (!empty && !value.trim()) || /\u0000/.test(value)) fail(path, `expected ${empty ? "a" : "a nonempty"} string of at most ${max} characters`);
  return value;
}
function identifier(value, path) {
  string(value, path, 100, false);
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(value)) fail(path, "use letters, digits, dot, underscore, colon or hyphen");
  return value;
}
function scoreVector(value, path) {
  if (!Array.isArray(value) || value.length !== GROUPS.length) fail(path, "expected five scores in fixed GROUPS order");
  return Array.from(value, (score, index) => number(score, `${path}[${index}]`, 0, 1));
}
function groupIds(value, path = "groups", fallback = IDS) {
  if (value === undefined) return [...fallback];
  if (!Array.isArray(value) || value.length > 5) fail(path, "expected at most five group IDs");
  const seen = new Set();
  for (const id of value) {
    if (!BY_ID.has(id) || seen.has(id)) fail(path, "expected unique known group IDs");
    seen.add(id);
  }
  return IDS.filter((id) => seen.has(id));
}
function bounds(value, path, duration = LIMITS.duration) {
  const start = own(value, "start") ? value.start : value.timestamp;
  const end = own(value, "end") ? value.end : value.window_end;
  number(start, `${path}.start`, 0, duration);
  number(end, `${path}.end`, 0, duration);
  if (!(end > start)) fail(path, "end must be greater than start");
  if (own(value, "timestamp") && value.timestamp !== start) fail(path, "timestamp and start disagree");
  if (own(value, "window_end") && value.window_end !== end) fail(path, "window_end and end disagree");
  return { start, end };
}

function normalizeFrames(frames, duration = LIMITS.duration) {
  if (!Array.isArray(frames) || frames.length > LIMITS.frames) fail("frames", `expected at most ${LIMITS.frames} frames`);
  const ids = new Set();
  let previousStart = -1;
  return Array.from(frames, (raw, index) => {
    const path = `frames[${index}]`;
    object(raw, path);
    keys(raw, ["id", "start", "end", "timestamp", "window_end", "activity", "dominance"], path);
    const id = identifier(raw.id, `${path}.id`);
    if (ids.has(id)) fail(`${path}.id`, "duplicate ID");
    ids.add(id);
    const { start, end } = bounds(raw, path, duration);
    if (index && start <= previousStart) fail(path, "frame start times must be strictly increasing");
    previousStart = start;
    return { id, start, end, window_end: end, activity: scoreVector(raw.activity, `${path}.activity`), dominance: scoreVector(raw.dominance, `${path}.dominance`) };
  });
}

/** Schema v1 is strict, finite and bounded. No UART event is accepted as a frame. */
export function normalizeSession(raw) {
  object(raw, "session");
  keys(raw, ["schema_version", "id", "source", "track", "frames", "annotations", "sample_rate", "created_at"], "session");
  if (raw.schema_version !== 1) fail("schema_version", "expected version 1");
  const source = object(raw.source, "source");
  keys(source, ["kind", "label", "description", "model", "model_version", "created_at", "uri"], "source");
  if (!["demo", "import", "inference", "manual"].includes(source.kind)) fail("source.kind", "expected demo, import, inference or manual");
  const normalizedSource = { kind: source.kind };
  for (const key of ["label", "description", "model", "model_version", "created_at", "uri"]) {
    if (own(source, key)) normalizedSource[key] = string(source[key], `source.${key}`);
  }
  const track = object(raw.track, "track");
  keys(track, ["id", "title", "composer", "artist", "duration", "sample_rate", "description"], "track");
  const normalizedTrack = {
    id: identifier(track.id, "track.id"), title: string(track.title, "track.title", 300, false),
    duration: number(track.duration, "track.duration", Number.EPSILON),
  };
  for (const key of ["composer", "artist", "description"]) if (own(track, key)) normalizedTrack[key] = string(track[key], `track.${key}`);
  const sampleRate = track.sample_rate ?? raw.sample_rate;
  if (sampleRate !== undefined) normalizedTrack.sample_rate = integer(sampleRate, "track.sample_rate", 8000, 384000);
  if (own(track, "sample_rate") && own(raw, "sample_rate") && track.sample_rate !== raw.sample_rate) fail("sample_rate", "track and session sample rates disagree");
  const frames = normalizeFrames(raw.frames, track.duration);
  const annotations = raw.annotations ?? [];
  if (!Array.isArray(annotations) || annotations.length > LIMITS.annotations) fail("annotations", `expected at most ${LIMITS.annotations} annotations`);
  const annotationIds = new Set();
  const normalizedAnnotations = Array.from(annotations, (annotation, index) => {
    const path = `annotations[${index}]`;
    object(annotation, path);
    keys(annotation, ["id", "start", "end", "label", "groups", "notes"], path);
    const id = identifier(annotation.id, `${path}.id`);
    if (annotationIds.has(id)) fail(`${path}.id`, "duplicate ID");
    annotationIds.add(id);
    const result = { id, ...bounds(annotation, path, track.duration), label: string(annotation.label, `${path}.label`, 300, false), groups: groupIds(annotation.groups, `${path}.groups`, []) };
    if (own(annotation, "notes")) result.notes = string(annotation.notes, `${path}.notes`);
    return result;
  });
  const result = { schema_version: 1, source: normalizedSource, track: normalizedTrack, frames, annotations: normalizedAnnotations };
  if (own(raw, "id")) result.id = identifier(raw.id, "id");
  if (own(raw, "created_at")) result.created_at = string(raw.created_at, "created_at", 100);
  return result;
}

/**
 * Latest-start windows own their validity until the next window starts.
 * Original frame spans stay intact; effective ends prevent overlap counting.
 * Hysteresis applies only inside that validity. Every uncovered gap splits.
 */
export function deriveSegments(rawFrames, options = {}) {
  object(options, "options");
  const on = number(options.on ?? 0.6, "on", 0, 1);
  const off = number(options.off ?? 0.4, "off", 0, 1);
  if (off > on) fail("off", "must be less than or equal to on");
  const minDuration = number(options.minDuration ?? 0.3, "minDuration");
  // Accepted for caller compatibility; unknown intervals are always split.
  number(options.maxGap ?? 0, "maxGap");
  const selected = groupIds(options.selectedGroups, "selectedGroups");
  const frames = normalizeFrames(rawFrames);
  const output = [];
  for (const id of selected) {
    const group = BY_ID.get(id);
    let active = null;
    const finish = () => {
      if (!active) return;
      const duration = active.end - active.start;
      if (duration + EPS >= minDuration) {
        output.push({ id: `${id}:${active.start}:${active.end}`, group: id, groups: [id], start: active.start, end: active.end, window_end: active.end, duration, peak: active.peak, mean: active.total / active.coverage, dominance: active.dominance / active.coverage, dominant: active.dominance / active.coverage + EPS >= 0.5, label: group.name, frameIds: active.frameIds });
      }
      active = null;
    };
    for (let index = 0; index < frames.length; index += 1) {
      const frame = frames[index];
      const effectiveEnd = Math.min(frame.end, frames[index + 1]?.start ?? frame.end);
      if (active && frame.start > active.end) finish();
      const score = frame.activity[group.index];
      if (active && (score < off || score === 0)) finish();
      if (!active && score > 0 && score >= on) active = { start: frame.start, end: frame.start, coverage: 0, total: 0, dominance: 0, peak: 0, frameIds: [] };
      if (active) {
        const duration = effectiveEnd - frame.start;
        active.end = effectiveEnd;
        active.coverage += duration;
        active.total += score * duration;
        active.dominance += frame.dominance[group.index] * duration;
        active.peak = Math.max(active.peak, score);
        active.frameIds.push(frame.id);
      }
    }
    finish();
  }
  return output.sort((a, b) => a.start - b.start || a.end - b.end || IDS.indexOf(a.group) - IDS.indexOf(b.group));
}

function checkedSegments(segments) {
  if (!Array.isArray(segments) || segments.length > LIMITS.frames * GROUPS.length) fail("segments", "invalid or excessive segment count");
  return Array.from(segments, (segment, index) => {
    object(segment, `segments[${index}]`);
    const { start, end } = bounds(segment, `segments[${index}]`);
    const groups = groupIds(segment.groups ?? (segment.group ? [segment.group] : []));
    if (!groups.length && segment.kind !== "manual") fail(`segments[${index}].groups`, "expected a group or kind:manual annotation");
    if (segment.dominance !== undefined) number(segment.dominance, "dominance", 0, 1);
    if (segment.peak !== undefined) number(segment.peak, "peak", 0, 1);
    if (segment.mean !== undefined) number(segment.mean, "mean", 0, 1);
    return { ...segment, groups, start, end, duration: end - start };
  });
}
function searchable(segment) {
  return [segment.label ?? "", segment.notes ?? "", ...segment.groups.flatMap((id) => BY_ID.get(id).aliases)].join(" ").toLocaleLowerCase();
}

/** all means positive-duration simultaneous intersection of every chosen group. */
export function querySegments(rawSegments, options = {}) {
  object(options, "options");
  const groups = groupIds(options.groups, "groups", []);
  const mode = options.mode ?? "any";
  if (!["any", "all"].includes(mode)) fail("mode", "expected any or all");
  const minDuration = number(options.minDuration ?? 0, "minDuration");
  const text = string(options.text ?? "", "text", 300).trim().toLocaleLowerCase();
  const tokens = text.split(/\s+/u).filter(Boolean);
  if (options.dominantOnly !== undefined && typeof options.dominantOnly !== "boolean") fail("dominantOnly", "expected boolean");
  const segments = checkedSegments(rawSegments).filter((segment) => !options.dominantOnly || (segment.dominance ?? 0) + EPS >= 0.5);
  let result;
  if (mode !== "all" || groups.length < 2) {
    result = segments.filter((segment) => !groups.length || groups.some((id) => segment.groups.includes(id)));
  } else {
    // Union within each group, then intersect. Union never spans a gap.
    const perGroup = groups.map((id) => {
      const union = [];
      for (const segment of segments.filter((item) => item.groups.includes(id)).sort((a, b) => a.start - b.start)) {
        const last = union.at(-1);
        if (last && segment.start <= last.end) { last.end = Math.max(last.end, segment.end); last.sources.push(segment); }
        else union.push({ start: segment.start, end: segment.end, sources: [segment] });
      }
      return union;
    });
    const positions = groups.map(() => 0);
    result = [];
    while (perGroup.every((items, index) => positions[index] < items.length)) {
      const windows = perGroup.map((items, index) => items[positions[index]]);
      const start = Math.max(...windows.map((item) => item.start));
      const end = Math.min(...windows.map((item) => item.end));
      if (end > start) {
        const sources = [...new Set(windows.flatMap((item) => item.sources).filter((item) => item.start < end && item.end > start))];
        const metrics = (key) => Math.min(...sources.map((item) => item[key] ?? 0));
        result.push({ id: `all:${groups.join("+")}:${start}:${end}`, group: null, groups: [...groups], start, end, window_end: end, duration: end - start, label: groups.map((id) => BY_ID.get(id).name).join(" · "), notes: sources.map((item) => [item.label, item.notes].filter(Boolean).join(" ")).join(" / "), peak: metrics("peak"), mean: metrics("mean"), dominance: metrics("dominance"), dominant: sources.every((item) => (item.dominance ?? 0) + EPS >= 0.5), metricKind: "minimum-of-source-segments", sourceIds: [...new Set(sources.map((item) => item.id).filter(Boolean))], frameIds: [...new Set(sources.flatMap((item) => item.frameIds ?? []))] });
      }
      const earliest = Math.min(...windows.map((item) => item.end));
      windows.forEach((item, index) => { if (item.end === earliest) positions[index] += 1; });
    }
  }
  return result.filter((segment) => segment.duration + EPS >= minDuration && tokens.every((token) => searchable(segment).includes(token))).sort((a, b) => a.start - b.start || a.end - b.end);
}

/** These events are eight-class hardware observations, not group5 frames. */
export function parseTelemetry(text) {
  string(text, "telemetry", LIMITS.telemetryBytes);
  const lines = text.split(/\r\n|\n|\r/);
  if (lines.length > LIMITS.telemetryLines) fail("telemetry", "too many lines");
  const result = { schema_version: 1, kind: "uart-eight-class", source: { kind: "uart-eight-class", label: "125 MHz FreeRTOS UART" }, observations: [], heartbeats: [], timeouts: [], events: [], unknownLines: [], invalidLines: [] };
  for (let index = 0; index < lines.length; index += 1) {
    const raw = lines[index].trim();
    if (!raw) continue;
    const line = index + 1;
    const match = /^(RTOS NPU TIMEOUT|RTOS NPU|RTOS HEARTBEAT)\s+(.+)$/.exec(raw);
    if (!match) { result.unknownLines.push({ line, raw }); continue; }
    try {
      const fields = {};
      for (const token of match[2].split(/\s+/)) {
        const pair = /^([a-z0-9_]+)=(\d+)$/.exec(token);
        if (!pair || own(fields, pair[1])) fail("UART", "malformed or duplicate field");
        fields[pair[1]] = integer(Number(pair[2]), pair[1]);
      }
      const event = { line, raw };
      if (match[1] === "RTOS NPU") {
        keys(fields, ["top1", "last_class", "last_p", "c", "seq", "tick"], "UART NPU");
        for (const key of ["top1", "last_class", "last_p", "c", "seq", "tick"]) if (!own(fields, key)) fail("UART NPU", `missing ${key}`);
        integer(fields.top1, "top1", 0, 7); integer(fields.last_class, "last_class", 0, 7); integer(fields.last_p, "last_p", 0, 100);
        Object.assign(event, { type: "npu", ...fields, top1_label: CLASS8[fields.top1], last_class_label: CLASS8[fields.last_class] });
        result.observations.push(event);
      } else if (match[1] === "RTOS NPU TIMEOUT") {
        keys(fields, ["seq", "tick"], "UART TIMEOUT");
        for (const key of ["seq", "tick"]) if (!own(fields, key)) fail("UART TIMEOUT", `missing ${key}`);
        Object.assign(event, { type: "timeout", ...fields });
        result.timeouts.push(event);
      } else {
        keys(fields, ["tick", "results"], "UART HEARTBEAT");
        for (const key of ["tick", "results"]) if (!own(fields, key)) fail("UART HEARTBEAT", `missing ${key}`);
        Object.assign(event, { type: "heartbeat", ...fields });
        result.heartbeats.push(event);
      }
      result.events.push(event);
    } catch (error) { result.invalidLines.push({ line, raw, reason: error.message }); }
  }
  return result;
}

function csvCell(value) {
  let text = value === undefined || value === null ? "" : String(value);
  // Quoting alone does not prevent spreadsheet formula evaluation.
  if (typeof value === "string" && (/^[\s\uFEFF]*[=+@-]/u.test(text) || /^[\t\r\n]/.test(text))) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
export function exportSegmentsCSV(rawSegments, { session } = {}) {
  const segments = checkedSegments(rawSegments);
  const normalized = session ? normalizeSession(session) : null;
  if (normalized && segments.some((segment) => segment.end > normalized.track.duration)) fail("segments", "segment extends beyond the exported track");
  const headings = ["start_seconds", "end_seconds", "duration_seconds", "groups", "group_names", "label", "notes", "activity_mean", "activity_peak", "dominance", "source_kind", "source_label", "track_id", "track_title"];
  const rows = segments.map((segment) => [segment.start, segment.end, segment.duration, segment.groups.join("|"), segment.groups.map((id) => BY_ID.get(id).name).join("|"), segment.label ?? "", segment.notes ?? "", segment.mean ?? "", segment.peak ?? "", segment.dominance ?? "", normalized?.source.kind ?? "unverified", normalized?.source.label ?? "", normalized?.track.id ?? "", normalized?.track.title ?? ""]);
  return "\uFEFF" + [headings, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
export function exportSessionJSON(session) { return JSON.stringify(normalizeSession(session), null, 2) + "\n"; }
export function formatTime(seconds) {
  number(seconds, "seconds");
  const tenths = Math.floor((seconds + EPS) * 10);
  const minutes = Math.floor(tenths / 600);
  return `${String(minutes).padStart(2, "0")}:${String(Math.floor(tenths / 10) % 60).padStart(2, "0")}.${tenths % 10}`;
}

/** Illustrative score data only. The source declaration survives JSON and CSV. */
export function createDemoSession() {
  const cues = [
    [0, 16, [0.87, 0.20, 0.04, 0.03, 0.08], [0.85, 0.08, 0.03, 0.02, 0.02]],
    [16, 30, [0.68, 0.88, 0.05, 0.08, 0.12], [0.27, 0.65, 0.03, 0.02, 0.03]],
    [30, 42, [0.80, 0.68, 0.89, 0.74, 0.10], [0.23, 0.12, 0.59, 0.04, 0.02]],
    [42, 45, [0.03, 0.02, 0.01, 0.01, 0.02], [0.05, 0.05, 0.05, 0.05, 0.05]],
    [45, 57, [0.46, 0.14, 0.04, 0.05, 0.90], [0.12, 0.04, 0.02, 0.02, 0.80]],
    [57, 72, [0.88, 0.78, 0.34, 0.68, 0.74], [0.61, 0.19, 0.04, 0.04, 0.12]],
    [72, 86, [0.91, 0.81, 0.94, 0.88, 0.73], [0.22, 0.09, 0.58, 0.08, 0.03]],
    [86, 90, [0.72, 0.28, 0.15, 0.13, 0.22], [0.79, 0.08, 0.05, 0.04, 0.04]],
  ];
  const frames = Array.from({ length: 180 }, (_, index) => {
    const start = index * 0.5;
    const cue = cues.find(([begin, end]) => start >= begin && start < end);
    return { id: `demo-frame-${String(index).padStart(3, "0")}`, start, end: start + 0.5, activity: cue[2].map((value, group) => Number(Math.max(0, Math.min(1, value + Math.sin(index * 0.31 + group) * 0.025)).toFixed(4))), dominance: [...cue[3]] };
  });
  return normalizeSession({ schema_version: 1, id: "symphony-demo-90", source: { kind: "demo", label: "90 秒交互演示 · 人工构造数据", description: "本示例展示声部导览、重叠检索与标注流程；分数和时间段为确定性演示数据。", model: "illustrative-script-v1" }, track: { id: "demo-orchestra", title: "交响乐的九十秒", composer: "交互示例", duration: 90, sample_rate: 44100 }, frames, annotations: [{ id: "demo-intro", start: 0, end: 16, label: "弦乐主题", groups: ["strings"], notes: "关注主旋律的进入与持续。" }, { id: "demo-dialogue", start: 16, end: 30, label: "木管与弦乐对话", groups: ["strings", "woodwinds"], notes: "可用“同时出现”检索两组声部的重叠。" }, { id: "demo-pause", start: 42, end: 45, label: "短暂停顿", groups: [], notes: "显式静音切开前后片段。" }, { id: "demo-tutti", start: 72, end: 86, label: "全奏与高潮", groups: [...IDS], notes: "五组活动重叠，铜管主导。" }] });
}
