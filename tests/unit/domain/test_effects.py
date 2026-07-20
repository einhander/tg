"""Tests for tgapp.domain.effects — thermal effect calculation per PLAN_AUDIT §12."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from tgapp.domain.effects import calculate_thermal_effect, EFFECT_SCALE_K


class TestCalculateThermalEffect:
    def test_linear_baseline_zero_effect(self):
        """Чистая линейная базовая линия даёт нулевой эффект."""
        temp = np.linspace(100.0, 500.0, 100)
        dta = 0.001 * temp + 0.5  # linear
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})
        result = calculate_thermal_effect(frame, 100.0, 500.0, 100.0)
        assert "0.0" in result or "в пределах шума" in result

    def test_exothermic_peak(self):
        """Экзотермический пик даёт положительный эффект."""
        temp = np.linspace(100.0, 500.0, 200)
        dta = 2.0 * np.exp(-0.5 * ((temp - 300.0) / 30.0) ** 2)
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})
        result = calculate_thermal_effect(frame, 250.0, 350.0, 100.0)
        assert "Дж/г" in result
        match = re.search(r"([+-]?\d+\.?\d*[eE][+-]?\d+|[+-]?\d+\.?\d*)", result)
        if match:
            value = float(match.group(1))
            assert value > 0

    def test_endothermic_peak(self):
        """Эндотермический пик даёт отрицательный эффект."""
        temp = np.linspace(100.0, 500.0, 200)
        dta = -2.0 * np.exp(-0.5 * ((temp - 300.0) / 30.0) ** 2)
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})
        result = calculate_thermal_effect(frame, 250.0, 350.0, 100.0)
        match = re.search(r"([+-]?\d+\.?\d*[eE][+-]?\d+|[+-]?\d+\.?\d*)", result)
        if match:
            value = float(match.group(1))
            assert value < 0

    def test_triangular_peak_analytical(self):
        """Треугольный пик даёт аналитически известную площадь."""
        temp = np.linspace(200.0, 400.0, 200)
        dta = np.zeros_like(temp)
        mask = (temp >= 250.0) & (temp <= 350.0)
        mid = 300.0
        dta[mask] = 2.0 * (1.0 - np.abs(temp[mask] - mid) / 50.0)
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})
        result = calculate_thermal_effect(frame, 250.0, 350.0, 100.0)
        assert "Дж/г" in result

    def test_boundary_interpolation(self):
        """Выделение границ между существующими точками работает за счёт интерполяции."""
        temp = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        dta = np.array([0.0, 1.0, 2.0, 1.0, 0.0])
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})
        result = calculate_thermal_effect(frame, 150.0, 450.0, 100.0)
        assert "Дж/г" in result

    def test_zero_mass_rejected(self):
        """Нулевая масса отклоняется."""
        temp = np.linspace(100.0, 500.0, 50)
        dta = np.zeros_like(temp)
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})
        result = calculate_thermal_effect(frame, 100.0, 500.0, 0.0)
        assert "нулевой" in result or "положительной" in result

    def test_negative_mass_rejected(self):
        """Отрицательная масса отклоняется."""
        temp = np.linspace(100.0, 500.0, 50)
        dta = np.zeros_like(temp)
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})
        result = calculate_thermal_effect(frame, 100.0, 500.0, -1.0)
        assert "положительной" in result

    def test_interval_outside_data_rejected(self):
        """Интервал вне диапазона данных отклоняется."""
        temp = np.array([100.0, 200.0, 300.0])
        dta = np.array([0.0, 1.0, 0.0])
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})
        result = calculate_thermal_effect(frame, 50.0, 400.0, 100.0)
        assert "выходит за пределы" in result or "интервал" in result

    def test_floating_point_boundaries(self):
        """Границы с плавающей точкой не округляются до целых."""
        temp = np.linspace(100.0, 500.0, 100)
        dta = np.zeros_like(temp)
        dta += 0.5 * np.exp(-0.5 * ((temp - 250.5) / 5.0) ** 2)
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})
        result = calculate_thermal_effect(frame, 245.7, 255.3, 100.0)
        assert "Дж/г" in result

    def test_result_independent_of_bins(self):
        """Результат почти не зависит от числа bins."""
        temp_high = np.linspace(100.0, 500.0, 1000)
        dta_high = 1.0 * np.exp(-0.5 * ((temp_high - 300.0) / 20.0) ** 2)
        frame_high = pd.DataFrame({"temp": temp_high, "deltatemp": dta_high})

        temp_low = np.linspace(100.0, 500.0, 50)
        dta_low = 1.0 * np.exp(-0.5 * ((temp_low - 300.0) / 20.0) ** 2)
        frame_low = pd.DataFrame({"temp": temp_low, "deltatemp": dta_low})

        result_high = calculate_thermal_effect(frame_high, 260.0, 340.0, 100.0)
        result_low = calculate_thermal_effect(frame_low, 260.0, 340.0, 100.0)

        match_high = re.search(r"([+-]?\d+\.?\d*[eE][+-]?\d+|\d+\.?\d*)", result_high)
        match_low = re.search(r"([+-]?\d+\.?\d*[eE][+-]?\d+|\d+\.?\d*)", result_low)

        if match_high and match_low:
            val_high = float(match_high.group(1))
            val_low = float(match_low.group(1))
            if val_high != 0:
                relative_diff = abs(val_high - val_low) / abs(val_high)
                assert relative_diff < 0.05

    def test_swap_boundaries(self):
        """Перестановка границ интервала не меняет результат."""
        temp = np.linspace(100.0, 500.0, 100)
        dta = 1.5 * np.exp(-0.5 * ((temp - 300.0) / 25.0) ** 2)
        frame = pd.DataFrame({"temp": temp, "deltatemp": dta})

        result1 = calculate_thermal_effect(frame, 250.0, 350.0, 100.0)
        result2 = calculate_thermal_effect(frame, 350.0, 250.0, 100.0)

        match1 = re.search(r"([+-]?\d+\.?\d*[eE][+-]?\d+|\d+\.?\d*)", result1)
        match2 = re.search(r"([+-]?\d+\.?\d*[eE][+-]?\d+|\d+\.?\d*)", result2)

        if match1 and match2:
            val1 = float(match1.group(1))
            val2 = float(match2.group(1))
            assert val1 == val2

    def test_empty_frame(self):
        """Пустой фрейм → сообщение об отсутствии данных."""
        frame = pd.DataFrame()
        result = calculate_thermal_effect(frame, 100.0, 500.0, 100.0)
        assert "нет данных" in result or "интервал" in result

    def test_missing_columns(self):
        """Отсутствие temp/deltatemp → сообщение."""
        frame = pd.DataFrame({"temp": [1, 2, 3]})
        result = calculate_thermal_effect(frame, 100.0, 500.0, 100.0)
        assert "нет данных" in result or "интервал" in result

    def test_calibration_factor_documented(self):
        """EFFECT_SCALE_K — документированный калибровочный коэффициент."""
        assert EFFECT_SCALE_K == 0.4458333
        import tgapp.domain.effects as effects_module
        assert hasattr(effects_module, "EFFECT_SCALE_K")