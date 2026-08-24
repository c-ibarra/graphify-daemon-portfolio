---
status: accepted
---

# Reject duplicated auth headers as unauthenticated, not resolved to a value

`_ApiKeyMiddleware` treats a duplicated `X-API-Key` or `Authorization` header as absent rather than resolving it to any one of its values — even when one of the duplicates is correct. Considered and rejected: take the first value and log a warning, which tolerates a proxy that duplicates headers by accident. This daemon binds loopback-only and runs as a single local process, not behind a multi-tenant proxy, so that "accidental duplicate" case essentially doesn't occur in this deployment shape, while a duplicated auth header is exactly the shape of a header-smuggling/spoofing attempt. Treating any duplicate as absent closes that ambiguity entirely rather than picking a side of it.
