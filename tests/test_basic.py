"""
Basic unit tests for distortion_analyzer module.
Tests data classes and utility functions without requiring CODE V connection.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from distortion_analyzer import DistortionGrid, PupilSwimResult, _unwrap_grid


def test_distortion_grid_creation():
    """Test DistortionGrid dataclass creation."""
    actual = np.random.rand(11, 11, 2)
    ideal = np.random.rand(11, 11, 2)
    grid = DistortionGrid(
        actual=actual,
        ideal=ideal,
        num_lines=11,
        wavelength=650.0,
        zoom_pos=1,
        x_fov=26.565,
        y_fov=26.565,
    )
    assert grid.num_lines == 11
    assert grid.wavelength == 650.0
    assert grid.zoom_pos == 1
    assert grid.actual.shape == (11, 11, 2)
    print("test_distortion_grid_creation passed")


def test_distortion_grid_displacement():
    """Test displacement calculation."""
    actual = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float)
    ideal = np.array([[0.0, 0.0], [0.0, 0.0]], dtype=float)
    grid = DistortionGrid(
        actual=actual,
        ideal=ideal,
        num_lines=2,
        wavelength=550.0,
        zoom_pos=1,
        x_fov=5.0,
        y_fov=5.0,
    )
    disp = grid.displacement
    assert disp.shape == (2, 2, 2)
    assert np.allclose(disp[0, 0], [1.0, 2.0])
    print("test_distortion_grid_displacement passed")


def test_distortion_grid_displacement_magnitude():
    """Test displacement_magnitude calculation."""
    actual = np.array([[3.0, 4.0]], dtype=float)
    ideal = np.array([[0.0, 0.0]], dtype=float)
    grid = DistortionGrid(
        actual=actual,
        ideal=ideal,
        num_lines=1,
        wavelength=550.0,
        zoom_pos=1,
        x_fov=5.0,
        y_fov=5.0,
    )
    mag = grid.displacement_magnitude
    assert mag.shape == (1, 1)
    assert np.isclose(mag[0, 0], 5.0)
    print("test_distortion_grid_displacement_magnitude passed")


def test_pupil_swim_result():
    """Test PupilSwimResult dataclass."""
    displacement = np.random.rand(11, 11, 2)
    magnitude = np.linalg.norm(displacement, axis=2)
    swim = PupilSwimResult(
        displacement=displacement,
        magnitude=magnitude,
        ref_zoom=1,
        tgt_zoom=2,
        max_swim=float(np.max(magnitude)),
        mean_swim=float(np.mean(magnitude)),
        rms_swim=float(np.sqrt(np.mean(magnitude**2))),
    )
    assert swim.ref_zoom == 1
    assert swim.tgt_zoom == 2
    assert swim.displacement.shape == (11, 11, 2)
    print("test_pupil_swim_result passed")


def test_unwrap_grid_with_dataclass():
    """Test _unwrap_grid with DistortionGrid instance."""
    actual = np.random.rand(5, 5, 2)
    ideal = np.random.rand(5, 5, 2)
    grid = DistortionGrid(
        actual=actual,
        ideal=ideal,
        num_lines=5,
        wavelength=550.0,
        zoom_pos=1,
        x_fov=5.0,
        y_fov=5.0,
    )
    result = _unwrap_grid(grid)
    assert result is actual
    print("test_unwrap_grid_with_dataclass passed")


def test_unwrap_grid_with_array():
    """Test _unwrap_grid with raw ndarray."""
    arr = np.random.rand(5, 5, 2)
    result = _unwrap_grid(arr)
    assert result is arr
    print("test_unwrap_grid_with_array passed")


if __name__ == "__main__":
    print("Running basic unit tests for distortion_analyzer...")
    print()
    
    test_distortion_grid_creation()
    test_distortion_grid_displacement()
    test_distortion_grid_displacement_magnitude()
    test_pupil_swim_result()
    test_unwrap_grid_with_dataclass()
    test_unwrap_grid_with_array()
    
    print()
    print("All tests passed!")
