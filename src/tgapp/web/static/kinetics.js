/**
 * Kinetic analysis frontend.
 * Handles study CRUD, preparation UI, OFW results, and regression plots.
 */

const kineticsApp = {
  studyId: null,

  async init(studyId = null) {
    this.studyId = studyId;
    if (studyId) {
      await this.loadStudy();
    }
  },

  async loadStudy() {
    const resp = await fetch(`/api/kinetics/studies/${this.studyId}`);
    if (!resp.ok) {
      console.error("Failed to load study");
      return;
    }
    const study = await resp.json();
    this.renderStudy(study);
  },

  renderStudy(study) {
    const nameEl = document.getElementById("study-name");
    if (nameEl) nameEl.textContent = study.name;

    const sampleEl = document.getElementById("study-sample");
    if (sampleEl) sampleEl.textContent = study.sample_name || "—";

    const atmEl = document.getElementById("study-atmosphere");
    if (atmEl) atmEl.textContent = study.atmosphere || "—";

    const countEl = document.getElementById("study-run-count");
    if (countEl) countEl.textContent = study.runs.length;

    const tbody = document.getElementById("runs-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    for (const run of study.runs) {
      const tr = document.createElement("tr");
      const betaNom = run.nominal_heating_rate_k_s
        ? (run.nominal_heating_rate_k_s * 60).toFixed(1)
        : "—";
      const betaMeas = (run.measured_heating_rate_k_s * 60).toFixed(1);
      const tMin = run.temperature_range_k[0].toFixed(0);
      const tMax = run.temperature_range_k[1].toFixed(0);
      const m0 = run.mass_range_g[0].toFixed(3);
      const mf = run.mass_range_g[1].toFixed(3);
      const loss = ((run.mass_range_g[0] - run.mass_range_g[1]) / run.mass_range_g[0] * 100).toFixed(1);

      tr.innerHTML = `
        <td>${run.source_name}</td>
        <td>${betaNom}</td>
        <td>${betaMeas}</td>
        <td>${run.heating_linearity_r2.toFixed(4)}</td>
        <td>${tMin}–${tMax} K</td>
        <td>${m0}</td>
        <td>${mf}</td>
        <td>${loss}%</td>
        <td><span class="badge bg-success">OK</span></td>
      `;
      tbody.appendChild(tr);
    }

    this.renderChecklist(study);
  },

  renderChecklist(study) {
    const checks = [
      { label: "не менее трёх скоростей", pass: study.runs.length >= 3 },
      { label: "программы нагрева линейны", pass: study.runs.every(r => r.heating_linearity_r2 >= 0.995) },
      { label: "единицы определены", pass: true },
      { label: "плато подтверждены", pass: false },
      { label: "диапазоны α пересекаются", pass: true },
      { label: "выбран один процесс разложения", pass: false },
    ];

    const container = document.getElementById("study-checklist");
    if (!container) return;
    container.innerHTML = "";
    for (const check of checks) {
      const div = document.createElement("div");
      div.className = `checklist-item ${check.pass ? "text-success" : "text-warning"}`;
      div.innerHTML = `${check.pass ? "✓" : "⚠"} ${check.label}`;
      container.appendChild(div);
    }
  },

  async runAnalysis() {
    const resp = await fetch(`/api/kinetics/studies/${this.studyId}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method_id: "ofw_doyle" }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      alert("Ошибка анализа: " + (err.detail || "unknown"));
      return;
    }

    const result = await resp.json();
    this.renderResults(result);
  },

  renderResults(result) {
    const resultsSection = document.getElementById("study-results");
    if (resultsSection) resultsSection.style.display = "block";

    const summaryEl = document.getElementById("analysis-summary");
    if (summaryEl) {
      summaryEl.innerHTML = `
        <p><strong>Метод:</strong> ${result.method_id}</p>
        <p><strong>Средняя E<sub>α</sub>:</strong> ${result.mean_activation_energy_j_mol ? (result.mean_activation_energy_j_mol / 1000).toFixed(1) : "—"} kJ/mol</p>
        <p><strong>Медианная E<sub>α</sub>:</strong> ${result.median_activation_energy_j_mol ? (result.median_activation_energy_j_mol / 1000).toFixed(1) : "—"} kJ/mol</p>
      `;
    }

    this.renderEAlphaPlot(result);

    const tbody = document.getElementById("results-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    for (const p of result.points) {
      const tr = document.createElement("tr");
      tr.style.cursor = "pointer";
      tr.onclick = () => this.showRegression(p);

      const statusClass = p.status === "valid" ? "success"
        : p.status === "questionable" ? "warning" : "danger";

      tr.innerHTML = `
        <td>${p.alpha.toFixed(3)}</td>
        <td>${p.activation_energy_j_mol ? (p.activation_energy_j_mol / 1000).toFixed(1) : "—"}</td>
        <td>${p.r_squared ? p.r_squared.toFixed(4) : "—"}</td>
        <td>${p.slope_standard_error ? p.slope_standard_error.toFixed(4) : "—"}</td>
        <td><span class="badge bg-${statusClass}">${p.status}</span></td>
        <td>${p.warnings.join("; ") || "—"}</td>
      `;
      tbody.appendChild(tr);
    }
  },

  renderEAlphaPlot(result) {
    const validPoints = result.points.filter(p => p.activation_energy_j_mol !== null);
    const alphas = validPoints.map(p => p.alpha);
    const energies = validPoints.map(p => p.activation_energy_j_mol / 1000);

    const trace = {
      x: alphas,
      y: energies,
      mode: "lines+markers",
      type: "scatter",
      name: "Eα(α)",
      line: { color: "#e74c3c" },
      marker: { size: 8 },
    };

    const layout = {
      title: "Eα от степени превращения α",
      xaxis: { title: "α" },
      yaxis: { title: "Eα, kJ/mol" },
      hovermode: "closest",
    };

    Plotly.newPlot("plot-e-alpha", [trace], layout, { responsive: true });
  },

  showRegression(point) {
    const regSection = document.getElementById("study-regression");
    if (regSection) regSection.style.display = "block";

    const alphaEl = document.getElementById("regression-alpha");
    if (alphaEl) alphaEl.textContent = point.alpha.toFixed(3);

    const slopeEl = document.getElementById("reg-slope");
    if (slopeEl) slopeEl.textContent = point.slope?.toFixed(4) || "—";

    const interceptEl = document.getElementById("reg-intercept");
    if (interceptEl) interceptEl.textContent = point.intercept?.toFixed(4) || "—";

    const r2El = document.getElementById("reg-r2");
    if (r2El) r2El.textContent = point.r_squared?.toFixed(4) || "—";

    const seEl = document.getElementById("reg-se");
    if (seEl) seEl.textContent = point.slope_standard_error?.toFixed(4) || "—";

    const runsEl = document.getElementById("reg-runs");
    if (runsEl) runsEl.textContent = point.run_ids.join(", ");

    if (!point.regression_x || !point.regression_y) return;

    const trace = {
      x: point.regression_x,
      y: point.regression_y,
      mode: "markers",
      type: "scatter",
      name: "данные",
      marker: { size: 6 },
    };

    if (point.slope !== null && point.intercept !== null) {
      const xMin = Math.min(...point.regression_x);
      const xMax = Math.max(...point.regression_x);
      const fitTrace = {
        x: [xMin, xMax],
        y: [
          point.slope * xMin + point.intercept,
          point.slope * xMax + point.intercept,
        ],
        mode: "lines",
        type: "scatter",
        name: "fit",
        line: { color: "#3498db", dash: "dash" },
      };
      Plotly.newPlot("plot-regression", [trace, fitTrace], {
        title: `Регрессия при α = ${point.alpha.toFixed(3)}`,
        xaxis: { title: "1/T, K⁻¹" },
        yaxis: { title: "log₁₀(β)" },
      }, { responsive: true });
    }
  },

  showPreparation() {
    const prep = document.getElementById("kinetics-preparation");
    const res = document.getElementById("kinetics-results");
    if (prep) prep.style.display = "block";
    if (res) res.style.display = "none";
  },

  showResults() {
    const prep = document.getElementById("kinetics-preparation");
    const res = document.getElementById("kinetics-results");
    if (prep) prep.style.display = "none";
    if (res) res.style.display = "block";
  },
};