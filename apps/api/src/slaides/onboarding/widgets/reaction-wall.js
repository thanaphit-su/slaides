(function () {
  var slaides = window.slaides;
  if (!slaides) return;

  var keysEl = document.getElementById("keys");
  var statusEl = document.getElementById("status");

  var counts = {};

  function paint() {
    var p = slaides.props || {};
    var keys = Array.isArray(p.keys) ? p.keys : [];

    keysEl.textContent = "";
    var total = 0;
    keys.forEach(function (entry) {
      if (!entry || entry.key == null) return;
      var key = String(entry.key);
      var label = entry.label != null ? String(entry.label) : key;
      var count = Number(counts[key] || 0);
      total += count;

      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "reaction-wall-key";
      btn.dataset.key = key;
      btn.addEventListener("click", function () { tap(key); });

      var glyph = document.createElement("span");
      glyph.className = "reaction-wall-glyph";
      glyph.textContent = label;

      var num = document.createElement("span");
      num.className = "reaction-wall-count";
      num.textContent = String(count);

      btn.appendChild(glyph);
      btn.appendChild(num);
      li.appendChild(btn);
      keysEl.appendChild(li);
    });

    if (total === 0) {
      statusEl.textContent = "Tap a reaction.";
    } else {
      statusEl.textContent = total === 1 ? "1 reaction" : total + " reactions";
    }
  }

  function tap(key) {
    if (typeof slaides.contribute === "function") {
      slaides.contribute(key);
    }
  }

  paint();
  slaides.on && slaides.on("props", paint);
  slaides.on && slaides.on("state", function (next) {
    var tally = next && next.tally && typeof next.tally === "object" ? next.tally : {};
    counts = tally;
    paint();
  });
})();
