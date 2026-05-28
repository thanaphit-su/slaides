(function () {
  var slaides = window.slaides;
  if (!slaides) return;

  var questionEl = document.getElementById("question");
  var choicesEl = document.getElementById("choices");
  var statusEl = document.getElementById("status");

  var localChoice = null;       // this viewer's currently-selected choice id
  var lastState = { tally: {}, voters: 0 };
  var lastChoiceList = [];      // last-seen list of choices, used when state arrives before props

  function render() {
    var p = slaides.props || {};
    var question = p.question || "";
    var choices = Array.isArray(p.choices) ? p.choices : [];
    lastChoiceList = choices;

    questionEl.textContent = question;
    choicesEl.textContent = "";

    var tally = lastState.tally || {};
    var voters = Number(lastState.voters || 0);

    choices.forEach(function (choice) {
      if (!choice || choice.id == null) return;
      var id = String(choice.id);
      var label = choice.label != null ? String(choice.label) : id;
      var count = Number(tally[id] || 0);
      var pct = voters > 0 ? Math.round((count / voters) * 100) : 0;

      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "live-poll-choice";
      btn.dataset.id = id;
      btn.setAttribute("aria-pressed", localChoice === id ? "true" : "false");
      if (localChoice === id) btn.classList.add("is-picked");

      var bar = document.createElement("span");
      bar.className = "live-poll-bar";
      bar.style.width = pct + "%";

      var labelEl = document.createElement("span");
      labelEl.className = "live-poll-label";
      labelEl.textContent = label;

      var countEl = document.createElement("span");
      countEl.className = "live-poll-count";
      countEl.textContent = count + " · " + pct + "%";

      btn.appendChild(bar);
      btn.appendChild(labelEl);
      btn.appendChild(countEl);
      btn.addEventListener("click", function () { vote(id); });
      li.appendChild(btn);
      choicesEl.appendChild(li);
    });

    statusEl.textContent = voters === 1 ? "1 vote" : voters + " votes";
  }

  function vote(id) {
    localChoice = id;
    if (typeof slaides.contribute === "function") {
      slaides.contribute(id);
    }
    render();
  }

  // Initial paint from props (presenter / instructor preview); subscribe to
  // both `props` (composer edits) and `state` (audience tally broadcasts).
  render();
  slaides.on && slaides.on("props", function () { render(); });
  slaides.on && slaides.on("state", function (next) {
    lastState = next && typeof next === "object" ? next : { tally: {}, voters: 0 };
    render();
  });
})();
