"""Reading and applying the hand-written question files.

`tools/fakes` is authoring-time tooling: it prints a file, splices a column into
it, checks it before anyone runs it. This package is the database-facing half --
it parses the same files and writes what they describe into Supabase over
PostgREST, for the case where `psql` is not the tool at hand.
"""
