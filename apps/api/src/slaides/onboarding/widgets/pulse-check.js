(function () {
  var slaides = window.slaides;
  if (!slaides) return;

  var promptEl = document.getElementById("prompt");
  var scaleEl = document.getElementById("scale");
  var histogramEl = document.getElementById("histogram");
  var statusEl = document.getElementById("status");

  var localChoice = null;
  var distribution = {}; // { "1": count, "2": count, ... }

  function labelsArray() {
    var p = slaides.props || {};
    var labels = Array.isArray(p.labels) ? p.labels : [];
    if (labels.length === 0) labels = ["1", "2", "3", "4", "5"];
    return labels;
  }

  function paintScale() {
    var p = slaides.props || {};
    promptEl.textContent = p.prompt || "";
    var labels = labelsArray();

    scaleEl.textContent = "";
    labels.forEach(function (label, index) {
      var key = String(index + 1);
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pulse-check-step";
      btn.dataset.key = key;
      btn.setAttribute("aria-pressed", localChoice === key ? "true" : "false");
      if (localChoice === key) btn.classList.add("is-picked");

      var num = document.createElement("span");
      num.className = "pulse-check-step-num";
      num.textContent = key;

      var caption = document.createElement("span");
      caption.className = "pulse-check-step-label";
      caption.textContent = String(label);

      btn.appendChild(num);
      btn.appendChild(caption);
      btn.addEventListener("click", function () { setPulse(key); });
      scaleEl.appendChild(btn);
    });
  }

  function paintHistogram() {
    var labels = labelsArray();
    histogramEl.textContent = "";

    var max = 0;
    var total = 0;
    labels.forEach(function (_, i) {
      var c = Number(distribution[String(i + 1)] || 0);
      if (c > max) max = c;
      total += c;
    });

    labels.forEach(function (label, i) {
      var key = String(i + 1);
      var count = Number(distribution[key] || 0);
      var pct = max > 0 ? Math.round((count / max) * 100) : 0;

      var li = document.createElement("li");
      li.className = "pulse-check-bar-row";

      var label$ = document.createElement("span");
      label$.className = "pulse-check-bar-label";
      label$.textContent = key + ". " + String(label);

      var track = document.createElement("span");
      track.className = "pulse-check-bar-track";
      var fill = document.createElement("span");
      fill.className = "pulse-check-bar-fill";
      fill.style.width = pct + "%";
      track.appendChild(fill);

      var num = document.createElement("span");
      num.className = "pulse-check-bar-count";
      num.textContent = String(count);

      li.appendChild(label$);
      li.appendChild(track);
      li.appendChild(num);
      histogramEl.appendChild(li);
    });

    statusEl.textContent = total === 0 ? "No responses yet." : total === 1 ? "1 response" : total + " responses";
  }

  function setPulse(key) {
    localChoice = key;
    if (typeof slaides.contribute === "function") {
      slaides.contribute(key);
    }
    paintScale();
  }

  paintScale();
  paintHistogram();
  slaides.on && slaides.on("props", function () {
    paintScale();
    paintHistogram();
  });
  slaides.on && slaides.on("state", function (next) {
    var dist = next && next.distribution && typeof next.distribution === "object"
      ? next.distribution
      : (next && next.tally && typeof next.tally === "object" ? next.tally : {});
    distribution = dist;
    paintHistogram();
  });
})();
