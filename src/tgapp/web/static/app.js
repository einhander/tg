(function () {
  function parsePlotJson(raw) {
    if (!raw) {
      return null;
    }

    try {
      return JSON.parse(raw);
    } catch (error) {
      console.warn("Could not parse plot JSON", error);
      return null;
    }
  }

  function normalizeFigure(payload) {
    if (!payload) {
      return null;
    }

    if (payload.data || payload.layout) {
      return {
        data: payload.data || [],
        layout: payload.layout || {},
        config: payload.config || {}
      };
    }

    if (payload.figure && (payload.figure.data || payload.figure.layout)) {
      return {
        data: payload.figure.data || [],
        layout: payload.figure.layout || {},
        config: payload.config || payload.figure.config || {}
      };
    }

    return null;
  }

  function renderPlot(element) {
    if (!element || typeof Plotly === "undefined") {
      return;
    }

    var payload = parsePlotJson(element.getAttribute("data-plot-json"));
    var figure = normalizeFigure(payload);
    if (!figure) {
      element.innerHTML = "";
      return;
    }

    var layout = Object.assign({}, figure.layout || {});
    if (!layout.height) {
      var declaredHeight = element.getAttribute("data-plot-height");
      if (declaredHeight && declaredHeight.indexOf("px") !== -1) {
        layout.height = parseInt(declaredHeight, 10);
      }
    }

    var config = Object.assign({responsive: true}, figure.config || {});

    Plotly.newPlot(element, figure.data || [], layout, config).then(function () {
      bindPlotSelection(element);
    });
  }

  function renderPlots(root) {
    var scope = root || document;
    var plots = scope.querySelectorAll("#main-plot[data-plot-json]");
    plots.forEach(renderPlot);
  }

  function replaceEffectBlock(html) {
    var parser = new DOMParser();
    var doc = parser.parseFromString(html, "text/html");
    var incoming = doc.querySelector("#effect-block");
    var current = document.querySelector("#effect-block");

    if (incoming && current) {
      current.replaceWith(incoming);
    } else if (current) {
      current.innerHTML = html;
    }
  }

  function bindPlotSelection(element) {
    if (!element || element.dataset.selectionBound === "1") {
      return;
    }

    element.dataset.selectionBound = "1";

    element.on("plotly_selected", function (eventData) {
      if (!eventData || !eventData.range || !eventData.range.x) {
        return;
      }

      var xmin = eventData.range.x[0];
      var xmax = eventData.range.x[1];
      var effectUrl = element.getAttribute("data-effect-url");
      var sessionId = element.getAttribute("data-session-id") || "";
      var body = new URLSearchParams();

      if (!effectUrl) {
        return;
      }

      body.append("xmin", xmin);
      body.append("xmax", xmax);
      if (sessionId) {
        body.append("session_id", sessionId);
      }

      fetch(effectUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "HX-Request": "true"
        },
        body: body.toString()
      })
        .then(function (response) { return response.text(); })
        .then(replaceEffectBlock)
        .catch(function (error) {
          console.warn("Could not load effect text", error);
        });
    });
  }

  function bindTabs(root) {
    var scope = root || document;
    var tabLinks = scope.querySelectorAll(".tab-link[data-tab-target]");

    tabLinks.forEach(function (link) {
      if (link.dataset.tabsBound === "1") {
        return;
      }

      link.dataset.tabsBound = "1";
      link.addEventListener("click", function (event) {
        event.preventDefault();
        var targetId = link.getAttribute("data-tab-target");
        var list = link.closest(".app-tabs");
        var content = document.querySelector(".app-tab-content");
        if (!list || !content) {
          return;
        }

        list.querySelectorAll("li").forEach(function (item) {
          item.classList.remove("active");
        });
        content.querySelectorAll(".tab-pane").forEach(function (pane) {
          pane.classList.remove("active");
        });

        link.parentElement.classList.add("active");
        var targetPane = document.getElementById(targetId);
        if (targetPane) {
          targetPane.classList.add("active");
        }
      });
    });
  }

  function bindRangeControls(root) {
    var scope = root || document;
    scope.querySelectorAll(".range-control").forEach(function (input) {
      if (input.dataset.rangeBound === "1") {
        return;
      }

      input.dataset.rangeBound = "1";
      var valueBlock = input.parentElement.querySelector(".range-value");
      var update = function () {
        if (valueBlock) {
          valueBlock.textContent = input.value;
        }
      };
      input.addEventListener("input", update);
      update();
    });
  }

  function init(root) {
    bindTabs(root);
    bindRangeControls(root);
    renderPlots(root);
  }

  document.addEventListener("DOMContentLoaded", function () {
    init(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    init(event.target);
  });
})();
