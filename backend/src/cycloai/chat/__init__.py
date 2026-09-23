"""CycloAI chat package (phase P7b).

Currently holds the pure-function system-prompt builder
(:mod:`cycloai.chat.prompt`, ported from ``lib/ai/system-prompt.ts``). The
chat endpoint, streaming and persistence live elsewhere / arrive later.
"""

from cycloai.chat.prompt import ChatAthlete, build_system_prompt

__all__ = ["ChatAthlete", "build_system_prompt"]
