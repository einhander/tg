(function () {
  var plotResizeObserver = typeof ResizeObserver === "undefined"
    ? null
    : new ResizeObserver(function (entries) {
        entries.forEach(function (entry) {
          var plot = entry.target.classList.contains("main-plot")
            ? entry.target
            : entry.target.querySelector(".main-plot");
          resizePlot(plot);
        });
      });

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
    var config = Object.assign({responsive: true}, figure.config || {});

    if (element.classList.contains("js-plotly-plot")) {
      Plotly.react(element, figure.data || [], layout, config);
      return;
    }

    Plotly.newPlot(element, figure.data || [], layout, config);
  }

  function resizePlot(element) {
    if (!element || typeof Plotly === "undefined" || !element.classList.contains("js-plotly-plot")) {
      return;
    }

    // Only resize if the plot is actually visible (not in a hidden tab)
    var style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden') {
      return;
    }

    window.requestAnimationFrame(function () {
      Plotly.Plots.resize(element);
    });
  }

  function resizePlots(root) {
    var scope = root || document;
    if (scope.classList && scope.classList.contains("main-plot")) {
      resizePlot(scope);
    }

    var plots = scope.querySelectorAll ? scope.querySelectorAll(".main-plot") : [];
    plots.forEach(resizePlot);
  }

  function collectPlots(root) {
    var scope = root || document;
    var plots = [];

    if (scope.classList && scope.classList.contains("main-plot") && scope.getAttribute("data-plot-json")) {
      plots.push(scope);
    }

    if (scope.querySelectorAll) {
      scope.querySelectorAll(".main-plot[data-plot-json]").forEach(function (plot) {
        plots.push(plot);
      });
    }

    return plots;
  }

  function scheduleAfterLayout(callback) {
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(callback);
    });
  }

  function schedulePlotUpdate(plots) {
    if (!plots.length) {
      return;
    }

    scheduleAfterLayout(function () {
      plots.forEach(function (plot) {
        renderPlot(plot);
        resizePlot(plot);
      });
    });
  }

  function observePlotContainers(root) {
    if (!plotResizeObserver) {
      return;
    }

    var scope = root || document;
    var plots = [];

    if (scope.classList && scope.classList.contains("main-plot")) {
      plots.push(scope);
    }

    if (scope.querySelectorAll) {
      scope.querySelectorAll(".main-plot").forEach(function (plot) {
        plots.push(plot);
      });
    }

    plots.forEach(function (plot) {
      if (plot.dataset.resizeObserved === "1") {
        return;
      }

      plot.dataset.resizeObserved = "1";
      plotResizeObserver.observe(plot);
      if (plot.parentElement) {
        plotResizeObserver.observe(plot.parentElement);
      }
    });
  }

  function renderPlots(root) {
    schedulePlotUpdate(collectPlots(root));
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
          resizePlots(targetPane);
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

  function bindSgToggle(root) {
    var scope = root || document;
    scope.querySelectorAll("input[data-sg-toggle]").forEach(function (sgCheckbox) {
      if (sgCheckbox.dataset.sgBound === "1") {
        return;
      }
      sgCheckbox.dataset.sgBound = "1";

      var targetIds = sgCheckbox.getAttribute("data-sg-toggle").split(",");
      var sgControls = [];
      for (var t = 0; t < targetIds.length; t++) {
        var el = document.getElementById(targetIds[t].trim());
        if (el) {
          sgControls.push(el);
        }
      }
      if (sgControls.length === 0) {
        return;
      }

      var update = function () {
        for (var i = 0; i < sgControls.length; i++) {
          if (sgCheckbox.checked) {
            sgControls[i].classList.add("visible");
          } else {
            sgControls[i].classList.remove("visible");
          }
        }
      };

      sgCheckbox.addEventListener("change", update);
      update();
    });
  }

  function bindVisibilityToggles(root) {
    var scope = root || document;
    scope.querySelectorAll("form input[data-visibility-toggle]").forEach(function (checkbox) {
      if (checkbox.dataset.visibilityToggleBound === "1") {
        return;
      }
      checkbox.dataset.visibilityToggleBound = "1";

      var fieldName = checkbox.getAttribute("data-visibility-toggle");
      var form = checkbox.form || checkbox.closest("form");
      if (!form) {
        return;
      }
      var hidden = form.querySelector("input[type='hidden'][data-visibility-hidden='" + fieldName + "']");
      if (!hidden) {
        return;
      }

      var sync = function () {
        hidden.value = checkbox.checked ? "1" : "0";
      };

      checkbox.addEventListener("change", sync);
      sync();
    });
  }

  function init(root) {
    bindTabs(root);
    bindRangeControls(root);
    bindSgToggle(root);
    bindVisibilityToggles(root);
    renderPlots(root);
    observePlotContainers(root);
  }

  function getPostSwapRoot(event) {
    if (event.detail && event.detail.elt) {
      return event.detail.elt;
    }

    return event.target;
  }

  function handlePostSwap(event) {
    var root = getPostSwapRoot(event);
    init(root);

    var target = event.detail && event.detail.target ? event.detail.target : null;
    if (target && target !== root) {
      schedulePlotUpdate(collectPlots(target));
      observePlotContainers(target);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    init(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    handlePostSwap(event);
  });

  window.addEventListener("resize", function () {
    resizePlots(document);
  });
})();
