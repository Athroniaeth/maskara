# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Yes    |

## Reporting a Vulnerability

**Please do not report security vulnerabilities in public GitHub issues.**

If you discover a security vulnerability in PIIGhost, please report it **privately** via [GitHub's private vulnerability reporting](https://github.com/Athroniaeth/piighost/security/advisories/new).

Please include:
1. Description of the vulnerability
2. Steps to reproduce (if possible)
3. Potential impact assessment
4. Suggested fix (if you have one)

We aim to acknowledge reports within **48 hours** and provide an initial assessment within **1 week**.

## Security Considerations

PIIGhost handles potentially sensitive PII data. Key design decisions:

- **Anonymization is local** — PII is detected and replaced before being sent to any LLM or external service
- **SHA-256 keyed placeholder store** — placeholders are deterministically derived, not stored in plaintext
- **No logging of raw PII** — the library itself does not log entity values
- **Frozen dataclasses** — immutable data models prevent accidental mutation of sensitive data

> **Note**: PIIGhost anonymizes PII before LLM calls but does not encrypt data at rest. Ensure your `PlaceholderStore` backend is appropriately secured in production.
