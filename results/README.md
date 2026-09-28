# Results

Every experiment writes a JSON summary here, and every chart and number in the case study is generated from these files.

- The schema is defined in Phase 2.
- Every file carries a `source` tag: `gpu`, `sim`, `projection` or `floci` (see [methodology](../docs/methodology.md)).
- Raw per-request traces go in `results/raw/`, which isn't committed because of size. Summaries are committed.
- Files are never hand-edited. To change a result, re-run the experiment.
