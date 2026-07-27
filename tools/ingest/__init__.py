"""Wikipedia -> local model -> Supabase question ingestion.

Run as a module from the repo root: `python -m tools.ingest --help`.

The pipeline is a LangGraph state machine; see `graph.py` for the shape.

Nothing in this package talks to a hosted service. The model runs in the
project's Ollama container, and the tracing below is switched off here -- at
import time, before `langchain_core` is loaded -- because LangSmith would
otherwise pick these variables up from the ambient environment and start
shipping every article and every generated question to LangChain's cloud. That
is the exact property this tool was built to avoid, so it is closed off in code
rather than left to whoever happens to have `LANGSMITH_TRACING=1` exported.
Debugging is served instead by the per-node trace in `graph.py`, which stays on
this machine.
"""

import os

for _var in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
    os.environ[_var] = "false"
