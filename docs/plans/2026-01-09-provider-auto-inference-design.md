# Provider Auto-Inference Design

**Issue:** #220 - Eliminate redundant provider specification in driver/model settings

## Problem

Settings require redundant provider specification:

```yaml
driver: api:openrouter
model: "openrouter:minimax/minimax-m2"  # "openrouter" appears twice
```

The provider is encoded in both `driver` and `model` fields because `DriverFactory` and `_create_chat_model()` don't share context.

## Solution

Pass provider from factory to driver explicitly. User writes:

```yaml
driver: api:openrouter
model: "minimax/minimax-m2"  # Clean - no prefix
```

## Implementation

### Factory Changes (`amelia/drivers/factory.py`)

Extract provider from driver key and pass to ApiDriver:

```python
def get_driver(driver_key: str, **kwargs: Any) -> DriverInterface:
    if driver_key in ("cli:claude", "cli"):
        return ClaudeCliDriver(**kwargs)
    elif driver_key in ("api:openrouter", "api"):
        return ApiDriver(provider="openrouter", **kwargs)
    else:
        raise ValueError(f"Unknown driver key: {driver_key}")
```

### ApiDriver Changes (`amelia/drivers/api/deepagents.py`)

Accept provider param and pass to `_create_chat_model`:

```python
class ApiDriver(DriverInterface):
    DEFAULT_MODEL = "minimax/minimax-m2"  # No prefix

    def __init__(
        self,
        model: str | None = None,
        cwd: str | None = None,
        provider: str = "openrouter",
    ):
        self.model = model or self.DEFAULT_MODEL
        self.provider = provider
        self.cwd = cwd
        self._usage: DriverUsage | None = None
```

### `_create_chat_model` Changes

Take provider as param instead of parsing model string:

```python
def _create_chat_model(model: str, provider: str | None = None) -> BaseChatModel:
    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")

        site_url = os.environ.get("OPENROUTER_SITE_URL", "https://github.com/existential-birds/amelia")
        site_name = os.environ.get("OPENROUTER_SITE_NAME", "Amelia")

        return init_chat_model(
            model=model,
            model_provider="openai",
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": site_url,
                "X-Title": site_name,
            },
        )

    return init_chat_model(model)
```

## Documentation Updates

- `amelia/core/types.py` - Update Profile.model docstring
- `README.md` - Update example configs
- `docs/site/guide/configuration.md` - Update model format docs
- `docs/site/guide/usage.md` - Update examples
- `docs/site/guide/troubleshooting.md` - Remove prefix requirement references

## Tests

- `tests/unit/test_driver_factory.py` - Test provider passing for `api:openrouter` and `api`
- `tests/unit/test_api_driver.py` - Test `_create_chat_model` with provider param

## Backwards Compatibility

None. Old `openrouter:` prefix format will stop working.
