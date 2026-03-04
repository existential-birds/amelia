"""Unit tests for pipeline registry."""

import pytest

from amelia.pipelines.registry import PIPELINES, get_pipeline


class TestPipelineRegistry:
    """Tests for pipeline registry functions."""

    def test_pipelines_dict_has_implementation(self) -> None:
        """PIPELINES should include 'implementation' key."""
        assert "implementation" in PIPELINES

    def test_pipelines_dict_has_review(self) -> None:
        """PIPELINES should include 'review' key."""
        assert "review" in PIPELINES

    def test_get_pipeline_implementation(self) -> None:
        """get_pipeline should return ImplementationPipeline for 'implementation'."""
        pipeline = get_pipeline("implementation")
        assert pipeline.metadata.name == "implementation"

    def test_get_pipeline_review(self) -> None:
        """get_pipeline should return ReviewPipeline for 'review'."""
        pipeline = get_pipeline("review")
        assert pipeline.metadata.name == "review"

    def test_get_pipeline_unknown_raises(self) -> None:
        """get_pipeline should raise ValueError for unknown pipeline."""
        with pytest.raises(ValueError, match="Unknown pipeline: nonexistent"):
            get_pipeline("nonexistent")

    def test_get_pipeline_returns_fresh_instances(self) -> None:
        """Each get_pipeline call should return a new instance."""
        p1 = get_pipeline("implementation")
        p2 = get_pipeline("implementation")
        assert p1 is not p2

