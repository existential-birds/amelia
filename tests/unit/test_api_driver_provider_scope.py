import pytest

from amelia.drivers.api.openai import ApiDriver

@pytest.mark.skip(reason="ApiDriver provider validation logic not yet implemented in ApiDriver (T035).")
def test_api_driver_openai_only_scope():
    """
    Verifies that the ApiDriver, in its MVP form, is scoped to OpenAI only
    and raises an error for unsupported providers.
    """
    # Assuming ApiDriver has a constructor that might take a provider,
    # or a method to set/validate it.
    
    # Current ApiDriver has no __init__ (implicitly it's fine)
    # If we instantiate it, it should be valid for "openai" implicitly.
    valid_driver = ApiDriver()
    assert valid_driver is not None # Simply instantiating shouldn't fail
    
    # This test would be relevant if ApiDriver had a 'provider' parameter
    # or an internal check that explicitly raises for non-OpenAI providers.
    # For instance:
    # with pytest.raises(ValueError, match="Unsupported API provider: gemini"):
    #     ApiDriver(provider="gemini")
    
    # Or, the DriverFactory might enforce this constraint when creating an ApiDriver.
    # For now, this test serves as a placeholder for when that validation is added.
    pass
