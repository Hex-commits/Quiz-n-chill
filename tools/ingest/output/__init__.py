"""Where a finished question goes.

Two destinations, deliberately independent of each other and of the pipeline
that produced the question:

* `store.py` -- Supabase. Ordered inserts with a rollback, because PostgREST
  offers no transaction across quizzes -> categories -> items.
* `report.py` -- the Markdown a person actually reads to answer the one
  question nothing automatic can: is each extra answer really unplaceable?

A dry run exercises `report.py` and never touches `store.py`, which is why they
are separate modules rather than one "results" step.
"""
