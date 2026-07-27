"""What a Zuordnungsfrage *is*, and what makes one valid.

The bottom layer: pure data and pure rules, with no network, no database and no
model. Nothing in here imports from `pipeline`, `sources` or `output` -- the
dependency only ever points inwards, which is what keeps the rules cheap to test
and impossible to break by changing a prompt.

* `rules.py` -- the bounds, defined once so the JSON Schema and the validator
  cannot drift apart.
* `models.py` -- the Pydantic shapes, plus the JSON Schemas the model is
  constrained to emit.
* `validate.py` -- the structural gate. Its complaints are written to be fed
  back to the model, so they name the offending value and say what to do.
"""
