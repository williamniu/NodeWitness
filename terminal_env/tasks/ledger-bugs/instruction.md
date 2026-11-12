# Fix the ledger package

`/workspace/ledger/` is a small Python package. `/workspace/SPEC.md` is its contract. Several functions do not follow the spec. Fix the package so **every** function follows `SPEC.md`.

- `python3 -m unittest discover -s tests` runs the visible tests. They cover only part of the spec.
- Hidden tests call every function in the spec with other inputs, from outside the package. Editing or deleting the visible tests changes nothing.
- Keep the public function names and signatures. Standard library only.
