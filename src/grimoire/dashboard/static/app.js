/* Grimoire dashboard controller. All text is set with textContent; no HTML strings are parsed. */
(function () {
  "use strict";

  var L = window.GrimoireLib;
  var MAX_ZIP = 50 * 1024 * 1024;
  var MAX_LOG_LINES = 3000;

  var state = {
    mode: "hosted",
    samples: [],
    source: null, // {kind: "sample"|"path"|"upload", id, label, body}
    autopsy: null,
    run: null, // {id, stages, lastId, ended, es, poll}
    result: null,
    filters: { severity: "all", category: "all", repair_class: "all", query: "" },
    sort: { key: "severity", dir: "asc" },
    selectedFile: null,
    fileView: "diff",
    busy: { scan: false, run: false, path: false, upload: false },
    logLines: [],
    retry: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function h(tag, opts, children) {
    var node = document.createElement(tag);
    opts = opts || {};
    if (opts.cls) node.className = opts.cls;
    if (opts.text !== undefined) node.textContent = opts.text;
    if (opts.attrs) {
      Object.keys(opts.attrs).forEach(function (k) {
        node.setAttribute(k, opts.attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c) node.appendChild(c);
    });
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function setWidth(node, pct) {
    node.style.width = pct + "%"; // CSSOM, allowed under the CSP
  }

  // ---------------------------------------------------------------- API

  function api(method, path, body, contentType) {
    var opts = { method: method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = contentType || "application/json";
      opts.body = contentType ? body : JSON.stringify(body);
    }
    return fetch(path, opts).then(function (resp) {
      return resp.text().then(function (text) {
        var data = null;
        try {
          data = text ? JSON.parse(text) : null;
        } catch (e) {
          data = null;
        }
        if (!resp.ok) {
          var msg = data && data.detail ? data.detail : data && data.error ? data.error : "HTTP " + resp.status;
          var err = new Error(msg);
          err.status = resp.status;
          throw err;
        }
        return data;
      });
    });
  }

  function showError(message, retry) {
    $("error-text").textContent = message;
    $("error-banner").hidden = false;
    state.retry = retry || null;
    $("error-retry").hidden = !retry;
  }

  function hideError() {
    $("error-banner").hidden = true;
    state.retry = null;
  }

  function describeError(err) {
    if (err && err.status) return err.message;
    return "Could not reach the Grimoire server. " + (err && err.message ? err.message : "");
  }

  // ---------------------------------------------------------------- health, samples

  function loadHealth() {
    return api("GET", "/api/health")
      .then(function (d) {
        state.mode = d.mode;
        $("mode-badge").textContent = "mode: " + d.mode;
        $("mode-badge").className = "badge badge-mode badge-" + d.mode;
        $("health-dot").className = "dot dot-ok";
        var wh = d.wheelhouse && d.wheelhouse.in_use ? d.wheelhouse.wheels + " offline wheels" : "no wheelhouse";
        $("health-text").textContent = "Healthy, v" + d.version + ", " + wh;
        applyMode();
      })
      .catch(function (err) {
        $("health-dot").className = "dot dot-bad";
        $("health-text").textContent = "Server unreachable";
        showError(describeError(err), init);
      });
  }

  function applyMode() {
    var local = state.mode === "local";
    $("hosted-note").hidden = local;
    ["path-input", "path-btn", "zip-input"].forEach(function (id) {
      $(id).disabled = !local;
    });
    $("drop-zone").setAttribute("aria-disabled", local ? "false" : "true");
    $("drop-zone").classList.toggle("disabled", !local);
    $("drop-hint").textContent = local ? "Drop a .zip here or press Enter to browse" : "Uploads are disabled in hosted mode";
  }

  function loadSamples() {
    return api("GET", "/api/samples")
      .then(function (d) {
        state.samples = d.samples || [];
        renderSamples();
      })
      .catch(function (err) {
        showError(describeError(err), init);
      });
  }

  function renderSamples() {
    var box = $("sample-list");
    clear(box);
    if (!state.samples.length) {
      box.appendChild(h("p", { cls: "empty", text: "No bundled samples were found." }));
      return;
    }
    state.samples.forEach(function (s) {
      var selected = state.source && state.source.kind === "sample" && state.source.id === s.id;
      var files = h("ul", { cls: "mini-files" });
      s.files.forEach(function (f) {
        files.appendChild(h("li", {}, [h("span", { cls: "mono", text: f.path }), h("span", { cls: "muted", text: " " + L.formatBytes(f.size) })]));
      });
      var card = h(
        "button",
        { cls: "sample-card" + (selected ? " selected" : ""), attrs: { type: "button", role: "radio", "aria-checked": selected ? "true" : "false", "data-sample": s.id } },
        [
          h("span", { cls: "sample-id mono", text: s.id }),
          h("span", { cls: "sample-title", text: s.title }),
          h("span", { cls: "muted", text: s.python_files + " Python " + L.plural(s.python_files, "file") + ", " + s.files.length + " " + L.plural(s.files.length, "file") + " total" }),
          files,
        ]
      );
      card.addEventListener("click", function () {
        selectSource({ kind: "sample", id: s.id, label: s.id, body: { sample: s.id } });
      });
      box.appendChild(card);
    });
  }

  // ---------------------------------------------------------------- selection and reset

  function selectSource(src) {
    stopRun();
    state.source = src;
    state.autopsy = null;
    state.result = null;
    state.selectedFile = null;
    state.fileView = "diff";
    state.logLines = [];
    state.filters = { severity: "all", category: "all", repair_class: "all", query: "" };
    hideError();
    $("selected-source").textContent = "Selected: " + src.label + " (" + src.kind + ")";
    renderSamples();
    renderAll();
    updateButtons();
  }

  function renderAll() {
    renderAutopsy();
    renderFilters();
    renderFindings();
    renderPlan();
    renderPipeline();
    renderTimeline();
    renderLog();
    renderResults();
    renderDetail();
  }

  function updateButtons() {
    var b = state.busy;
    var any = b.scan || b.run || b.path || b.upload;
    var local = state.mode === "local";
    $("scan-btn").disabled = !state.source || any;
    $("resurrect-btn").disabled = !state.source || any;
    $("path-btn").disabled = !local || any;
    $("path-input").disabled = !local || any;
    $("zip-input").disabled = !local || any;
    $("prove-check").disabled = b.run;
    $("node-check").disabled = any;
    $("scan-btn").textContent = b.scan ? "Scanning..." : "Scan repository";
    $("resurrect-btn").textContent = b.run ? "Resurrecting..." : "Resurrect";
    $("download-btn").disabled = !state.result;
  }

  // ---------------------------------------------------------------- local sources

  function usePath() {
    var value = $("path-input").value;
    var problem = L.validatePath(value);
    $("path-msg").textContent = problem;
    $("path-msg").className = "field-msg" + (problem ? " bad" : "");
    if (problem) return;
    var path = value.trim();
    // Validate with the real server before accepting the path.
    state.busy.path = true;
    updateButtons();
    $("path-msg").textContent = "Checking path...";
    api("POST", "/api/autopsy", L.withOptions({ path: path }, { node: $("node-check").checked }))
      .then(function (d) {
        $("path-msg").textContent = "Path accepted.";
        $("path-msg").className = "field-msg good";
        selectSource({ kind: "path", id: path, label: path, body: { path: path } });
        state.autopsy = d;
        renderAll();
      })
      .catch(function (err) {
        $("path-msg").textContent = describeError(err);
        $("path-msg").className = "field-msg bad";
      })
      .then(function () {
        state.busy.path = false;
        updateButtons();
      });
  }

  function handleZip(file) {
    if (state.mode !== "local" || !file) return;
    var problem = L.validateZipFile(file.name, file.size, MAX_ZIP);
    $("zip-msg").textContent = problem;
    $("zip-msg").className = "field-msg" + (problem ? " bad" : "");
    if (problem) return;
    state.busy.upload = true;
    updateButtons();
    $("zip-msg").textContent = "Uploading " + file.name + " (" + L.formatBytes(file.size) + ")...";
    api("POST", "/api/upload", file, "application/zip")
      .then(function (d) {
        $("zip-msg").textContent = "Uploaded " + file.name + ".";
        $("zip-msg").className = "field-msg good";
        selectSource({ kind: "upload", id: d.upload_id, label: file.name, body: { upload: d.upload_id } });
      })
      .catch(function (err) {
        $("zip-msg").textContent = describeError(err);
        $("zip-msg").className = "field-msg bad";
      })
      .then(function () {
        state.busy.upload = false;
        $("zip-input").value = "";
        updateButtons();
      });
  }

  // ---------------------------------------------------------------- scan

  function scan() {
    if (!state.source) return;
    state.busy.scan = true;
    $("autopsy-status").textContent = "Scanning...";
    updateButtons();
    var src = state.source;
    api("POST", "/api/autopsy", L.withOptions(src.body, { node: $("node-check").checked }))
      .then(function (d) {
        if (state.source !== src) return;
        state.autopsy = d;
        $("autopsy-status").textContent = "Scan complete";
        renderAll();
      })
      .catch(function (err) {
        $("autopsy-status").textContent = "Scan failed";
        showError("Scan failed: " + describeError(err), scan);
      })
      .then(function () {
        state.busy.scan = false;
        updateButtons();
      });
  }

  // ---------------------------------------------------------------- autopsy rendering

  function tile(label, value, tone) {
    return h("div", { cls: "tile" + (tone ? " tile-" + tone : "") }, [h("div", { cls: "tile-value", text: value }), h("div", { cls: "tile-label", text: label })]);
  }

  function sevBadge(sev) {
    return h("span", { cls: "sev sev-" + sev, text: L.severityIcon(sev) + " " + L.severityLabel(sev) });
  }

  function renderAutopsy() {
    var a = state.autopsy;
    $("autopsy-empty").hidden = !!a;
    $("autopsy-body").hidden = !a;
    if (!a) return;
    var sum = a.summary;
    var files = 0;
    sum.coverage.forEach(function (c) {
      files += c.files;
    });
    var tiles = $("tiles");
    clear(tiles);
    tiles.appendChild(tile("Findings", L.formatNumber(sum.counts.total), sum.counts.total ? "warn" : "ok"));
    tiles.appendChild(tile("Files scanned", L.formatNumber(files)));
    tiles.appendChild(tile("Automatic repairs", L.formatNumber(sum.counts.repair_class.AUTOMATIC || 0)));
    tiles.appendChild(tile("Manual repairs", L.formatNumber(sum.counts.repair_class.MANUAL || 0)));
    tiles.appendChild(tile("Project types", sum.project_types.length ? sum.project_types.join(", ") : "none"));

    renderSeverityChart($("sev-chart"), sum.counts.severity);

    var cause = $("cause-list");
    clear(cause);
    if (!a.cause_of_death.length) cause.appendChild(h("p", { cls: "empty", text: "No cause of death found." }));
    var max = a.cause_of_death.length ? a.cause_of_death[0].count : 0;
    a.cause_of_death.forEach(function (c, i) {
      var fill = h("span", { cls: "bar-fill" });
      setWidth(fill, L.barPercent(c.count, max));
      cause.appendChild(
        h("div", { cls: "bar-row" }, [
          h("div", { cls: "bar-head" }, [h("span", { text: (i + 1) + ". " + c.category }), h("span", { cls: "mono", text: L.formatNumber(c.count) })]),
          h("span", { cls: "bar-track" }, [fill]),
        ])
      );
    });

    var cov = $("coverage-list");
    clear(cov);
    if (!sum.coverage.length) cov.appendChild(h("p", { cls: "empty", text: "No source files recognized." }));
    sum.coverage.forEach(function (c) {
      cov.appendChild(
        h("div", { cls: "cov-row" }, [
          h("span", { text: c.language }),
          h("span", { cls: "muted", text: c.status }),
          h("span", { cls: "mono", text: L.formatNumber(c.files) + " " + L.plural(c.files, "file") }),
        ])
      );
    });
  }

  function renderSeverityChart(box, counts) {
    clear(box);
    var segs = L.severitySegments(counts);
    if (!segs.length) {
      box.appendChild(h("p", { cls: "empty", text: "No findings." }));
      return;
    }
    var track = h("div", { cls: "stack", attrs: { role: "img", "aria-label": segs.map(function (s) { return s.count + " " + L.severityLabel(s.severity); }).join(", ") } });
    segs.forEach(function (s) {
      var seg = h("span", { cls: "stack-seg sevbg-" + s.severity });
      setWidth(seg, s.percent);
      track.appendChild(seg);
    });
    box.appendChild(track);
    var legend = h("ul", { cls: "legend" });
    L.SEVERITIES.forEach(function (s) {
      legend.appendChild(h("li", {}, [sevBadge(s), h("span", { cls: "mono", text: L.formatNumber(counts[s] || 0) })]));
    });
    box.appendChild(legend);
  }

  // ---------------------------------------------------------------- findings

  function renderFilters() {
    var sel = $("filter-severity");
    if (sel.options.length <= 1) {
      L.SEVERITIES.forEach(function (s) {
        var o = h("option", { text: L.severityLabel(s), attrs: { value: s } });
        sel.appendChild(o);
      });
    }
    var catSel = $("filter-category");
    while (catSel.options.length > 1) catSel.remove(1);
    var cats = state.autopsy ? Object.keys(state.autopsy.summary.counts.category) : [];
    cats.forEach(function (c) {
      catSel.appendChild(h("option", { text: c, attrs: { value: c } }));
    });
    sel.value = state.filters.severity;
    catSel.value = state.filters.category;
    $("filter-class").value = state.filters.repair_class;
    $("filter-query").value = state.filters.query;
  }

  function renderFindings() {
    var body = $("findings-body");
    clear(body);
    var all = state.autopsy ? state.autopsy.findings : [];
    var rows = L.sortFindings(L.filterFindings(all, state.filters), state.sort.key, state.sort.dir);
    $("findings-count").textContent = state.autopsy ? "Showing " + rows.length + " of " + all.length : "";
    var empty = $("findings-empty");
    $("findings-table").hidden = rows.length === 0;
    empty.hidden = rows.length !== 0;
    if (!state.autopsy) empty.textContent = "No scan yet. Select a repository and scan it.";
    else if (!all.length) empty.textContent = "No issues found. This repository looks healthy.";
    else empty.textContent = "No findings match the current filters.";
    rows.forEach(function (f) {
      var tag = h("span", { cls: "tag tag-" + f.repair_class, text: f.repair_class });
      body.appendChild(
        h("tr", {}, [
          h("td", {}, [sevBadge(f.severity)]),
          h("td", { cls: "mono", text: f.rule_id }),
          h("td", { cls: "mono wrap", text: f.file + (f.line ? ":" + f.line : "") }),
          h("td", { cls: "wrap", text: f.reason }),
          h("td", {}, [tag]),
        ])
      );
    });
    document.querySelectorAll("[data-sort]").forEach(function (btn) {
      var active = btn.getAttribute("data-sort") === state.sort.key;
      btn.parentNode.setAttribute("aria-sort", active ? (state.sort.dir === "asc" ? "ascending" : "descending") : "none");
      btn.classList.toggle("active", active);
      btn.setAttribute("data-dir", active ? (state.sort.dir === "asc" ? "\u25B2" : "\u25BC") : "");
    });
  }

  function onFilterChange() {
    state.filters = {
      severity: $("filter-severity").value,
      category: $("filter-category").value,
      repair_class: $("filter-class").value,
      query: $("filter-query").value,
    };
    renderFindings();
  }

  function resetFilters() {
    state.filters = { severity: "all", category: "all", repair_class: "all", query: "" };
    renderFilters();
    renderFindings();
  }

  function onSort(key) {
    if (state.sort.key === key) state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
    else state.sort = { key: key, dir: "asc" };
    renderFindings();
  }

  // ---------------------------------------------------------------- plan and pipeline

  function renderPlan() {
    var list = $("plan-list");
    clear(list);
    var plan = state.autopsy ? state.autopsy.plan : [];
    $("plan-empty").hidden = !!state.autopsy && plan.length > 0;
    $("plan-empty").textContent = state.autopsy ? "Nothing to repair. The scan found no issues." : "Scan a repository to see what Grimoire would do.";
    plan.forEach(function (p) {
      var files = h("ul", { cls: "mini-files" });
      p.files.forEach(function (f) {
        files.appendChild(h("li", { cls: "mono", text: f }));
      });
      list.appendChild(
        h("article", { cls: "plan-card" }, [
          h("div", { cls: "plan-head" }, [
            sevBadge(p.severity),
            h("span", { cls: "mono plan-rule", text: p.rule_id }),
            h("span", { cls: "muted", text: p.count + " " + L.plural(p.count, "occurrence") }),
            h("span", { cls: "tag tag-" + p.repair_class, text: p.repair_class }),
          ]),
          h("p", { cls: "plan-action", text: p.action }),
          files,
        ])
      );
    });
  }

  var STATUS_ICON = { pending: "\u25CB", running: "\u25D4", done: "\u2713", error: "\u2715", skipped: "\u2013" };

  function renderPipeline() {
    var ol = $("pipeline");
    clear(ol);
    var nodes = L.pipelineNodes(state.run ? state.run.stages : [], !!state.autopsy);
    nodes.forEach(function (n) {
      var bits = [h("span", { cls: "node-icon", text: STATUS_ICON[n.status] || "?", attrs: { "aria-hidden": "true" } }), h("span", { cls: "node-label", text: n.label })];
      if (n.duration_s !== null) bits.push(h("span", { cls: "muted mono", text: L.formatDuration(n.duration_s) }));
      bits.push(h("span", { cls: "visually-hidden", text: n.status }));
      ol.appendChild(h("li", { cls: "node node-" + n.status }, bits));
    });
  }

  // ---------------------------------------------------------------- run lifecycle

  function stopRun() {
    if (state.run) {
      if (state.run.es) state.run.es.close();
      if (state.run.poll) clearTimeout(state.run.poll);
      state.run.stopped = true;
    }
    state.run = null;
    state.busy.run = false;
    $("progress-status").textContent = "Idle";
  }

  function startRun() {
    if (!state.source) return;
    stopRun();
    state.result = null;
    state.logLines = [];
    state.selectedFile = null;
    state.busy.run = true;
    $("progress-status").textContent = "Starting...";
    updateButtons();
    renderResults();
    renderDetail();
    renderLog();
    var body = L.withOptions(state.source.body, { prove: $("prove-check").checked, node: $("node-check").checked });
    api("POST", "/api/runs", body)
      .then(function (d) {
        var run = { id: d.run_id, stages: [], lastId: 0, ended: false, es: null, poll: null, stopped: false, starts: {} };
        state.run = run;
        return api("GET", "/api/runs/" + d.run_id).then(function (snap) {
          if (run.stopped) return;
          run.stages = snap.stages;
          renderTimeline();
          renderPipeline();
          openStream(run);
        });
      })
      .catch(function (err) {
        state.busy.run = false;
        $("progress-status").textContent = "Failed to start";
        showError("Could not start the run: " + describeError(err), startRun);
        updateButtons();
      });
  }

  function openStream(run) {
    if (typeof EventSource === "undefined") return poll(run);
    var es = new EventSource("/api/runs/" + run.id + "/events");
    run.es = es;
    ["state", "stage", "log", "error", "end"].forEach(function (type) {
      es.addEventListener(type, function (msg) {
        var ev;
        try {
          ev = JSON.parse(msg.data);
        } catch (e) {
          return;
        }
        applyEvent(run, ev);
      });
    });
    es.onerror = function () {
      if (run.ended || run.stopped) return;
      es.close();
      run.es = null;
      poll(run);
    };
  }

  function poll(run) {
    if (run.stopped || run.ended) return;
    api("GET", "/api/runs/" + run.id)
      .then(function (snap) {
        if (run.stopped) return;
        snap.events.forEach(function (ev) {
          applyEvent(run, ev);
        });
        if (!run.ended) run.poll = setTimeout(function () {
          poll(run);
        }, 1000);
      })
      .catch(function (err) {
        if (run.stopped) return;
        $("progress-status").textContent = "Connection lost, retrying";
        run.poll = setTimeout(function () {
          poll(run);
        }, 2000);
        void err;
      });
  }

  function applyEvent(run, ev) {
    if (run.stopped || ev.id <= run.lastId) return;
    run.lastId = ev.id;
    var line = L.eventLogLine(ev);
    if (line) pushLog(line);
    if (ev.type === "stage") {
      run.stages.forEach(function (s) {
        if (s.name !== ev.stage) return;
        if (ev.status === "start") {
          s.status = "running";
          run.starts[s.name] = ev.t;
        } else {
          s.status = "done";
          s.duration_s = Math.max(0, +(ev.t - (run.starts[s.name] !== undefined ? run.starts[s.name] : ev.t)).toFixed(3));
        }
        s.message = ev.message;
      });
      $("progress-status").textContent = "Stage: " + ev.stage + " (" + (ev.status === "start" ? "running" : "done") + ")";
      renderTimeline();
      renderPipeline();
    } else if (ev.type === "end") {
      run.ended = true;
      if (run.es) run.es.close();
      finishRun(run);
    }
  }

  function finishRun(run) {
    api("GET", "/api/runs/" + run.id)
      .then(function (snap) {
        if (run.stopped) return;
        run.stages = snap.stages;
        state.result = snap.result;
        state.busy.run = false;
        $("progress-status").textContent = snap.state === "error" ? "Run failed" : "Run complete: " + (snap.result ? snap.result.outcome : snap.state);
        if (snap.result && snap.result.patches && snap.result.patches.length) state.selectedFile = snap.result.patches[0].path;
        renderTimeline();
        renderPipeline();
        renderResults();
        renderDetail();
        updateButtons();
        $("results").scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
      })
      .catch(function (err) {
        state.busy.run = false;
        updateButtons();
        showError("Could not load the run result: " + describeError(err), function () {
          finishRun(run);
        });
      });
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  // ---------------------------------------------------------------- timeline and log

  function renderTimeline() {
    var ol = $("stage-timeline");
    clear(ol);
    var stages = state.run ? state.run.stages : [];
    if (!stages.length) {
      ol.appendChild(h("li", { cls: "empty", text: "No run yet." }));
      return;
    }
    stages.forEach(function (s) {
      ol.appendChild(
        h("li", { cls: "tl tl-" + s.status }, [
          h("span", { cls: "node-icon", text: STATUS_ICON[s.status] || "?", attrs: { "aria-hidden": "true" } }),
          h("span", { cls: "tl-name", text: s.name }),
          h("span", { cls: "tl-status muted", text: s.status }),
          h("span", { cls: "mono tl-dur", text: L.formatDuration(s.duration_s) }),
        ])
      );
    });
  }

  function pushLog(line) {
    state.logLines.push(line);
    var con = $("log-console");
    con.appendChild(h("div", { cls: "log log-" + line.kind, text: line.text }));
    if (state.logLines.length > MAX_LOG_LINES) {
      state.logLines.shift();
      if (con.firstChild) con.removeChild(con.firstChild);
    }
    if ($("autoscroll-check").checked) con.scrollTop = con.scrollHeight;
  }

  function renderLog() {
    var con = $("log-console");
    clear(con);
    if (!state.logLines.length) {
      con.appendChild(h("div", { cls: "log log-muted", text: "Run output will appear here." }));
      return;
    }
    state.logLines.forEach(function (l) {
      con.appendChild(h("div", { cls: "log log-" + l.kind, text: l.text }));
    });
  }

  function copyLog() {
    var text = state.logLines
      .map(function (l) {
        return l.text;
      })
      .join("\n");
    var msg = $("copy-msg");
    if (!text) {
      msg.textContent = "Nothing to copy.";
      return;
    }
    var done = function () {
      msg.textContent = "Copied.";
    };
    var fail = function () {
      msg.textContent = "Copy failed. Select the log text and copy it manually.";
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fail);
    else fail();
  }

  // ---------------------------------------------------------------- results

  function renderResults() {
    var r = state.result;
    $("results-empty").hidden = !!r;
    $("results-body").hidden = !r;
    if (!r) return;
    var p = L.outcomePresentation(r.outcome);
    $("outcome-banner").className = "outcome outcome-" + p.tone;
    $("outcome-icon").textContent = p.icon;
    $("outcome-label").textContent = p.label + " (" + r.outcome + ")";
    $("outcome-reason").textContent = r.reason || p.summary;
    var tiles = $("stat-tiles");
    clear(tiles);
    if (r.stats) {
      var s = r.stats;
      tiles.appendChild(tile("Issues before", L.formatNumber(s.issues_before), s.issues_before ? "warn" : ""));
      tiles.appendChild(tile("Issues after", L.formatNumber(s.issues_after), s.issues_after ? "warn" : "ok"));
      tiles.appendChild(tile("Fixed automatically", L.formatNumber(s.automatic_fixed), "ok"));
      tiles.appendChild(tile("Manual remaining", L.formatNumber(s.manual_remaining), s.manual_remaining ? "warn" : ""));
      tiles.appendChild(tile("Files scanned", L.formatNumber(s.files_scanned)));
      tiles.appendChild(tile("Files patched", L.formatNumber(s.files_patched)));
    }
    var cmp = $("compare-bars");
    clear(cmp);
    if (r.before && r.after) {
      var rows = L.compareRows(r.before.counts, r.after.counts);
      var max = 0;
      rows.forEach(function (row) {
        max = Math.max(max, row.before, row.after);
      });
      rows.forEach(function (row) {
        var bf = h("span", { cls: "bar-fill before" });
        var af = h("span", { cls: "bar-fill after" + (row.severity ? " sevbg-" + row.severity : "") });
        setWidth(bf, L.barPercent(row.before, max));
        setWidth(af, L.barPercent(row.after, max));
        cmp.appendChild(
          h("div", { cls: "cmp-row" }, [
            h("span", { cls: "cmp-label", text: row.label }),
            h("div", { cls: "cmp-bars" }, [
              h("div", { cls: "cmp-line" }, [h("span", { cls: "bar-track" }, [bf]), h("span", { cls: "mono cmp-n", text: "before " + row.before })]),
              h("div", { cls: "cmp-line" }, [h("span", { cls: "bar-track" }, [af]), h("span", { cls: "mono cmp-n", text: "after " + row.after })]),
            ]),
          ])
        );
      });
      var total = rows[rows.length - 1];
      cmp.appendChild(h("p", { cls: "muted", text: "Total findings reduced by " + L.reductionPercent(total.before, total.after) + "% (" + total.before + " to " + total.after + ", including INFO)." }));
    }
    var list = $("patched-list");
    clear(list);
    var patches = r.patches || [];
    if (!patches.length) list.appendChild(h("li", { cls: "empty", text: "No files were patched." }));
    patches.forEach(function (pt) {
      var btn = h("button", { cls: "file-btn" + (pt.path === state.selectedFile ? " selected" : ""), attrs: { type: "button" } }, [
        h("span", { cls: "mono", text: pt.path }),
        h("span", { cls: "muted", text: pt.rules.join(", ") }),
      ]);
      btn.addEventListener("click", function () {
        state.selectedFile = pt.path;
        renderResults();
        renderDetail();
        $("detail").scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
      });
      list.appendChild(h("li", {}, [btn]));
    });
  }

  // ---------------------------------------------------------------- detail

  function codeLines(text, kindFn) {
    var frag = document.createDocumentFragment();
    String(text).split("\n").forEach(function (t) {
      frag.appendChild(h("div", { cls: "cl cl-" + kindFn(t), text: t === "" ? " " : t }));
    });
    return frag;
  }

  function renderDetail() {
    var r = state.result;
    var diffView = $("diff-view");
    clear(diffView);
    var patch = r && r.patches ? r.patches.filter(function (p) { return p.path === state.selectedFile; })[0] : null;
    $("detail-file").textContent = patch ? patch.path : "No file selected";
    $("detail-rules").textContent = patch ? "Rules applied: " + patch.rules.join(", ") : "";
    ["diff", "before", "after"].forEach(function (v) {
      $("view-" + v).setAttribute("aria-pressed", state.fileView === v ? "true" : "false");
    });
    if (!r) {
      diffView.appendChild(h("p", { cls: "empty", text: "Run a resurrection to see repairs." }));
    } else if (!patch) {
      diffView.appendChild(h("p", { cls: "empty", text: "No patched files to show." }));
    } else if (state.fileView === "diff") {
      var chunk = L.splitDiffByFile(r.diff || "")[patch.path];
      if (chunk) diffView.appendChild(codeLines(chunk.join("\n"), L.classifyDiffLine));
      else diffView.appendChild(h("p", { cls: "empty", text: "No diff recorded for this file." }));
    } else {
      diffView.appendChild(codeLines(patch[state.fileView], function () { return "ctx"; }));
    }

    var dk = $("dockerfile-view");
    dk.textContent = r ? (r.dockerfile ? r.dockerfile : "No Dockerfile was generated for this run.") : "Run a resurrection to see the generated Dockerfile.";

    var vv = $("validation-view");
    clear(vv);
    if (!r) vv.appendChild(h("p", { cls: "empty", text: "Run a resurrection to see validation results." }));
    else if (!r.validation || !r.validation.length) vv.appendChild(h("p", { cls: "empty", text: "No validation results were produced." }));
    else {
      var tbody = h("tbody");
      r.validation.forEach(function (v) {
        tbody.appendChild(h("tr", {}, [h("td", { cls: "mono", text: v.name }), h("td", {}, [h("span", { cls: "tag tag-" + (/pass|ok/i.test(v.status) ? "AUTOMATIC" : "MANUAL"), text: v.status })]), h("td", { cls: "wrap", text: v.detail })]));
      });
      vv.appendChild(h("div", { cls: "table-wrap" }, [h("table", { cls: "table" }, [h("thead", {}, [h("tr", {}, [h("th", { text: "Check" }), h("th", { text: "Status" }), h("th", { text: "Detail" })])]), tbody])]));
    }

    var pv = $("proof-view");
    if (!r) {
      $("proof-summary").textContent = "";
      pv.textContent = "Run a resurrection to see the proof log.";
    } else if (!r.proof) {
      $("proof-summary").textContent = "Proof was not requested for this run.";
      pv.textContent = "";
    } else {
      $("proof-summary").textContent = "Status: " + r.proof.status + (r.proof.exit_code === null || r.proof.exit_code === undefined ? "" : ", exit code " + r.proof.exit_code);
      pv.textContent = r.proof.log_lines.length ? r.proof.log_lines.join("\n") : "No output was captured.";
    }
  }

  function setTab(name) {
    document.querySelectorAll("[data-tab]").forEach(function (b) {
      var on = b.getAttribute("data-tab") === name;
      b.setAttribute("aria-selected", on ? "true" : "false");
      b.tabIndex = on ? 0 : -1;
      $("panel-" + b.getAttribute("data-tab")).hidden = !on;
    });
  }

  function downloadReport() {
    if (!state.result) return;
    var payload = { source: state.source ? { kind: state.source.kind, id: state.source.id } : null, autopsy: state.autopsy, result: state.result };
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "grimoire-report.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  // ---------------------------------------------------------------- wiring

  function wire() {
    $("error-retry").addEventListener("click", function () {
      var fn = state.retry;
      hideError();
      if (fn) fn();
    });
    $("error-dismiss").addEventListener("click", hideError);
    $("path-btn").addEventListener("click", usePath);
    $("path-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") usePath();
    });
    var dz = $("drop-zone");
    dz.addEventListener("click", function () {
      if (state.mode === "local" && !$("zip-input").disabled) $("zip-input").click();
    });
    dz.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        dz.click();
      }
    });
    dz.addEventListener("dragover", function (e) {
      e.preventDefault();
      if (state.mode === "local") dz.classList.add("over");
    });
    dz.addEventListener("dragleave", function () {
      dz.classList.remove("over");
    });
    dz.addEventListener("drop", function (e) {
      e.preventDefault();
      dz.classList.remove("over");
      if (state.mode !== "local") {
        $("zip-msg").textContent = "Uploads are disabled in hosted mode.";
        $("zip-msg").className = "field-msg bad";
        return;
      }
      var files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length) handleZip(files[0]);
    });
    $("zip-input").addEventListener("change", function () {
      if (this.files && this.files.length) handleZip(this.files[0]);
    });
    $("scan-btn").addEventListener("click", scan);
    $("resurrect-btn").addEventListener("click", startRun);
    $("node-check").addEventListener("change", function () {
      if (state.source && state.autopsy) scan(); // the autopsy depends on this option
    });
    $("prove-check").addEventListener("change", function () {
      $("caution").classList.toggle("dim", !this.checked);
    });
    ["filter-severity", "filter-category", "filter-class"].forEach(function (id) {
      $(id).addEventListener("change", onFilterChange);
    });
    $("filter-query").addEventListener("input", onFilterChange);
    $("filter-reset").addEventListener("click", resetFilters);
    document.querySelectorAll("[data-sort]").forEach(function (b) {
      b.addEventListener("click", function () {
        onSort(b.getAttribute("data-sort"));
      });
    });
    $("autoscroll-check").addEventListener("change", function () {
      if (this.checked) $("log-console").scrollTop = $("log-console").scrollHeight;
    });
    $("copy-log-btn").addEventListener("click", copyLog);
    document.querySelectorAll("[data-tab]").forEach(function (b) {
      b.addEventListener("click", function () {
        setTab(b.getAttribute("data-tab"));
      });
      b.addEventListener("keydown", function (e) {
        var tabs = Array.prototype.slice.call(document.querySelectorAll("[data-tab]"));
        var i = tabs.indexOf(b);
        var next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : -1;
        if (next < 0 || next >= tabs.length) return;
        e.preventDefault();
        setTab(tabs[next].getAttribute("data-tab"));
        tabs[next].focus();
      });
    });
    document.querySelectorAll("[data-view]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.fileView = b.getAttribute("data-view");
        renderDetail();
      });
    });
    $("download-btn").addEventListener("click", downloadReport);
  }

  function init() {
    hideError();
    return Promise.all([loadHealth(), loadSamples()]).then(function () {
      renderAll();
      updateButtons();
    });
  }

  wire();
  init();
})();
