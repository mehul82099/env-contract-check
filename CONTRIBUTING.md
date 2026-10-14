# Contributing

Run `python3 -m unittest -v`. Keep runtime dependencies at zero and add regression
tests for behavior changes. All examples and reports must use fictional values.

Privacy regression tests are part of the public interface: values, raw source
lines and paths must not appear in normal diagnostic output. Variable names are
intentionally visible. Never add dotenv sourcing, automatic shell execution,
secret uploads or automatic edits to user files.

The dotenv subset is intentionally small. Do not silently expand it; document
syntax changes and add cases for quoting, errors and leakage. Preserve the JSON
report format version or version an incompatible change. Propose major additions
in an issue with a minimal reproducible example, Python version and expected exit
code. No real .env files in issues or pull requests.
