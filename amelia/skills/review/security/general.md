# Security Code Review

Focus exclusively on security vulnerabilities and risks. For general code quality concerns, defer to the general review — this review targets exploitable issues only.

## Checklist
- [ ] No SQL injection (parameterized queries only)
- [ ] No command injection (no shell=True with user input, no string interpolation in commands)
- [ ] No XSS (user input escaped in HTML output)
- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] Authentication checks on all protected endpoints
- [ ] Authorization checks (users can only access their own resources)
- [ ] No path traversal (user input not used in file paths without validation)
- [ ] Sensitive data not logged or exposed in error messages
- [ ] CORS configured restrictively (not wildcard for authenticated endpoints)
- [ ] Dependencies don't have known CVEs
- [ ] Cryptographic operations use standard libraries (no custom crypto)
- [ ] Session management follows best practices (secure cookies, token rotation)

## Severity Guide
- **Critical**: Exploitable vulnerability (injection, auth bypass, data exposure)
- **Major**: Weak security control that could be exploited with effort
- **Minor**: Defense-in-depth improvement, hardening suggestion
