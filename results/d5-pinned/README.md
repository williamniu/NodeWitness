# D5-pinned — sensitivity rerun of `qwen36`

The D5 review found that the harness sent only temperature and context limits, so each model's Modelfile defaults set the rest (`qwen36`: `repeat_penalty` 1.08, `top_p` 0.9, `top_k` 40; `qwen38`: 1.0, 0.95, 20). Commit `8916b46` sends every sampling option explicitly, set to `qwen38`'s effective D5 values. This folder holds the 20 `qwen36` trials rerun under it: same 4 tasks, same seeds 1001–1005, all on `8916b46` with a clean `terminal_env/`.

```bash
python3 scripts/passk_report.py d5-pinned --trials results/d5-pinned/trials
```

`tests/reporting/test_passk.py` checks in CI that this regenerates `results/passk/d5-pinned.{json,md}` byte-for-byte.
