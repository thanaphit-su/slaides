(function () {
  var slaides = window.slaides;
  if (!slaides) return;

  function paint(props) {
    var p = props || {};
    document.querySelectorAll("[data-bind]").forEach(function (el) {
      var key = el.getAttribute("data-bind");
      el.textContent = (p && p[key] != null) ? String(p[key]) : "";
    });
  }

  paint(slaides.props || {});
  slaides.on && slaides.on("props", function (next) {
    paint(next || {});
  });
})();
