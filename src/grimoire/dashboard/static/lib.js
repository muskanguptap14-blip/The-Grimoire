/* Pure helpers for the Grimoire dashboard. No DOM access, so node:test can load this file. */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.GrimoireLib = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var SEVERITIES = ["CRITICAL", "ERROR", "WARNING", "INFO"];
  var SEVERITY_META = {
    CRITICAL: { label: "Critical", icon: "\u25C6" }, // diamond
    ERROR: { label: "Error", icon: "\u25A0" }, // square
    WARNING: { label: "Warning", icon: "\u25B2" }, // triangle
    INFO: { label: "Info", icon: "\u25CF" }, // circle
  };

  function severityRank(sev) {
    var i = SEVERITIES.indexOf(sev);
    return i === -1 ? SEVERITIES.length : i;
  }

  function severityLabel(sev) {
    return SEVERITY_META[sev] ? SEVERITY_META[sev].label : String(sev);
  }

  function severityIcon(sev) {
    return SEVERITY_META[sev] ? SEVERITY_META[sev].icon : "?";
  }

  function countBySeverity(findings) {
    var counts = { CRITICAL: 0, ERROR: 0, WARNING: 0, INFO: 0 };
    (findings || []).forEach(function (f) {
      if (Object.prototype.hasOwnProperty.call(counts, f.severity)) counts[f.severity] += 1;
    });
    return counts;
  }

  /* [{key, count}] sorted by count desc then key asc. */
  function aggregateBy(findings, field) {
    var map = {};
    (findings || []).forEach(function (f) {
      var k = f[field];
      map[k] = (map[k] || 0) + 1;
    });
    return Object.keys(map)
      .map(function (k) {
        return { key: k, count: map[k] };
      })
      .sort(function (a, b) {
        return b.count - a.count || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0);
      });
  }

  /* Width of a bar as a whole percent in [0, 100]. A non-zero value always shows at least 2%. */
  function barPercent(value, max) {
    if (!(max > 0) || !(value > 0)) return 0;
    var pct = Math.round((value / max) * 100);
    return Math.min(100, Math.max(2, pct));
  }

  /* Segments for a stacked severity bar: [{severity, count, percent}] in severity order, zero counts omitted. */
  function severitySegments(counts) {
    var total = 0;
    SEVERITIES.forEach(function (s) {
      total += (counts && counts[s]) || 0;
    });
    if (total === 0) return [];
    return SEVERITIES.filter(function (s) {
      return counts[s] > 0;
    }).map(function (s) {
      return { severity: s, count: counts[s], percent: (counts[s] / total) * 100 };
    });
  }

  /* Classify one line of a unified diff: meta, hunk, add, del, ctx. */
  function classifyDiffLine(line) {
    if (typeof line !== "string") return "ctx";
    if (line.indexOf("+++") === 0 || line.indexOf("---") === 0) return "meta";
    if (line.indexOf("diff ") === 0 || line.indexOf("index ") === 0) return "meta";
    if (line.indexOf("@@") === 0) return "hunk";
    if (line.charAt(0) === "+") return "add";
    if (line.charAt(0) === "-") return "del";
    return "ctx";
  }

  function parseDiff(text) {
    if (!text) return [];
    var lines = String(text).split("\n");
    if (lines.length && lines[lines.length - 1] === "") lines.pop();
    return lines.map(function (l) {
      return { kind: classifyDiffLine(l), text: l };
    });
  }

  function diffStats(text) {
    var s = { added: 0, removed: 0 };
    parseDiff(text).forEach(function (l) {
      if (l.kind === "add") s.added += 1;
      else if (l.kind === "del") s.removed += 1;
    });
    return s;
  }

  /* Split a unified diff into per-file chunks keyed by the "+++ b/<path>" header when present. */
  function splitDiffByFile(text) {
    var out = {};
    var current = null;
    var pending = [];
    parseDiff(text).forEach(function (l) {
      if (l.text.indexOf("--- ") === 0 && l.kind === "meta") {
        current = null;
        pending = [l.text];
        return;
      }
      if (l.text.indexOf("+++ ") === 0 && l.kind === "meta") {
        var name = l.text.slice(4).trim().replace(/^[ab]\//, "").split("\t")[0];
        current = name;
        out[current] = pending.concat([l.text]);
        pending = [];
        return;
      }
      if (current !== null) out[current].push(l.text);
    });
    return out;
  }

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined || typeof seconds !== "number" || isNaN(seconds) || seconds < 0) return "n/a";
    if (seconds < 1) return Math.round(seconds * 1000) + " ms";
    if (seconds < 60) return seconds.toFixed(seconds < 10 ? 2 : 1) + " s";
    var m = Math.floor(seconds / 60);
    var s = Math.round(seconds - m * 60);
    if (s === 60) {
      m += 1;
      s = 0;
    }
    return m + " m " + (s < 10 ? "0" : "") + s + " s";
  }

  function formatNumber(n) {
    if (typeof n !== "number" || !isFinite(n)) return "0";
    var neg = n < 0;
    var digits = String(Math.round(Math.abs(n)));
    var out = "";
    while (digits.length > 3) {
      out = "," + digits.slice(-3) + out;
      digits = digits.slice(0, -3);
    }
    return (neg ? "-" : "") + digits + out;
  }

  function formatBytes(n) {
    if (typeof n !== "number" || !isFinite(n) || n < 0) return "0 B";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  function plural(n, one, many) {
    return n === 1 ? one : many || one + "s";
  }

  var OUTCOMES = {
    SUCCESS: { label: "Resurrected", tone: "success", icon: "\u2713", summary: "Fully repaired and verified alive." },
    PARTIAL: { label: "Partial recovery", tone: "partial", icon: "\u25D0", summary: "Repairs applied, but work remains or the result is unverified." },
    FAILURE: { label: "Resurrection failed", tone: "failure", icon: "\u2715", summary: "The project could not be brought back." },
  };

  function outcomePresentation(outcome) {
    return OUTCOMES[outcome] || { label: "Unknown", tone: "failure", icon: "?", summary: "The run returned an unrecognized outcome." };
  }

  /* Pipeline nodes and the backend stages that feed each one. */
  var PIPELINE = [
    { id: "scan", label: "Scan", stages: ["autopsy"] },
    { id: "autopsy", label: "Autopsy", stages: ["autopsy"] },
    { id: "repair", label: "Repair", stages: ["copy", "repair"] },
    { id: "validate", label: "Validate", stages: ["reanalyze", "validate", "dockerfile"] },
    { id: "prove", label: "Prove", stages: ["prove"] },
  ];

  function groupStatus(statuses) {
    if (!statuses.length) return "pending";
    if (statuses.indexOf("error") !== -1) return "error";
    if (statuses.indexOf("running") !== -1) return "running";
    var done = statuses.filter(function (s) {
      return s === "done";
    }).length;
    var skipped = statuses.filter(function (s) {
      return s === "skipped";
    }).length;
    if (skipped === statuses.length) return "skipped";
    if (done + skipped === statuses.length) return "done";
    if (done > 0) return "running";
    return "pending";
  }

  /* stages: the run snapshot's stage list. autopsyDone: a standalone autopsy has completed. */
  function pipelineNodes(stages, autopsyDone) {
    var byName = {};
    (stages || []).forEach(function (s) {
      byName[s.name] = s;
    });
    return PIPELINE.map(function (node) {
      var present = node.stages.filter(function (n) {
        return byName[n];
      });
      var status = groupStatus(
        present.map(function (n) {
          return byName[n].status;
        })
      );
      if (status === "pending" && autopsyDone && (node.id === "scan" || node.id === "autopsy")) status = "done";
      var duration = null;
      present.forEach(function (n) {
        if (typeof byName[n].duration_s === "number") duration = (duration || 0) + byName[n].duration_s;
      });
      return { id: node.id, label: node.label, status: status, duration_s: duration };
    });
  }

  /* One console line for a stream event, or null when the event has nothing to print. */
  function eventLogLine(ev) {
    if (!ev || typeof ev !== "object") return null;
    var t = typeof ev.t === "number" ? "[" + ev.t.toFixed(2) + "s] " : "";
    if (ev.type === "log") return { kind: "log", text: t + (ev.message || "") };
    if (ev.type === "stage") {
      var verb = ev.status === "start" ? "start" : "done ";
      return { kind: "stage", text: t + "[" + ev.stage + "] " + verb + (ev.message ? " " + ev.message : "") };
    }
    if (ev.type === "state") return { kind: "stage", text: t + "run " + ev.state };
    if (ev.type === "error") return { kind: "error", text: t + "error: " + (ev.message || "") };
    if (ev.type === "end") return { kind: "stage", text: t + "finished: " + (ev.outcome || ev.state) + (ev.reason ? " (" + ev.reason + ")" : "") };
    return null;
  }

  /* Filter findings by {severity, category, repair_class, query}; empty or "all" means no filter. */
  function filterFindings(findings, f) {
    f = f || {};
    var q = (f.query || "").trim().toLowerCase();
    return (findings || []).filter(function (x) {
      if (f.severity && f.severity !== "all" && x.severity !== f.severity) return false;
      if (f.category && f.category !== "all" && x.category !== f.category) return false;
      if (f.repair_class && f.repair_class !== "all" && x.repair_class !== f.repair_class) return false;
      if (q) {
        var hay = (x.rule_id + " " + x.file + " " + x.reason + " " + x.category).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  function sortFindings(findings, key, dir) {
    var sign = dir === "desc" ? -1 : 1;
    var copy = (findings || []).slice();
    copy.sort(function (a, b) {
      var c;
      if (key === "severity") c = severityRank(a.severity) - severityRank(b.severity);
      else if (key === "line") c = a.line - b.line;
      else {
        var av = String(a[key] === undefined ? "" : a[key]);
        var bv = String(b[key] === undefined ? "" : b[key]);
        c = av < bv ? -1 : av > bv ? 1 : 0;
      }
      if (c === 0) {
        c = a.file < b.file ? -1 : a.file > b.file ? 1 : a.line - b.line;
      }
      return c * sign;
    });
    return copy;
  }

  /* Rows for the before/after comparison: one per severity plus a total. */
  function compareRows(before, after) {
    var rows = SEVERITIES.map(function (s) {
      return { label: severityLabel(s), severity: s, before: (before && before[s]) || 0, after: (after && after[s]) || 0 };
    });
    var tb = 0;
    var ta = 0;
    rows.forEach(function (r) {
      tb += r.before;
      ta += r.after;
    });
    rows.push({ label: "Total", severity: null, before: tb, after: ta });
    return rows;
  }

  /* Percent of the "before" count that is gone, clamped to [0, 100]. 0 when there was nothing before. */
  function reductionPercent(before, after) {
    if (!(before > 0)) return 0;
    var pct = Math.round(((before - after) / before) * 100);
    return Math.max(0, Math.min(100, pct));
  }

  function validateZipFile(name, size, maxBytes) {
    if (!name || !/\.zip$/i.test(name)) return "Choose a .zip archive.";
    if (!(size > 0)) return "The file is empty.";
    if (size > maxBytes) return "The archive is larger than " + formatBytes(maxBytes) + ".";
    return "";
  }

  function validatePath(value) {
    var v = (value || "").trim();
    if (!v) return "Enter a directory path.";
    if (v.indexOf("\u0000") !== -1) return "The path contains an invalid character.";
    return "";
  }

  return {
    SEVERITIES: SEVERITIES,
    PIPELINE: PIPELINE,
    severityRank: severityRank,
    severityLabel: severityLabel,
    severityIcon: severityIcon,
    countBySeverity: countBySeverity,
    aggregateBy: aggregateBy,
    barPercent: barPercent,
    severitySegments: severitySegments,
    classifyDiffLine: classifyDiffLine,
    parseDiff: parseDiff,
    diffStats: diffStats,
    splitDiffByFile: splitDiffByFile,
    formatDuration: formatDuration,
    formatNumber: formatNumber,
    formatBytes: formatBytes,
    plural: plural,
    outcomePresentation: outcomePresentation,
    groupStatus: groupStatus,
    pipelineNodes: pipelineNodes,
    eventLogLine: eventLogLine,
    filterFindings: filterFindings,
    sortFindings: sortFindings,
    compareRows: compareRows,
    reductionPercent: reductionPercent,
    validateZipFile: validateZipFile,
    validatePath: validatePath,
  };
});
