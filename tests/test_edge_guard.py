import pytest

from edge_guard import AnomalyDetector, FEATURES


def test_detector_calibrates_then_flags_extreme_sample():
    detector = AnomalyDetector(baseline_size=12)
    baseline = {
        "cpu_percent": 15.0,
        "memory_percent": 40.0,
        "process_count": 100.0,
        "network_sent_bytes_per_sec": 200.0,
        "network_recv_bytes_per_sec": 300.0,
    }

    for offset in range(12):
        sample = dict(baseline)
        sample["cpu_percent"] += offset * 0.1
        assert detector.observe(sample) is None

    assert detector.ready
    assert detector.baseline_samples == 12

    anomaly = {
        "cpu_percent": 100.0,
        "memory_percent": 99.0,
        "process_count": 2000.0,
        "network_sent_bytes_per_sec": 10_000_000.0,
        "network_recv_bytes_per_sec": 10_000_000.0,
    }
    result = detector.observe(anomaly)

    assert result is not None
    assert result["is_anomaly"] is True
    assert set(FEATURES) == set(baseline)


def test_detector_rejects_too_small_baseline():
    with pytest.raises(ValueError, match="at least 5"):
        AnomalyDetector(baseline_size=4)
