(function () {
  var slaides = window.slaides;
  if (!slaides) return;

  var img = document.getElementById("img");
  var caption = document.getElementById("caption");
  var prev = document.getElementById("prev");
  var next = document.getElementById("next");
  var dots = document.getElementById("dots");

  var index = 0;
  var timer = 0;

  function items() {
    var p = slaides.props || {};
    return Array.isArray(p.images) ? p.images.filter(function (e) {
      return e && typeof e === "object" && typeof e.url === "string" && e.url.length > 0;
    }) : [];
  }

  function paint() {
    var list = items();
    if (!list.length) {
      img.removeAttribute("src");
      img.alt = "";
      caption.textContent = "No images yet — paste an image URL in props.";
      dots.textContent = "";
      prev.disabled = true;
      next.disabled = true;
      return;
    }
    if (index >= list.length) index = 0;
    if (index < 0) index = list.length - 1;
    var cur = list[index];

    img.src = cur.url;
    img.alt = cur.caption ? String(cur.caption) : "";
    caption.textContent = cur.caption ? String(cur.caption) : "";

    prev.disabled = list.length < 2;
    next.disabled = list.length < 2;

    dots.textContent = "";
    for (var i = 0; i < list.length; i++) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.className = "carousel-dot" + (i === index ? " is-active" : "");
      b.setAttribute("aria-label", "Go to image " + (i + 1));
      b.dataset.index = String(i);
      (function (target) {
        b.addEventListener("click", function () { go(target); });
      })(i);
      li.appendChild(b);
      dots.appendChild(li);
    }
  }

  function go(i) {
    index = i;
    paint();
    restartAuto();
  }

  function step(delta) {
    var list = items();
    if (!list.length) return;
    index = (index + delta + list.length) % list.length;
    paint();
    restartAuto();
  }

  function restartAuto() {
    if (timer) { clearInterval(timer); timer = 0; }
    var p = slaides.props || {};
    if (!p.auto_advance) return;
    var ms = Number(p.interval_ms || 4000);
    if (ms < 1000) ms = 1000;
    timer = setInterval(function () { step(1); }, ms);
  }

  prev.addEventListener("click", function () { step(-1); });
  next.addEventListener("click", function () { step(1); });

  paint();
  restartAuto();
  slaides.on && slaides.on("props", function () { paint(); restartAuto(); });
})();
