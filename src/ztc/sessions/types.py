from __future__ import annotations

# (action, payload, layout)
# action ∈ {"attach", "new", "bash"}; None = el usuario salió sin elegir.
LaunchTarget = tuple[str, str | None, str | None] | None
