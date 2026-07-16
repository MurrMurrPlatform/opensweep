"""Git-over-HTTPS auth header for GitHub tokens.

GitHub's *git* endpoints (info/refs, upload-pack, receive-pack) reject
`Authorization: bearer <token>` for App installation tokens (401 → git falls
back to a username prompt and dies headless). The documented, reliable scheme
for BOTH installation tokens and PATs is HTTP basic with the `x-access-token`
username — the same technique actions/checkout uses. The REST API accepts
bearer, which is why API calls can work while clones fail; never share header
construction between the two.
"""

import base64


def git_auth_extraheader(token: str) -> str:
    """`http.extraHeader=` value for a transient `git -c` flag (never persisted)."""
    b64 = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return f"http.extraHeader=AUTHORIZATION: basic {b64}"
