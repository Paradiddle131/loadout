"""Every test suite here runs git in scratch repositories it builds; a repository-local variable inherited from the
shell that started pytest (GIT_DIR or GIT_INDEX_FILE, set while a git hook runs) would point those commands at another
repository. Git's own list of such variables (`git rev-parse --local-env-vars`, what git clears before it works in
another repository) is dropped before any test module is imported; author and committer identity are kept."""

from __future__ import annotations

import os
import subprocess

LOCAL = subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True, check=True,
                       env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")}).stdout.split()
for name in LOCAL:
    os.environ.pop(name, None)
