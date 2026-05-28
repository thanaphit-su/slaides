(function () {
  var slaides = window.slaides;
  if (!slaides) return;

  var promptEl = document.getElementById("prompt");
  var form = document.getElementById("form");
  var input = document.getElementById("input");
  var listEl = document.getElementById("list");
  var statusEl = document.getElementById("status");

  var entries = [];

  function paintProps() {
    var p = slaides.props || {};
    promptEl.textContent = p.prompt || "";
    input.placeholder = p.placeholder || "Your question…";
  }

  function paintEntries() {
    listEl.textContent = "";
    if (!entries.length) {
      statusEl.textContent = "No questions yet.";
      return;
    }
    statusEl.textContent = entries.length === 1 ? "1 question" : entries.length + " questions";
    // Newest at the top — append aggregator returns chronological; reverse for display.
    for (var i = entries.length - 1; i >= 0; i--) {
      var li = document.createElement("li");
      li.className = "qa-board-entry";
      li.textContent = String(entries[i]);
      listEl.appendChild(li);
    }
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var value = (input.value || "").trim();
    if (!value) return;
    if (typeof slaides.contribute === "function") {
      slaides.contribute(value);
    }
    input.value = "";
  });

  paintProps();
  paintEntries();
  slaides.on && slaides.on("props", paintProps);
  slaides.on && slaides.on("state", function (next) {
    var items = next && Array.isArray(next.entries) ? next.entries : [];
    entries = items;
    paintEntries();
  });
})();
