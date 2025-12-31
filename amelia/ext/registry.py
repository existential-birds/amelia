"""Extension registry for managing optional integrations.

The registry provides a central point for registering and retrieving
extension implementations. Core uses no-op defaults when no extensions
are registered.

Usage:
    # Get the global registry
    from amelia.ext import get_registry
    registry = get_registry()

    # Register extensions (typically done by Enterprise package)
    registry.register_audit_exporter(my_exporter)

    # Use extensions (done by Core)
    for exporter in registry.audit_exporters:
        await exporter.export(event)
"""

from __future__ import annotations

import threading

from amelia.ext.noop import (
    NoopAnalyticsSink,
    NoopAuditExporter,
    NoopAuthProvider,
    NoopPolicyHook,
)

# Cached noop instances to avoid recreation on every property access.
# We use the noop types in annotations but import protocols for type checking.
from amelia.ext.protocols import (
    AnalyticsSink,
    AuditExporter,
    AuthProvider,
    PolicyHook,
)


_NOOP_POLICY_HOOKS: list[PolicyHook] = [NoopPolicyHook()]
_NOOP_AUDIT_EXPORTERS: list[AuditExporter] = [NoopAuditExporter()]
_NOOP_ANALYTICS_SINKS: list[AnalyticsSink] = [NoopAnalyticsSink()]
_NOOP_AUTH_PROVIDER: AuthProvider = NoopAuthProvider()

# Lock for thread-safe registry initialization.
_registry_lock = threading.Lock()


class ExtensionRegistry:
    """Central registry for extension implementations.

    Maintains lists of registered extensions and provides accessors
    that fall back to no-op implementations when nothing is registered.

    Thread-safety: Registration should happen during startup before
    any concurrent access. Runtime access is read-only.
    """

    def __init__(self) -> None:
        """Initialize the registry with empty extension lists."""
        self._policy_hooks: list[PolicyHook] = []
        self._audit_exporters: list[AuditExporter] = []
        self._analytics_sinks: list[AnalyticsSink] = []
        self._auth_provider: AuthProvider | None = None

    # Registration methods

    def register_policy_hook(self, hook: PolicyHook) -> None:
        """Register a policy hook.

        Multiple hooks can be registered; they run in registration order.
        All hooks must return True for an action to be allowed.

        Args:
            hook: Policy hook implementation.
        """
        self._policy_hooks.append(hook)

    def register_audit_exporter(self, exporter: AuditExporter) -> None:
        """Register an audit exporter.

        Multiple exporters can be registered; events are sent to all.

        Args:
            exporter: Audit exporter implementation.
        """
        self._audit_exporters.append(exporter)

    def register_analytics_sink(self, sink: AnalyticsSink) -> None:
        """Register an analytics sink.

        Multiple sinks can be registered; metrics are sent to all.

        Args:
            sink: Analytics sink implementation.
        """
        self._analytics_sinks.append(sink)

    def register_auth_provider(self, provider: AuthProvider) -> None:
        """Register an auth provider.

        Only one auth provider can be registered. Later registrations
        replace earlier ones.

        Args:
            provider: Auth provider implementation.
        """
        self._auth_provider = provider

    # Accessor properties

    @property
    def policy_hooks(self) -> list[PolicyHook]:
        """Get registered policy hooks.

        Returns:
            List of registered hooks, or [NoopPolicyHook()] if none.
        """
        if not self._policy_hooks:
            return _NOOP_POLICY_HOOKS
        return self._policy_hooks

    @property
    def audit_exporters(self) -> list[AuditExporter]:
        """Get registered audit exporters.

        Returns:
            List of registered exporters, or [NoopAuditExporter()] if none.
        """
        if not self._audit_exporters:
            return _NOOP_AUDIT_EXPORTERS
        return self._audit_exporters

    @property
    def analytics_sinks(self) -> list[AnalyticsSink]:
        """Get registered analytics sinks.

        Returns:
            List of registered sinks, or [NoopAnalyticsSink()] if none.
        """
        if not self._analytics_sinks:
            return _NOOP_ANALYTICS_SINKS
        return self._analytics_sinks

    @property
    def auth_provider(self) -> AuthProvider:
        """Get the registered auth provider.

        Returns:
            Registered provider, or NoopAuthProvider() if none.
        """
        if self._auth_provider is None:
            return _NOOP_AUTH_PROVIDER
        return self._auth_provider

    def clear(self) -> None:
        """Clear all registered extensions.

        Useful for testing.
        """
        self._policy_hooks.clear()
        self._audit_exporters.clear()
        self._analytics_sinks.clear()
        self._auth_provider = None


# Global registry instance
_registry: ExtensionRegistry | None = None


def get_registry() -> ExtensionRegistry:
    """Get the global extension registry.

    Creates the registry on first access (lazy initialization).
    Thread-safe via double-checked locking pattern.

    Returns:
        The global ExtensionRegistry instance.
    """
    global _registry
    if _registry is None:
        with _registry_lock:
            # Double-check after acquiring lock.
            if _registry is None:
                _registry = ExtensionRegistry()
    return _registry
