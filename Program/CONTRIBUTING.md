# Contributing

Contributions that improve reproducibility, correctness, performance, documentation, or metric validation are welcome.

Before submitting a pull request:

1. Keep the user interface and public documentation in English.
2. Preserve the compatible CSV schema unless the change is explicitly documented as breaking compatibility.
3. Add or update tests for cryptographic metric changes.
4. Run:

```bash
python -m unittest discover -s tests -v
```

5. Describe any numerical differences from the legacy implementation.
