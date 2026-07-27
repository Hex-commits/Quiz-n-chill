"""Turning an article into a question: the LangChain half.

Depends on `domain` (the shapes it produces and the rules it is judged by) and
on `sources` for the `Article` type. Nothing here knows about Supabase or about
the Markdown report -- a step hands back a domain object and stops.

* `llm.py` -- the local model as a LangChain chat model.
* `prompts.py` -- every word sent to it, as prompt templates.
* `chains.py` -- one LCEL chain per step: `prepare | prompt | model | parse`.
* `graph.py` -- the LangGraph state machine deciding which step runs when.

The split between the last two is the one worth preserving: `chains.py` knows
how to run a step and nothing about what comes next, `graph.py` knows what comes
next and never touches a prompt or a schema.
"""
