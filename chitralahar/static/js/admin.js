/* Chitralahar — admin scripts: confirms, toggles, dependent dropdowns,
   menu forms, drag-reorder + drag-to-file/reparent, multi-select, dropzone. */
(function () {
  "use strict";

  /* ---------- Confirm before destructive submits ---------- */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.classList && form.classList.contains("js-confirm")) {
      var msg = form.getAttribute("data-confirm") || "Are you sure?";
      if (!window.confirm(msg)) e.preventDefault();
    }
  });

  /* ---------- Generic on/off toggles (featured, published) ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".toggle-btn");
    if (!btn) return;
    e.preventDefault();
    var url = btn.dataset.toggleUrl;
    if (!url) return;
    btn.disabled = true;
    fetch(url, { method: "POST", headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var on = !!d.on;
        btn.classList.toggle("is-on", on);
        if (btn.dataset.onText !== undefined) {
          btn.textContent = on ? btn.dataset.onText : (btn.dataset.offText || "");
        }
        if (btn.classList.contains("publish-btn") || btn.classList.contains("pill-toggle")) {
          var tile = btn.closest(".photo-tile, .cat-card, .sub-row");
          if (tile) tile.classList.toggle("is-hidden", !on);
        }
      })
      .catch(function () {})
      .then(function () { btn.disabled = false; });
  });

  /* ---------- Dependent category -> subcategory dropdowns (photo edit, upload) ---------- */
  document.querySelectorAll("select[data-subselect]").forEach(function (subSel) {
    var catSel = document.getElementById(subSel.getAttribute("data-subselect"));
    if (!catSel) return;
    function rebuild(preserve) {
      var current = preserve ? subSel.getAttribute("data-current") : "";
      var list = (window.CHITRALAHAR_SUBS || {})[catSel.value] || [];
      subSel.innerHTML = '<option value="">— None —</option>';
      list.forEach(function (s) {
        var o = document.createElement("option");
        o.value = s.id; o.textContent = s.name;
        if (String(s.id) === String(current)) o.selected = true;
        subSel.appendChild(o);
      });
      subSel.disabled = list.length === 0;
    }
    rebuild(true);
    catSel.addEventListener("change", function () { rebuild(false); });
  });

  /* ---------- Menu builder forms: reveal fields by link type ---------- */
  document.querySelectorAll("[data-menu-form]").forEach(function (form) {
    var typeSel = form.querySelector("select[name='link_type']");
    if (!typeSel) return;
    var catSel = form.querySelector("select[name='category_id']");
    var subSel = form.querySelector("select[name='subcategory_id']");
    function showFields() {
      var v = typeSel.value;
      form.querySelectorAll("[data-when]").forEach(function (el) {
        el.hidden = el.getAttribute("data-when").split(" ").indexOf(v) === -1;
      });
    }
    function rebuildSubs(preserve) {
      if (!catSel || !subSel) return;
      var current = preserve ? (subSel.getAttribute("data-current") || "") : "";
      var list = (window.CHITRALAHAR_SUBS || {})[catSel.value] || [];
      subSel.innerHTML = '<option value="">— Subcategory —</option>';
      list.forEach(function (s) {
        var o = document.createElement("option");
        o.value = s.id; o.textContent = s.name;
        if (String(s.id) === String(current)) o.selected = true;
        subSel.appendChild(o);
      });
    }
    showFields();
    rebuildSubs(true);
    typeSel.addEventListener("change", showFields);
    if (catSel) catSel.addEventListener("change", function () { rebuildSubs(false); });
  });

  /* ===================== Drag system ===================== */
  // Shared state for whatever is currently being dragged.
  var dragState = { kind: null, id: null, ids: [], parent: null, handled: false };
  var selected = new Set();  // selected photo ids (strings)

  function updateSelBar() {
    var bar = document.getElementById("selBar");
    if (!bar) return;
    bar.hidden = selected.size === 0;
    var c = document.getElementById("selCount");
    if (c) c.textContent = selected.size + " selected";
  }

  /* ----- Photo multi-select (click the image) ----- */
  document.addEventListener("click", function (e) {
    var imgWrap = e.target.closest(".photo-tile-img");
    if (!imgWrap) return;
    if (e.target.closest(".toggle-btn") || e.target.closest("a")) return;
    var tile = imgWrap.closest(".photo-tile");
    if (!tile) return;
    var id = tile.dataset.id;
    if (selected.has(id)) { selected.delete(id); tile.classList.remove("selected"); }
    else { selected.add(id); tile.classList.add("selected"); }
    updateSelBar();
  });

  var selClear = document.getElementById("selClear");
  if (selClear) selClear.addEventListener("click", function () {
    selected.forEach(function (id) {
      var t = document.querySelector('.photo-tile[data-id="' + id + '"]');
      if (t) t.classList.remove("selected");
    });
    selected.clear(); updateSelBar();
  });

  var selAssign = document.getElementById("selAssign");
  if (selAssign) selAssign.addEventListener("change", function () {
    var v = selAssign.value;
    if (!v || !selected.size) { selAssign.value = ""; return; }
    var cat = "", sub = "";
    if (v.indexOf("cat:") === 0) cat = v.slice(4);
    else if (v.indexOf("sub:") === 0) sub = v.slice(4);
    assignPhotos(Array.from(selected), cat, sub, null);
    selAssign.value = "";
  });

  function assignPhotos(ids, catId, subId, chip) {
    if (!ids.length || !window.CHITRALAHAR_ASSIGN_URL) return;
    fetch(window.CHITRALAHAR_ASSIGN_URL, {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ ids: ids, category_id: catId, subcategory_id: subId }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) return;
        ids.forEach(function (id) {
          var tile = document.querySelector('.photo-tile[data-id="' + id + '"]');
          if (tile) {
            var badge = tile.querySelector(".photo-tile-cat");
            if (badge) badge.textContent = d.label;
            tile.classList.add("just-filed");
            setTimeout(function () { tile.classList.remove("just-filed"); }, 1000);
            tile.classList.remove("selected");
          }
          selected.delete(id);
        });
        updateSelBar();
        if (chip) { chip.classList.add("drop-done"); setTimeout(function () { chip.classList.remove("drop-done"); }, 700); }
      })
      .catch(function () {});
  }

  /* ----- Reorder within a list; top-level rows also NEST when dropped on the
     middle of a sibling (drag a category onto another -> make it a subcategory;
     drag a top menu item onto another -> make it a dropdown child). ----- */
  function setupDrag(container) {
    var itemSel = container.dataset.dragItem;
    var url = container.dataset.reorderUrl;
    var kind = container.dataset.dragKind || "";
    var locked = container.dataset.reorderLock === "1";
    var nestable = (kind === "cat" || kind === "menu-top");
    if (!itemSel) return;
    var dragEl = null, nestTarget = null;

    function clearNest() {
      if (nestTarget) nestTarget.classList.remove("nest-target");
      nestTarget = null;
    }

    container.addEventListener("dragstart", function (e) {
      if (e.target.closest("[data-reorder-url]") !== container) return;
      var item = e.target.closest(itemSel);
      if (!item || item.parentNode !== container) return;
      dragEl = item;
      item.classList.add("dragging");
      dragState.kind = kind;
      dragState.id = item.dataset.id;
      dragState.parent = item.dataset.parent || null;
      dragState.handled = false;
      dragState.ids = (kind === "photo" && selected.has(item.dataset.id) && selected.size)
        ? Array.from(selected) : [item.dataset.id];
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", item.dataset.id); } catch (_) {}
    });

    container.addEventListener("dragover", function (e) {
      if (!dragEl || dragEl.parentNode !== container || locked) return;
      e.preventDefault();
      var item = e.target.closest(itemSel);
      if (!item || item === dragEl || item.parentNode !== container) return;
      var rect = item.getBoundingClientRect();
      var y = e.clientY - rect.top;
      if (nestable && y > rect.height * 0.28 && y < rect.height * 0.72) {
        if (nestTarget !== item) { clearNest(); nestTarget = item; item.classList.add("nest-target"); }
      } else {
        clearNest();
        if (y > rect.height / 2) item.after(dragEl); else item.before(dragEl);
      }
    });

    container.addEventListener("dragend", function () {
      if (!dragEl) return;
      dragEl.classList.remove("dragging");
      var inThis = dragEl.parentNode === container;
      var nt = nestTarget, handled = dragState.handled;
      var draggedId = dragState.id, draggedKind = dragState.kind;
      clearNest();
      dragEl = null;
      dragState.kind = null;
      if (handled) return;
      if (nt && nt.dataset.id && nt.dataset.id !== draggedId) {
        if (draggedKind === "cat") return moveCat(draggedId, "cat:" + nt.dataset.id);
        if (draggedKind === "menu-top") return moveMenu(draggedId, nt.dataset.id);
      }
      if (!inThis || !url || locked) return;
      var ids = Array.prototype.map.call(
        container.querySelectorAll(":scope > " + itemSel),
        function (t) { return t.dataset.id; }
      );
      fetch(url, {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
        body: JSON.stringify({ order: ids }),
      }).catch(function () {});
    });
  }
  document.querySelectorAll("[data-reorder-url]").forEach(setupDrag);

  function moveCat(id, target) {
    if (!window.CHITRALAHAR_CATMOVE_URL) return;
    fetch(window.CHITRALAHAR_CATMOVE_URL.replace("/0/", "/" + id + "/"), {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ target: target }),
    }).then(function (r) { return r.json(); })
      .then(function (d) { if (d && d.ok && d.reload) window.location.reload();
                           else if (d && d.error) window.alert(d.error); })
      .catch(function () {});
  }

  /* ----- Drop zones (conditional preventDefault by dragged kind) ----- */
  function dropZone(el, accepts, onDrop) {
    el.addEventListener("dragover", function (e) {
      if (!accepts()) return;
      e.preventDefault();
      el.classList.add("drop-hot");
    });
    el.addEventListener("dragleave", function (e) {
      if (!el.contains(e.relatedTarget)) el.classList.remove("drop-hot");
    });
    el.addEventListener("drop", function (e) {
      if (!accepts()) return;
      e.preventDefault();
      el.classList.remove("drop-hot");
      dragState.handled = true;
      onDrop(e);
    });
  }

  function reloadIf(d) { if (d && d.ok && d.reload) window.location.reload(); }

  // Photos -> category/subcategory drop targets (tree nodes or chips)
  document.querySelectorAll(".assign-target").forEach(function (target) {
    dropZone(target, function () { return dragState.kind === "photo"; }, function () {
      assignPhotos(dragState.ids.slice(), target.dataset.assignCat || "", target.dataset.assignSub || "", target);
    });
  });

  // Category tree: expand / collapse a branch
  document.querySelectorAll(".tree-toggle").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var cat = btn.closest(".tree-cat");
      if (cat) cat.classList.toggle("open");
    });
  });

  // Copy share link to clipboard
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    e.preventDefault();
    var wrap = btn.closest(".share-copy");
    var input = wrap && wrap.querySelector(".share-link");
    if (!input) return;
    input.focus(); input.select();
    var flash = function () {
      var t = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(function () { btn.textContent = t; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(input.value).then(flash, function () {
        try { document.execCommand("copy"); } catch (_) {} flash();
      });
    } else {
      try { document.execCommand("copy"); } catch (_) {}
      flash();
    }
  });

  // Subcategory -> another category card (reparent)
  document.querySelectorAll("[data-drop-cat]").forEach(function (zone) {
    var catId = zone.dataset.dropCat;
    dropZone(zone,
      function () { return dragState.kind === "sub" && dragState.parent !== catId; },
      function () { moveSub(dragState.id, "cat:" + catId); });
  });

  // Subcategory -> top-level (promote)
  document.querySelectorAll('[data-drop-top="cat"]').forEach(function (zone) {
    dropZone(zone, function () { return dragState.kind === "sub"; },
      function () { moveSub(dragState.id, "top"); });
  });

  function moveSub(id, target) {
    if (!window.CHITRALAHAR_SUBMOVE_URL) return;
    fetch(window.CHITRALAHAR_SUBMOVE_URL.replace("/0/", "/" + id + "/"), {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ target: target }),
    }).then(function (r) { return r.json(); }).then(reloadIf).catch(function () {});
  }

  // Menu sub-item -> another top item (reparent)
  document.querySelectorAll("[data-drop-menu]").forEach(function (zone) {
    var pid = zone.dataset.dropMenu;
    dropZone(zone,
      function () { return dragState.kind === "menu-child" && dragState.parent !== pid; },
      function () { moveMenu(dragState.id, pid); });
  });

  // Menu sub-item -> top level (promote)
  document.querySelectorAll('[data-drop-top="menu"]').forEach(function (zone) {
    dropZone(zone, function () { return dragState.kind === "menu-child"; },
      function () { moveMenu(dragState.id, "top"); });
  });

  function moveMenu(id, parent) {
    if (!window.CHITRALAHAR_MENUMOVE_URL) return;
    fetch(window.CHITRALAHAR_MENUMOVE_URL.replace("/0/", "/" + id + "/"), {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ parent: parent }),
    }).then(function (r) { return r.json(); }).then(reloadIf).catch(function () {});
  }

  /* ---------- Markdown editor: write / preview tabs ---------- */
  document.querySelectorAll(".editor-tabs").forEach(function (tabs) {
    var editor = tabs.closest(".editor-main");
    if (!editor) return;
    tabs.addEventListener("click", function (e) {
      var btn = e.target.closest(".tab");
      if (!btn) return;
      var which = btn.dataset.tab;
      tabs.querySelectorAll(".tab").forEach(function (t) { t.classList.toggle("is-active", t === btn); });
      editor.querySelectorAll(".editor-pane").forEach(function (p) { p.hidden = p.dataset.pane !== which; });
      if (which === "preview") runPreview(editor);
    });
  });

  function runPreview(editor) {
    var body = editor.querySelector(".body-input");
    var out = editor.querySelector(".preview-out");
    if (!body || !out || !window.CHITRALAHAR_PREVIEW_URL) return;
    if (!body.value.trim()) { out.innerHTML = '<p class="muted">Nothing to preview yet.</p>'; return; }
    out.innerHTML = '<p class="muted">Rendering…</p>';
    fetch(window.CHITRALAHAR_PREVIEW_URL, {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ text: body.value }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) { out.innerHTML = d.html || ""; })
      .catch(function () { out.innerHTML = '<p class="muted">Preview unavailable.</p>'; });
  }

  /* ---------- Upload dropzone ---------- */
  var dz = document.getElementById("dropzone");
  if (dz) {
    var input = document.getElementById("fileInput");
    var status = document.getElementById("dzStatus");
    var openPicker = function () { input.click(); };

    dz.addEventListener("click", function (e) {
      if (e.target === input) return;
      if (e.target.closest(".dz-controls")) return;
      openPicker();
    });
    var controls = dz.querySelector(".dz-controls");
    if (controls) controls.addEventListener("click", function (e) { e.stopPropagation(); });

    ["dragenter", "dragover"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("is-drag"); });
    });
    ["dragleave", "dragend", "drop"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) {
        if (ev === "dragleave" && dz.contains(e.relatedTarget)) return;
        dz.classList.remove("is-drag");
      });
    });
    dz.addEventListener("drop", function (e) {
      e.preventDefault();
      if (!e.dataTransfer || !e.dataTransfer.files.length) return;
      try { input.files = e.dataTransfer.files; } catch (_) {}
      submitUpload(e.dataTransfer.files.length);
    });
    input.addEventListener("change", function () {
      if (input.files && input.files.length) submitUpload(input.files.length);
    });
    function submitUpload(count) {
      var label = count + " photo" + (count !== 1 ? "s" : "");
      if (status) {
        status.hidden = false;
        status.innerHTML = 'Uploading ' + label + '… <span class="dz-pct">0%</span>' +
          '<span class="dz-bar"><span class="dz-bar-fill"></span></span>';
      }
      dz.classList.add("is-uploading");
      // XHR (not fetch) so we get upload progress events.
      var xhr = new XMLHttpRequest();
      xhr.open("POST", dz.action);
      xhr.upload.addEventListener("progress", function (e) {
        if (!e.lengthComputable || !status) return;
        var pct = Math.round((e.loaded / e.total) * 100);
        var fill = status.querySelector(".dz-bar-fill");
        var num = status.querySelector(".dz-pct");
        if (fill) fill.style.width = pct + "%";
        if (num) num.textContent = pct < 100 ? pct + "%" : "processing…";
      });
      xhr.onload = xhr.onerror = function () { window.location.reload(); };
      xhr.send(new FormData(dz));
    }
  }

  /* ---------- Modal close for edit/move popovers (Esc or backdrop click) ---------- */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll("details.row-edit[open]").forEach(function (d) { d.open = false; });
  });
  document.addEventListener("click", function (e) {
    // The fixed full-screen ::before backdrop belongs to the open <details>, so a
    // click on it targets the <details> element itself.
    if (e.target.tagName === "DETAILS" && e.target.classList.contains("row-edit") && e.target.open) {
      e.target.open = false;
    }
  });

  /* ---------- Markdown formatting toolbar ---------- */
  document.querySelectorAll("[data-md-toolbar]").forEach(function (bar) {
    var main = bar.closest(".editor-main");
    var ta = main && main.querySelector(".body-input");
    if (!ta) return;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-md]");
      if (!btn) return;
      e.preventDefault();
      applyMd(ta, btn.dataset.md);
    });
  });

  function applyMd(ta, kind) {
    var s = ta.selectionStart, en = ta.selectionEnd;
    var before = ta.value.slice(0, s), sel = ta.value.slice(s, en), after = ta.value.slice(en);
    function wrap(pre, post, ph) {
      var t = sel || ph;
      ta.value = before + pre + t + post + after;
      ta.focus();
      ta.selectionStart = before.length + pre.length;
      ta.selectionEnd = ta.selectionStart + t.length;
    }
    function lines(prefix, ph) {
      var t = sel || ph;
      var out = t.split("\n").map(function (l) { return prefix + l; }).join("\n");
      ta.value = before + out + after;
      ta.focus();
      ta.selectionStart = before.length;
      ta.selectionEnd = before.length + out.length;
    }
    if (kind === "bold") wrap("**", "**", "bold text");
    else if (kind === "italic") wrap("*", "*", "italic text");
    else if (kind === "h2") lines("## ", "Heading");
    else if (kind === "ul") lines("- ", "List item");
    else if (kind === "quote") lines("> ", "Quote");
    else if (kind === "link") {
      var u = window.prompt("Link URL", "https://");
      if (u) wrap("[", "](" + u + ")", "link text");
    }
  }
})();
