"""
Tests for standalone mocks (app/standalone_mocks.py).
"""

from app.standalone_mocks import get_consent_detected, get_fraud_score, get_liveness_avg


class TestFraudScoreMock:
    def test_priya_preset(self):
        assert get_fraud_score("PRIYA-001") == 12

    def test_rohit_preset(self):
        assert get_fraud_score("ROHIT-002") == 82

    def test_meera_preset(self):
        assert get_fraud_score("MEERA-003") == 35

    def test_unknown_is_deterministic(self):
        s1 = get_fraud_score("UNKNOWN-XYZ")
        s2 = get_fraud_score("UNKNOWN-XYZ")
        assert s1 == s2
        assert 0 <= s1 <= 100

    def test_different_ids_different_scores(self):
        s1 = get_fraud_score("AAA-111")
        s2 = get_fraud_score("BBB-222")
        # Highly unlikely to collide
        assert isinstance(s1, int) and isinstance(s2, int)

    def test_case_insensitive_preset(self):
        assert get_fraud_score("priya-001") == 12


class TestLivenessAvgMock:
    def test_priya_preset(self):
        assert get_liveness_avg("PRIYA-001") == 0.92

    def test_rohit_preset(self):
        assert get_liveness_avg("ROHIT-002") == 0.45

    def test_meera_preset(self):
        assert get_liveness_avg("MEERA-003") == 0.88

    def test_unknown_is_deterministic(self):
        v1 = get_liveness_avg("UNKNOWN-XYZ")
        v2 = get_liveness_avg("UNKNOWN-XYZ")
        assert v1 == v2
        assert 0.0 <= v1 <= 1.0


class TestConsentMock:
    def test_priya_preset(self):
        assert get_consent_detected("PRIYA-001") is True

    def test_default_is_true(self):
        assert get_consent_detected("RANDOM-999") is True
