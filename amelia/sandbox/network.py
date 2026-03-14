"""Network allowlist rule generation for sandbox containers.

Generates iptables rules that restrict outbound connections to approved
hosts only. The generated script is applied inside the container by
setup-network.sh.
"""

import shlex


def generate_allowlist_rules(
    allowed_hosts: list[str],
    proxy_host: str = "host.docker.internal",
    dns_server: str = "127.0.0.11",
) -> str:
    """Generate iptables rules for the network allowlist.

    Returns a shell script that:
    1. Flushes existing OUTPUT rules
    2. Allows established/related connections
    3. Allows loopback
    4. Allows DNS (UDP + TCP port 53) to the specified DNS server only
    5. Allows the proxy host (LLM + git credentials)
    6. Resolves and allows each configured host
    7. DROPs everything else

    Args:
        allowed_hosts: Hostnames to allow outbound connections to.
        proxy_host: Host running the LLM/git proxy.
        dns_server: DNS server to restrict DNS queries to. Defaults to
            Docker's internal resolver (127.0.0.11).

    Returns:
        Shell script string with iptables rules.
    """
    lines = [
        "#!/bin/sh",
        "set -e",
        "",
        "# Flush existing OUTPUT rules",
        "iptables -F OUTPUT",
        "",
        "# Allow established/related connections",
        "iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT",
        "",
        "# Allow loopback",
        "iptables -A OUTPUT -o lo -j ACCEPT",
        "iptables -A INPUT -i lo -j ACCEPT",
        "",
        f"# Allow DNS via Docker resolver ({dns_server})",
        f"iptables -A OUTPUT -d {dns_server} -p udp --dport 53 -j ACCEPT",
        f"iptables -A OUTPUT -d {dns_server} -p tcp --dport 53 -j ACCEPT",
        "",
        f"# Allow proxy host ({proxy_host})",
        f"PROXY_IP=$(getent hosts {shlex.quote(proxy_host)} | awk '{{print $1}}')",
        'if [ -n "$PROXY_IP" ]; then',
        '    iptables -A OUTPUT -d "$PROXY_IP" -j ACCEPT',
        "fi",
    ]

    if allowed_hosts:
        lines.append("")
        lines.append("# Allow configured hosts")
        for host in allowed_hosts:
            lines.append(f"HOST_IP=$(getent hosts {shlex.quote(host)} | awk '{{print $1}}')")
            lines.append('if [ -n "$HOST_IP" ]; then')
            lines.append('    iptables -A OUTPUT -d "$HOST_IP" -j ACCEPT')
            lines.append("fi")

    lines.extend([
        "",
        "# Drop everything else",
        "iptables -A OUTPUT -j DROP",
    ])

    return "\n".join(lines) + "\n"
