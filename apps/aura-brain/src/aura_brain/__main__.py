"""`python -m aura_brain` — the launch path that does not need a console-script shim.

U344: on a managed Windows machine the Defender ASR rule "block executable files
unless they meet a prevalence, age or trusted list criterion" refuses the freshly
generated `.venv\\Scripts\\aura-brain.exe`, so the brain died with os error 5 before
its first line. The interpreter itself is signed and prevalent, and it is allowed.
"""

from aura_brain.main import run

run()
