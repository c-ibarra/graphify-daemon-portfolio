---
status: accepted
---

# MCP tool errors return a fixed generic message, never a sanitized version of the real exception

An unexpected tool failure logs the real exception (with traceback) for operators, then returns a client-facing message naming only the tool and the fact that it failed — e.g. `"Tool graph_stats failed. See daemon logs for detail."` — never any text derived from the exception itself.

## Considered Options

- **Scrub the exception text before returning it** (e.g. regex-strip the vault's absolute path, redact anything matching a filesystem-path shape): rejected. Scrubbing is a blocklist against an open-ended set of things that could leak through an exception message — a file path, node content, an internal function name in a stack frame — and a blocklist only has to miss one case to leak it. This daemon already rejected an equivalent blocklist shape once before, for duplicated auth headers (`docs/adr/0002-reject-duplicate-auth-headers.md`): reject/generalize the ambiguous case rather than trying to enumerate every bad one.
- **A fixed set of generic messages per failure class** (chosen): an allowlist by construction. Nothing internal can appear in the response because nothing internal is ever substituted into it — the message is a constant string, not a transformation of untrusted content.

## Consequences

A well-behaved MCP client trying to distinguish one failure cause from another gets less signal than raw exception text would give it. Accepted: the real detail is still available server-side, in the daemon's own owner-only log file — the MCP contract's job isn't to be a remote-debugging channel into a process that may be handling confidential vault content.
