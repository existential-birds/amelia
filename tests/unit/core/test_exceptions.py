from amelia.core.exceptions import AmeliaError, ModelProviderError, SchemaValidationError


class TestSchemaValidationError:
    """Tests for SchemaValidationError exception type."""

    def test_is_amelia_error(self) -> None:
        err = SchemaValidationError("bad schema", provider_name="codex")
        assert isinstance(err, AmeliaError)

    def test_is_not_model_provider_error(self) -> None:
        err = SchemaValidationError("bad schema", provider_name="codex")
        assert not isinstance(err, ModelProviderError)

    def test_attributes(self) -> None:
        err = SchemaValidationError(
            "Schema validation failed",
            provider_name="codex",
            original_message="raw output",
        )
        assert err.provider_name == "codex"
        assert err.original_message == "raw output"
        assert str(err) == "Schema validation failed"

    def test_not_in_transient_exceptions(self) -> None:
        from amelia.server.orchestrator.service import TRANSIENT_EXCEPTIONS

        assert SchemaValidationError not in TRANSIENT_EXCEPTIONS
