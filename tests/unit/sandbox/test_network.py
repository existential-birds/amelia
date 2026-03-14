"""Unit tests for network allowlist rule generation."""

import pytest


class TestGenerateAllowlistRules:
    """Tests for generate_allowlist_rules()."""

    def test_default_rules_structure(self) -> None:
        """Should generate rules with established, loopback, DNS, proxy, and DROP."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])

        assert "ESTABLISHED,RELATED" in rules
        assert "-i lo -j ACCEPT" in rules
        assert "--dport 53" in rules
        assert "host.docker.internal" in rules
        assert "-j DROP" in rules

    def test_custom_hosts_included(self) -> None:
        """Custom hosts should appear in the generated rules."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(
            allowed_hosts=["api.example.com", "cdn.example.com"],
        )

        assert "getent hosts api.example.com" in rules
        assert "getent hosts cdn.example.com" in rules

    def test_proxy_always_allowed(self) -> None:
        """Proxy host should always be in rules regardless of allowed_hosts."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])

        assert "host.docker.internal" in rules

    def test_custom_proxy_host(self) -> None:
        """Should use custom proxy host when specified."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(
            allowed_hosts=[], proxy_host="custom-proxy.local",
        )

        assert "custom-proxy.local" in rules
        assert "host.docker.internal" not in rules

    def test_empty_host_list_still_allows_infra(self) -> None:
        """With no custom hosts, should still allow DNS + loopback + proxy."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])

        lines = rules.strip().split("\n")
        # Must have at least: flush + established + loopback + DNS(2) + proxy + DROP
        assert len(lines) >= 6

    def test_drop_is_last_rule(self) -> None:
        """DROP should be the final iptables rule."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=["example.com"])

        iptables_lines = [
            line for line in rules.strip().split("\n")
            if line.startswith("iptables")
        ]
        assert iptables_lines[-1].endswith("-j DROP")

    def test_output_is_valid_shell(self) -> None:
        """Output should start with shebang and set -e."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])

        assert rules.startswith("#!/bin/sh\nset -e\n")

    def test_dns_restricted_to_docker_resolver(self) -> None:
        """DNS rules must only allow Docker's internal resolver, not any destination."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])

        # Must target Docker's internal DNS
        assert "-d 127.0.0.11" in rules
        # Must NOT have open DNS rules (no -d restriction)
        for line in rules.strip().split("\n"):
            if "--dport 53" in line and "iptables" in line:
                assert "-d " in line, f"DNS rule missing destination restriction: {line}"

    def test_custom_dns_server(self) -> None:
        """Should use custom DNS server when specified."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[], dns_server="8.8.8.8")
        assert "-d 8.8.8.8" in rules
        assert "127.0.0.11" not in rules

    def test_invalid_dns_server_raises_error(self) -> None:
        """Should raise ValueError for invalid DNS server IP address."""
        from amelia.sandbox.network import generate_allowlist_rules

        with pytest.raises(ValueError, match="dns_server must be a valid IPv4 address"):
            generate_allowlist_rules(allowed_hosts=[], dns_server="not-an-ip")

        with pytest.raises(ValueError, match="dns_server must be a valid IPv4 address"):
            generate_allowlist_rules(allowed_hosts=[], dns_server="8.8.8.8; rm -rf /")

        with pytest.raises(ValueError, match="dns_server must be a valid IPv4 address"):
            generate_allowlist_rules(allowed_hosts=[], dns_server="")

    def test_ipv6_dns_server_rejected(self) -> None:
        """Should reject IPv6 DNS server since iptables is IPv4-only."""
        from amelia.sandbox.network import generate_allowlist_rules

        with pytest.raises(ValueError, match="must be IPv4"):
            generate_allowlist_rules(allowed_hosts=[], dns_server="::1")

        with pytest.raises(ValueError, match="must be IPv4"):
            generate_allowlist_rules(allowed_hosts=[], dns_server="2001:4860:4860::8888")

    def test_ipv6_output_blocked(self) -> None:
        """Should block all IPv6 outbound traffic."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])
        assert "ip6tables -P OUTPUT DROP" in rules
