# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

Kalpa is a local-first tool with no network or cloud components. However, if you
discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue for the vulnerability
2. Email: swadhinbiswas.cse@gmail.com
3. Include a description of the vulnerability and steps to reproduce

You should receive a response within 48 hours. If the issue is confirmed, a fix
will be released as soon as possible.

## Security Considerations

- Kalpa stores data only in the local `.kalpa/` directory
- No telemetry, no network calls, no accounts
- Database files use default system permissions
- Path traversal is prevented in all file operations
- Symlinks in forks are preserved as symlinks, not followed
