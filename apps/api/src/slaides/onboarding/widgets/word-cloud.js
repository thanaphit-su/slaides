(function () {
  var slaides = window.slaides;
  if (!slaides) return;

  var promptEl = document.getElementById("prompt");
  var form = document.getElementById("form");
  var input = document.getElementById("input");
  var wordsEl = document.getElementById("words");
  var statusEl = document.getElementById("status");

  var words = [];

  function paintProps() {
    var p = slaides.props || {};
    promptEl.textContent = p.prompt || "";
    var max = Number(p.max_length || 40);
    input.maxLength = max;
  }

  function paintWords() {
    wordsEl.textContent = "";
    if (!words.length) {
      statusEl.textContent = "No words yet.";
      return;
    }
    statusEl.textContent = words.length === 1 ? "1 word" : words.length + " words";
    // Size by order of arrival (earlier = bigger) so the cloud has visual rhythm.
    var max = words.length;
    words.forEach(function (word, index) {
      var li = document.createElement("li");
      li.className = "word-cloud-word";
      li.textContent = String(word);
      var size = 1 + ((max - index) / max) * 1.1; // 1.0–2.1rem
      li.style.fontSize = size.toFixed(2) + "rem";
      wordsEl.appendChild(li);
    });
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
  paintWords();
  slaides.on && slaides.on("props", paintProps);
  slaides.on && slaides.on("state", function (next) {
    // set_union exposes { items: [...] }; tolerate older shape too.
    var items = next && Array.isArray(next.items) ? next.items : [];
    words = items;
    paintWords();
  });
})();
