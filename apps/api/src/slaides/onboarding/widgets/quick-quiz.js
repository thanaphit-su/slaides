(function () {
  var slaides = window.slaides;
  if (!slaides) return;

  var form = document.getElementById("root");
  var questionEl = document.getElementById("question");
  var choicesEl = document.getElementById("choices");
  var submitEl = document.getElementById("submit");
  var resetEl = document.getElementById("reset");
  var feedbackEl = document.getElementById("feedback");

  var state = { picked: null, locked: false, correct: null };

  function render() {
    var p = slaides.props || {};
    var question = p.question || "";
    var choices = Array.isArray(p.choices) ? p.choices : [];
    var correct = p.correct_answer != null ? String(p.correct_answer) : "";

    questionEl.textContent = question;
    choicesEl.textContent = "";
    state.correct = correct;
    state.picked = null;
    state.locked = false;

    choices.forEach(function (choice) {
      if (!choice || choice.id == null) return;
      var id = String(choice.id);
      var label = choice.label != null ? String(choice.label) : id;

      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "quick-quiz-choice";
      btn.dataset.id = id;
      btn.textContent = label;
      btn.addEventListener("click", function () { pick(id); });
      li.appendChild(btn);
      choicesEl.appendChild(li);
    });

    submitEl.disabled = true;
    resetEl.hidden = true;
    feedbackEl.textContent = "";
    feedbackEl.dataset.tone = "";
  }

  function pick(id) {
    if (state.locked) return;
    state.picked = id;
    Array.prototype.forEach.call(choicesEl.querySelectorAll(".quick-quiz-choice"), function (el) {
      var on = el.dataset.id === id;
      el.classList.toggle("is-picked", on);
      el.setAttribute("aria-pressed", on ? "true" : "false");
    });
    submitEl.disabled = false;
  }

  function lock(verdict) {
    state.locked = true;
    submitEl.disabled = true;
    resetEl.hidden = false;
    Array.prototype.forEach.call(choicesEl.querySelectorAll(".quick-quiz-choice"), function (el) {
      el.disabled = true;
      if (el.dataset.id === state.correct) el.classList.add("is-correct");
      if (el.dataset.id === state.picked && verdict !== "correct") el.classList.add("is-wrong");
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (state.locked || !state.picked) return;
    var verdict = state.picked === state.correct ? "correct" : "wrong";
    feedbackEl.dataset.tone = verdict;
    feedbackEl.textContent = verdict === "correct" ? "Correct." : "Not quite — see the highlighted answer.";
    lock(verdict);
  });

  resetEl.addEventListener("click", function () {
    render();
  });

  render();
  slaides.on && slaides.on("props", function () { render(); });
})();
