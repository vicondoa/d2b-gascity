# Setup

## Preconditions

This capability speaks GitHub through `gh`, Git, and the bundled Python
helper.  If `gh repo view` cannot resolve the repository, stop and report that
the target cannot be watched here.

Resolve a pull request from its number, URL, or the current branch.  If no
open pull request exists, stop without creating state for another target.

Before a permitted write, the checkout must be the pull request's head branch,
must track the matching upstream, and must be clean.  A matching SHA on a
different branch or a detached checkout is not sufficient.  Switch a clean
checkout to the correct branch; report a dirty or unpushable checkout as a
blocker.

Use a caller-supplied state directory.  It must be private to this pull
request and writable by the current user.  The helper creates only its lock
and JSON journal there.
