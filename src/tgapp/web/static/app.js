(function () {
  var plotObservers = new WeakMap();

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

  var plotRenderQueue = new WeakMap();
  var plotRenderCount = new WeakMap();
  var scheduledPlots = new WeakSet();

  function incrementRenderCount(plot) {
    var count = (plotRenderCount.get(plot) || 0) + 1;
    plotRenderCount.set(plot, count);
    console.debug("Plot render count:", count, plot);
  }

  function queuePlotRender(plot) {
    var previous = plotRenderQueue.get(plot) || Promise.resolve();

    var next = previous
        .catch(function (error) {
            console.error("Previous Plotly render failed:", error);
        })
        .then(function () {
            if (plot._renderFailed) return;
            if (!plot.isConnected) {
                return false;
            }
            return waitForPlotSize(plot);
        })
        .then(function (hasSize) {
            if (!hasSize || !plot.isConnected) {
                return false;
            }
            return renderPlot(plot).then(function () {
                return true;
            });
        })
        .then(function (rendered) {
            if (!rendered || !plot.isConnected) {
                return false;
            }
            return nextAnimationFrame().then(function () {
                return true;
            });
        })
        .then(function (rendered) {
            if (!rendered || !plot.isConnected || !plot.classList.contains("js-plotly-plot")) {
                return;
            }
            return Plotly.Plots.resize(plot);
        })
        .catch(function (error) {
            if (error.message === "Plot payload is missing") {
                plot._renderFailed = true;
                showPlotError(plot);
                return;
            }
            console.error("Plotly render failed:", error);
            showPlotError(plot);
        });

    plotRenderQueue.set(plot, next);
    return next;
  }

  function schedulePlotRender(plot) {
    if (scheduledPlots.has(plot)) {
      return;
    }

    scheduledPlots.add(plot);

    queueMicrotask(function () {
      scheduledPlots.delete(plot);
      queuePlotRender(plot);
    });
  }

  function waitForPlotSize(plot, attempts) {
    var remaining = typeof attempts === "number" ? attempts : 30;

    if (!plot.isConnected) {
        return Promise.resolve(false);
    }

    if (isPlotVisible(plot)) {
        return Promise.resolve(true);
    }

    if (remaining <= 0) {
        return Promise.resolve(false);
    }

    return nextAnimationFrame().then(function () {
        return waitForPlotSize(plot, remaining - 1);
    });
  }

  function nextAnimationFrame() {
    return new Promise(function (resolve) {
      requestAnimationFrame(function () { requestAnimationFrame(resolve); });
    });
  }

  function isPlotVisible(plot) {
    if (!plot || !plot.isConnected) {
        return false;
    }

    var rect = plot.getBoundingClientRect();

    return rect.width > 0 && rect.height > 0;
  }

  function readPlotPayload(plot) {
    if (!plot) return null;
    var raw = plot.getAttribute("data-plot-json");
    if (!raw) return null;
    return normalizeFigure(parsePlotJson(raw));
  }

  function showPlotError(plot) {
    if (!plot) return;
    plot.classList.add("plot-error");
    var errorDiv = document.createElement("div");
    errorDiv.className = "plot-error-message";
    errorDiv.textContent = "Ошибка отрисовки графика. Проверьте консоль.";
    plot.appendChild(errorDiv);
  }

  function observePlot(plot) {
    if (!plot || !plotObservers.has(plot)) {
        var observer = new ResizeObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!plot.isConnected || !plot.classList.contains("js-plotly-plot")) {
                    return;
                }
                Plotly.Plots.resize(plot).catch(function (error) {
                    console.error("Plotly resize failed:", error);
                });
            });
        });
        observer.observe(plot);
        plotObservers.set(plot, observer);
    }
  }

  function disconnectPlotObserver(plot) {
    var observer = plotObservers.get(plot);
    if (!observer) return;
    observer.disconnect();
    plotObservers.delete(plot);
  }

  function renderPlot(plot) {
    // Remove previous error indicator if present
    var existingError = plot.querySelector(".plot-error-message");
    if (existingError) existingError.remove();

    var payload = readPlotPayload(plot);

    if (!payload) {
        return Promise.reject(new Error("Plot payload is missing"));
    }

    incrementRenderCount(plot);

    var data = payload.data || [];
    var layout = payload.layout || {};
    var config = payload.config || {};

    console.debug("Rendering plot", {
        connected: plot.isConnected,
        width: plot.getBoundingClientRect().width,
        height: plot.getBoundingClientRect().height,
        hasXAxisTitle: Boolean(layout.xaxis?.title),
        hasYAxisTitle: Boolean(layout.yaxis?.title),
        hasLegend: Boolean(layout.legend)
    });

    if (plot.classList.contains("js-plotly-plot")) {
        return Plotly.react(plot, data, layout, config);
    }

    return Plotly.newPlot(plot, data, layout, config);
  }

  function resizePlot(element) {
    if (!element || typeof Plotly === "undefined" || !element.classList.contains("js-plotly-plot")) {
      return;
    }

    // Only resize if the plot is actually visible (not in a hidden tab)
    var style = window.getComputedStyle(element);
    if (
      style.display === 'none' ||
      style.visibility === 'hidden' ||
      !element.isConnected ||
      element.clientWidth === 0 ||
      element.clientHeight === 0
    ) {
      return;
    }

    window.requestAnimationFrame(function () {
      Promise.resolve(Plotly.Plots.resize(element)).catch(function () {
        // Plotly can reject while a just-swapped plot is still settling.
      });
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

  function initPlots(root) {
    collectPlots(root).forEach(function (plot) {
      observePlot(plot);
      schedulePlotRender(plot);
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
    initPlots(root);
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
  }

  document.addEventListener("DOMContentLoaded", function () {
    init(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    handlePostSwap(event);
  });

  document.body.addEventListener("htmx:oobAfterSwap", function (event) {
    var root = event.detail && event.detail.elt ? event.detail.elt : event.target;
    if (root) init(root);
  });

  document.body.addEventListener("htmx:beforeCleanupElement", function (event) {
    var elt = event.detail && event.detail.elt ? event.detail.elt : event.target;
    if (!elt) return;

    var plots = [];

    if (elt.matches && elt.matches(".js-plotly-plot")) {
        plots.push(elt);
    }

    if (elt.querySelectorAll) {
        elt.querySelectorAll(".js-plotly-plot").forEach(function (plot) {
            plots.push(plot);
        });
    }

    plots.forEach(function (plot) {
        disconnectPlotObserver(plot);
        try { Plotly.purge(plot); } catch (e) {}
    });
  });

  window.addEventListener("resize", function () {
    resizePlots(document);
  });
})();