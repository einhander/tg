"""Behavioral tests for build_effect_text (domain/summary)."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from tgapp.domain.summary import build_effect_text


class TestBuildEffectTextBehavioral:
    """Behavioral tests — known shapes, expected output patterns."""

    def test_triangle_peak_returns_nonzero(self):
        """Треугольный пик DTA → ненулевой тепловой эффект."""
        temps = np.linspace(0, 200, 201)
        dta = np.zeros(201)
        for i, t in enumerate(temps):
            if 80 <= t <= 100:
                dta[i] = 10 * (t - 80) / 20
            elif 100 < t <= 120:
                dta[i] = 10 * (120 - t) / 20

        frame = pd.DataFrame({"temp": temps, "deltatemp": dta})
        result = build_effect_text(frame, 80.0, 120.0, 100.0)
        assert "Тепловой эффект:" in result
        match = re.search(r"(-?[\d.]+)", result)
        assert match is not None
        effect_value = float(match.group(1))
        assert abs(effect_value) > 0

    def test_zero_mass_returns_error(self):
        """init_mass == 0 → сообщение об ошибке."""
        frame = pd.DataFrame({"temp": [10.0, 25.0, 35.0, 50.0], "deltatemp": [0.1, 0.2, 0.3, 0.4]})
        result = build_effect_text(frame, 20.0, 40.0, 0.0)
        assert "начальная масса должна быть ненулевой" in result

    def test_linear_baseline_returns_value(self):
        """Линейная базовая линия DTA → функция возвращает строку с числом."""
        temps = np.linspace(0, 200, 201)
        dta = np.linspace(0, 10, 201)
        frame = pd.DataFrame({"temp": temps, "deltatemp": dta})
        result = build_effect_text(frame, 0.0, 200.0, 100.0)
        assert "Тепловой эффект:" in result
        match = re.search(r"(-?[\d.]+)", result)
        assert match is not None
        # Линейный наклон имеет ненулевую trapz — эффект будет ≠ 0

    def test_same_xmin_xmax_returns_prompt(self):
        """xmin == xmax → prompt to select interval."""
        frame = pd.DataFrame({"temp": [1.0, 2.0], "deltatemp": [0.1, 0.2]})
        result = build_effect_text(frame, 50.0, 50.0, 100.0)
        assert "выделите температурный интервал" in result

    def test_selection_too_few_points(self):
        """Менее 2 точек в интервале → 'слишком мало точек'."""
        frame = pd.DataFrame({
            "temp": [10.0, 50.0, 150.0, 200.0],
            "deltatemp": [0.0, 0.1, 0.2, 0.0],
        })
        result = build_effect_text(frame, 60.0, 90.0, 100.0)
        assert "слишком мало точек" in result

    def test_effect_text_units(self):
        """Результат всегда содержит единицы Дж/г."""
        frame = pd.DataFrame({"temp": [10.0, 25.0, 35.0, 50.0], "deltatemp": [0.1, 0.2, 0.3, 0.4]})
        result = build_effect_text(frame, 20.0, 40.0, 1.0)
        assert "Дж/г" in result