"""Tests for tgapp.domain.summary — build_heat_speed_text with linear regression."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tgapp.domain.summary import build_heat_speed_text


class TestBuildHeatSpeedText:
    def test_linear_heating_10k_min(self):
        """T(t) = 25 + 10t → β = 10 K/мин"""
        time = np.linspace(0, 100, 100)
        temp = 25.0 + 10.0 * time
        frame = pd.DataFrame({"time": time, "temp": temp})
        result = build_heat_speed_text(frame)
        assert "10.0 K/мин" in result

    def test_linear_heating_different_initial_temp(self):
        """T(t) = 100 + 5t → β = 5 K/мин"""
        time = np.linspace(0, 50, 50)
        temp = 100.0 + 5.0 * time
        frame = pd.DataFrame({"time": time, "temp": temp})
        result = build_heat_speed_text(frame)
        assert "5.0 K/мин" in result

    def test_time_offset(self):
        """t starts at 10, T(t) = 25 + 8t → β = 8 K/мин"""
        time = np.linspace(10, 110, 100)
        temp = 25.0 + 8.0 * (time - 10)
        frame = pd.DataFrame({"time": time, "temp": temp})
        result = build_heat_speed_text(frame)
        assert "8.0 K/мин" in result

    def test_empty_frame(self):
        frame = pd.DataFrame()
        result = build_heat_speed_text(frame)
        assert "недоступна" in result

    def test_non_monotonic_time(self):
        time = np.array([0, 10, 5, 20])
        temp = np.array([25, 125, 75, 225])
        frame = pd.DataFrame({"time": time, "temp": temp})
        result = build_heat_speed_text(frame)
        assert "недоступна" in result

    def test_nonlinear_heating(self):
        """T(t) = 25 + 50*sin(π*t/50) → сильно нелинейный нагрев (R² < 0.9)"""
        time = np.linspace(0, 100, 200)
        temp = 25.0 + 50.0 * np.sin(np.pi * time / 50.0)
        frame = pd.DataFrame({"time": time, "temp": temp})
        result = build_heat_speed_text(frame)
        # Должен быть warning о нелинейности
        assert "нелинеен" in result or "нелинейн" in result