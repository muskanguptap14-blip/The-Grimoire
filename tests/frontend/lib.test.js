const test = require("node:test");
const assert = require("node:assert/strict");
const L = require("../../src/grimoire/dashboard/static/lib.js");

test("severity order, labels and icons", () => {
  assert.deepEqual(L.SEVERITIES, ["CRITICAL", "ERROR", "WARNING", "INFO"]);
  assert.equal(L.severityRank("CRITICAL"), 0);
  assert.equal(L.severityRank("INFO"), 3);
  assert.equal(L.severityRank("bogus"), 4);
  assert.equal(L.severityLabel("WARNING"), "Warning");
  assert.equal(L.severityLabel("x"), "x");
  const icons = new Set(L.SEVERITIES.map(L.severityIcon));
  assert.equal(icons.size, 4, "each severity has a distinct icon");
  assert.equal(L.severityIcon("x"), "?");
});

test("countBySeverity handles empty, null and unknown severities", () => {
  assert.deepEqual(L.countBySeverity([]), { CRITICAL: 0, ERROR: 0, WARNING: 0, INFO: 0 });
  assert.deepEqual(L.countBySeverity(null), { CRITICAL: 0, ERROR: 0, WARNING: 0, INFO: 0 });
  const c = L.countBySeverity([{ severity: "ERROR" }, { severity: "ERROR" }, { severity: "INFO" }, { severity: "nope" }]);
  assert.deepEqual(c, { CRITICAL: 0, ERROR: 2, WARNING: 0, INFO: 1 });
});

test("aggregateBy sorts by count then key", () => {
  const r = L.aggregateBy([{ c: "b" }, { c: "a" }, { c: "b" }, { c: "z" }], "c");
  assert.deepEqual(r, [{ key: "b", count: 2 }, { key: "a", count: 1 }, { key: "z", count: 1 }]);
  assert.deepEqual(L.aggregateBy(undefined, "c"), []);
});

test("barPercent clamps and keeps small values visible", () => {
  assert.equal(L.barPercent(5, 10), 50);
  assert.equal(L.barPercent(10, 10), 100);
  assert.equal(L.barPercent(20, 10), 100);
  assert.equal(L.barPercent(1, 1000), 2);
  assert.equal(L.barPercent(0, 10), 0);
  assert.equal(L.barPercent(5, 0), 0);
  assert.equal(L.barPercent(-1, 10), 0);
  assert.equal(L.barPercent(NaN, 10), 0);
});

test("severitySegments", () => {
  assert.deepEqual(L.severitySegments({ CRITICAL: 0, ERROR: 0, WARNING: 0, INFO: 0 }), []);
  assert.deepEqual(L.severitySegments(null), []);
  const s = L.severitySegments({ CRITICAL: 1, ERROR: 0, WARNING: 3, INFO: 0 });
  assert.deepEqual(s.map((x) => x.severity), ["CRITICAL", "WARNING"]);
  assert.equal(s[0].percent, 25);
  assert.equal(s[1].percent, 75);
});

test("classifyDiffLine", () => {
  assert.equal(L.classifyDiffLine("+++ b/x.py"), "meta");
  assert.equal(L.classifyDiffLine("--- a/x.py"), "meta");
  assert.equal(L.classifyDiffLine("@@ -1,2 +1,2 @@"), "hunk");
  assert.equal(L.classifyDiffLine("+print('x')"), "add");
  assert.equal(L.classifyDiffLine("-print 'x'"), "del");
  assert.equal(L.classifyDiffLine(" context"), "ctx");
  assert.equal(L.classifyDiffLine(""), "ctx");
  assert.equal(L.classifyDiffLine(undefined), "ctx");
});

test("parseDiff and diffStats", () => {
  const text = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n+c\n";
  const lines = L.parseDiff(text);
  assert.equal(lines.length, 6);
  assert.deepEqual(L.diffStats(text), { added: 2, removed: 1 });
  assert.deepEqual(L.parseDiff(""), []);
  assert.deepEqual(L.parseDiff(null), []);
  assert.deepEqual(L.diffStats(""), { added: 0, removed: 0 });
});

test("splitDiffByFile", () => {
  const text = "--- a/one.py\n+++ b/one.py\n@@ -1 +1 @@\n-a\n+b\n--- a/dir/two.py\n+++ b/dir/two.py\n@@ -1 +1 @@\n-c\n+d\n";
  const parts = L.splitDiffByFile(text);
  assert.deepEqual(Object.keys(parts), ["one.py", "dir/two.py"]);
  assert.equal(parts["one.py"][0], "--- a/one.py");
  assert.ok(parts["dir/two.py"].includes("+d"));
  assert.ok(!parts["one.py"].includes("+d"));
  assert.deepEqual(L.splitDiffByFile(""), {});
});

test("formatDuration", () => {
  assert.equal(L.formatDuration(0), "0 ms");
  assert.equal(L.formatDuration(0.25), "250 ms");
  assert.equal(L.formatDuration(1.5), "1.50 s");
  assert.equal(L.formatDuration(12.34), "12.3 s");
  assert.equal(L.formatDuration(65), "1 m 05 s");
  assert.equal(L.formatDuration(119.7), "2 m 00 s");
  assert.equal(L.formatDuration(null), "n/a");
  assert.equal(L.formatDuration(undefined), "n/a");
  assert.equal(L.formatDuration(-1), "n/a");
  assert.equal(L.formatDuration(NaN), "n/a");
  assert.equal(L.formatDuration("3"), "n/a");
});

test("formatNumber and formatBytes and plural", () => {
  assert.equal(L.formatNumber(0), "0");
  assert.equal(L.formatNumber(999), "999");
  assert.equal(L.formatNumber(1000), "1,000");
  assert.equal(L.formatNumber(1234567), "1,234,567");
  assert.equal(L.formatNumber(-4321), "-4,321");
  assert.equal(L.formatNumber(NaN), "0");
  assert.equal(L.formatNumber("x"), "0");
  assert.equal(L.formatBytes(0), "0 B");
  assert.equal(L.formatBytes(1023), "1023 B");
  assert.equal(L.formatBytes(2048), "2.0 KB");
  assert.equal(L.formatBytes(50 * 1024 * 1024), "50.0 MB");
  assert.equal(L.formatBytes(-1), "0 B");
  assert.equal(L.plural(1, "file"), "file");
  assert.equal(L.plural(2, "file"), "files");
  assert.equal(L.plural(0, "match", "matches"), "matches");
});

test("outcomePresentation covers all outcomes and unknown", () => {
  assert.equal(L.outcomePresentation("SUCCESS").tone, "success");
  assert.equal(L.outcomePresentation("PARTIAL").tone, "partial");
  assert.equal(L.outcomePresentation("FAILURE").tone, "failure");
  const icons = new Set(["SUCCESS", "PARTIAL", "FAILURE"].map((o) => L.outcomePresentation(o).icon));
  assert.equal(icons.size, 3);
  assert.equal(L.outcomePresentation("???").label, "Unknown");
  assert.equal(L.outcomePresentation(undefined).tone, "failure");
});

test("groupStatus", () => {
  assert.equal(L.groupStatus([]), "pending");
  assert.equal(L.groupStatus(["pending", "pending"]), "pending");
  assert.equal(L.groupStatus(["done", "pending"]), "running");
  assert.equal(L.groupStatus(["done", "running"]), "running");
  assert.equal(L.groupStatus(["done", "done"]), "done");
  assert.equal(L.groupStatus(["done", "skipped"]), "done");
  assert.equal(L.groupStatus(["skipped"]), "skipped");
  assert.equal(L.groupStatus(["done", "error"]), "error");
});

test("pipelineNodes follow real stage states", () => {
  const nodes = L.pipelineNodes([], false);
  assert.deepEqual(nodes.map((n) => n.label), ["Scan", "Autopsy", "Repair", "Validate", "Prove"]);
  assert.ok(nodes.every((n) => n.status === "pending"));
  const pre = L.pipelineNodes([], true);
  assert.deepEqual(pre.map((n) => n.status), ["done", "done", "pending", "pending", "pending"]);
  const stages = [
    { name: "autopsy", status: "done", duration_s: 0.1 },
    { name: "copy", status: "done", duration_s: 0.2 },
    { name: "repair", status: "running", duration_s: null },
    { name: "reanalyze", status: "pending", duration_s: null },
    { name: "validate", status: "pending", duration_s: null },
    { name: "dockerfile", status: "pending", duration_s: null },
  ];
  const mid = L.pipelineNodes(stages, false);
  assert.deepEqual(mid.map((n) => n.status), ["done", "done", "running", "pending", "pending"]);
  assert.ok(Math.abs(mid[2].duration_s - 0.2) < 1e-9);
  assert.equal(mid[0].duration_s, 0.1);
  assert.equal(mid[3].duration_s, null);
});

test("pipelineNodes marks skipped prove when proof is not requested", () => {
  const stages = [{ name: "autopsy", status: "done" }, { name: "copy", status: "done" }, { name: "repair", status: "done" }, { name: "reanalyze", status: "done" }, { name: "validate", status: "done" }, { name: "dockerfile", status: "done" }];
  const nodes = L.pipelineNodes(stages, false);
  assert.equal(nodes[4].status, "pending");
  const withSkip = L.pipelineNodes(stages.concat([{ name: "prove", status: "skipped" }]), false);
  assert.equal(withSkip[4].status, "skipped");
});

test("eventLogLine", () => {
  assert.deepEqual(L.eventLogLine({ type: "log", t: 1.234, message: "hello" }), { kind: "log", text: "[1.23s] hello" });
  assert.equal(L.eventLogLine({ type: "stage", stage: "repair", status: "start", message: "go", t: 0 }).text, "[0.00s] [repair] start go");
  assert.equal(L.eventLogLine({ type: "stage", stage: "repair", status: "end", message: "", t: 2 }).text, "[2.00s] [repair] done ");
  assert.equal(L.eventLogLine({ type: "state", state: "running" }).text, "run running");
  assert.equal(L.eventLogLine({ type: "error", message: "boom" }).kind, "error");
  assert.match(L.eventLogLine({ type: "end", state: "done", outcome: "SUCCESS", reason: "ok" }).text, /finished: SUCCESS \(ok\)/);
  assert.equal(L.eventLogLine({ type: "weird" }), null);
  assert.equal(L.eventLogLine(null), null);
  assert.equal(L.eventLogLine("x"), null);
});

const FINDINGS = [
  { rule_id: "PRINT_STMT", category: "SYNTAX", file: "b.py", line: 3, reason: "print statement", severity: "ERROR", repair_class: "AUTOMATIC" },
  { rule_id: "BROKEN_IMPORT", category: "IMPORT", file: "a.py", line: 9, reason: "missing module foo", severity: "CRITICAL", repair_class: "MANUAL" },
  { rule_id: "UNSUPPORTED_LANGUAGE", category: "UNSUPPORTED", file: "c.rb", line: 0, reason: "no analyzer", severity: "INFO", repair_class: "MANUAL" },
];

test("filterFindings", () => {
  assert.equal(L.filterFindings(FINDINGS, {}).length, 3);
  assert.equal(L.filterFindings(FINDINGS, { severity: "all" }).length, 3);
  assert.equal(L.filterFindings(FINDINGS, { severity: "ERROR" }).length, 1);
  assert.equal(L.filterFindings(FINDINGS, { category: "IMPORT" })[0].rule_id, "BROKEN_IMPORT");
  assert.equal(L.filterFindings(FINDINGS, { repair_class: "MANUAL" }).length, 2);
  assert.equal(L.filterFindings(FINDINGS, { query: "  FOO " }).length, 1);
  assert.equal(L.filterFindings(FINDINGS, { query: "c.rb" }).length, 1);
  assert.equal(L.filterFindings(FINDINGS, { query: "zzz" }).length, 0);
  assert.equal(L.filterFindings(FINDINGS, { severity: "ERROR", repair_class: "MANUAL" }).length, 0);
  assert.deepEqual(L.filterFindings(null, {}), []);
});

test("sortFindings does not mutate and supports keys and direction", () => {
  const copy = FINDINGS.slice();
  const bySev = L.sortFindings(FINDINGS, "severity", "asc").map((f) => f.severity);
  assert.deepEqual(bySev, ["CRITICAL", "ERROR", "INFO"]);
  assert.deepEqual(FINDINGS, copy);
  assert.deepEqual(L.sortFindings(FINDINGS, "severity", "desc").map((f) => f.severity), ["INFO", "ERROR", "CRITICAL"]);
  assert.deepEqual(L.sortFindings(FINDINGS, "file", "asc").map((f) => f.file), ["a.py", "b.py", "c.rb"]);
  assert.deepEqual(L.sortFindings(FINDINGS, "line", "asc").map((f) => f.line), [0, 3, 9]);
  assert.deepEqual(L.sortFindings(FINDINGS, "rule_id", "asc").map((f) => f.rule_id), ["BROKEN_IMPORT", "PRINT_STMT", "UNSUPPORTED_LANGUAGE"]);
  assert.deepEqual(L.sortFindings(null, "file"), []);
});

test("compareRows and reductionPercent", () => {
  const rows = L.compareRows({ CRITICAL: 1, ERROR: 4, WARNING: 0, INFO: 2 }, { CRITICAL: 0, ERROR: 0, WARNING: 0, INFO: 2 });
  assert.equal(rows.length, 5);
  assert.deepEqual(rows[rows.length - 1], { label: "Total", severity: null, before: 7, after: 2 });
  assert.equal(rows[1].before, 4);
  const empty = L.compareRows(null, undefined);
  assert.equal(empty[4].before, 0);
  assert.equal(L.reductionPercent(10, 0), 100);
  assert.equal(L.reductionPercent(10, 5), 50);
  assert.equal(L.reductionPercent(0, 0), 0);
  assert.equal(L.reductionPercent(5, 9), 0);
});

test("validateZipFile and validatePath", () => {
  const max = 50 * 1024 * 1024;
  assert.equal(L.validateZipFile("a.zip", 10, max), "");
  assert.equal(L.validateZipFile("A.ZIP", 10, max), "");
  assert.match(L.validateZipFile("a.tar", 10, max), /\.zip/);
  assert.match(L.validateZipFile("", 10, max), /\.zip/);
  assert.match(L.validateZipFile("a.zip", 0, max), /empty/);
  assert.match(L.validateZipFile("a.zip", max + 1, max), /larger/);
  assert.equal(L.validatePath("/tmp/x"), "");
  assert.match(L.validatePath("   "), /Enter/);
  assert.match(L.validatePath(undefined), /Enter/);
  assert.match(L.validatePath("a\u0000b"), /invalid/);
});

test("withOptions copies the source body and sends node only when on", () => {
  const src = { sample: "sample-legacy-3" };
  assert.deepEqual(L.withOptions(src, { prove: true, node: true }), { sample: "sample-legacy-3", prove: true, node: true });
  assert.deepEqual(L.withOptions(src, { prove: false, node: false }), { sample: "sample-legacy-3", prove: false });
  assert.deepEqual(L.withOptions(src, { node: true }), { sample: "sample-legacy-3", node: true });
  assert.deepEqual(L.withOptions(src, undefined), { sample: "sample-legacy-3" });
  assert.deepEqual(src, { sample: "sample-legacy-3" });
});

test("splitDiffByFile keeps a package.json diff", () => {
  const diff = ["--- a/package.json", "+++ b/package.json", "@@ -1,3 +1,3 @@", '-        "node": "0.10.x"', '+        "node": ">=18"', ""].join("\n");
  const out = L.splitDiffByFile(diff);
  assert.deepEqual(Object.keys(out), ["package.json"]);
  assert.ok(out["package.json"].includes('+        "node": ">=18"'));
});
