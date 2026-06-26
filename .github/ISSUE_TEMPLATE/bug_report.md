---
name: Bug report
about: Report a reproducible problem with dga-sentinel
title: "[Bug] "
labels: bug
assignees: ''
---

## Description

A clear and concise description of the bug.

## Steps to Reproduce

1. Run `...`
2. Send request `...`
3. Observe `...`

## Expected Behavior

What you expected to happen.

## Actual Behavior

What actually happened. Include error messages, stack traces, or screenshots.

## Environment

| Field | Value |
|-------|-------|
| OS | e.g. macOS 14.5 / Ubuntu 22.04 |
| Docker version | `docker --version` |
| Docker Compose version | `docker compose version` |
| Python version | `python3 --version` |
| Deployment mode | Docker Compose / local dev |
| Branch / commit | e.g. `main` @ `abc1234` |

## Platform Status

Output of `scripts/platform.sh status` (redact any sensitive values):

```
paste output here
```

## Relevant Logs

```
scripts/platform.sh logs <service-name>
```

## Additional Context

Any other context, configuration changes, or workarounds you have tried.
