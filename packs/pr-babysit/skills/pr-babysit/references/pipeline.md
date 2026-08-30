# Bounded checkpoint mode

The caller drives checkpoint turns.  Each turn performs one
snapshot -> decision -> state-write operation and returns a JSON result.
There is no implicit wait for a human response or a running check.

Return `needs-human` when a source is ambiguous, authority is missing, or a
repair would require a choice outside the target envelope.  Return success
only when the current head is certain and clean, checks are terminal and
successful, feedback is empty, and branch currency is clear.

An in-progress check is waiting evidence, not a failure to repair.  A
terminal failing check remains a residual until a bounded repair changes the
head or the caller records a human decision.
