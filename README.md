# env-contract-check

**Catch missing deployment config without printing secret values.**

A local, dependency-free Python checker for an explicit environment-variable contract. Before starting your app, check required variables, empty values, integer bounds, booleans, HTTP URLs and allowed choices. Reports contain variable **names and fixed error codes**, never their values.

No sourcing `.env`, shell execution, network calls, auto-fixes or secret uploads. File mode reads only the file you name. Process mode reads only the names in your contract.

## Quick start

Python **3.10+**, Git. No `pip install` required.

```sh
git clone https://github.com/mehul82099/env-contract-check.git
cd env-contract-check
python3 env_contract.py contract.example.json --env-file good.example.env
```

```text
PASS
0 error(s), 0 warning(s)
```

Try the deliberately broken, fictional fixture:

```sh
python3 env_contract.py contract.example.json --env-file bad.example.env
```

```text
FAIL
ERROR: API_TOKEN: missing
ERROR: APP_ENV: not_in_choices
ERROR: DEBUG: invalid_boolean
ERROR: PORT: above_maximum
ERROR: PUBLIC_URL: invalid_http_url
WARNING: LEGACY_FLAG: unexpected
5 error(s), 1 warning(s)
```

That command intentionally exits **1**. Machine-readable version:

```sh
python3 env_contract.py contract.example.json --env-file bad.example.env --format json
```

See [expected-bad.json](expected-bad.json) for the exact output. All committed fixtures are fictional. Do not replace their dummy values with real credentials.

## Write a contract

Create a trusted JSON file with public-safe variable names and rules, not secrets:

```json
{
  "version": 1,
  "variables": {
    "PORT": {"type": "integer", "min": 1, "max": 65535},
    "DEBUG": {"type": "boolean"},
    "API_TOKEN": {},
    "APP_ENV": {"choices": ["development", "production"]},
    "LABEL": {"required": false, "allow_empty": true}
  }
}
```

| Rule | Default | Meaning |
| --- | --- | --- |
| `type` | `string` | `string`, `integer`, `boolean` or `http_url` |
| `required` | `true` | Missing variable is an error |
| `allow_empty` | `false` | Empty/whitespace-only values allowed; if allowed, type/choice checks are skipped |
| `min`, `max` | absent | Inclusive integer bounds; integer type only |
| `choices` | absent | Exact, case-sensitive list of allowed strings |

Optional means missing is allowed, not that a present empty value is valid. Set `allow_empty` too when that is intentional. Unknown rule fields and duplicate JSON keys are errors so misspelled rules don't silently pass.

Integers allow an optional sign and ASCII digits only, with at most 100 digits. Leading zeros are accepted. Booleans accept exactly `true` or `false`. URL checks require HTTP/HTTPS, a hostname, no whitespace/backslashes/credentials and a valid explicit port. They are basic syntax checks, not network, DNS, reachability or trust checks. `string` means a nonempty string unless emptiness is allowed; it cannot tell if an API token is real or a placeholder.

## Check a file or a running process

```sh
python3 env_contract.py my-contract.json --env-file .env.local
python3 env_contract.py my-contract.json --env-file .env.local --strict-extra
python3 env_contract.py my-contract.json --process --format json
```

File mode never loads or merges your current process environment. Undeclared file variables are warnings; `--strict-extra` makes them errors. Process mode checks declared names only, ignores unrelated shell/system variables and cannot be combined with `--strict-extra`.

Exit codes: **0** checks pass (warnings possible), **1** validation fails, **2** invalid contract/file/options. Argparse usage errors also exit 2. Input errors use fixed codes and sometimes line numbers. Normal diagnostics do not echo values, raw input lines, file paths, rule choice values or Python exception messages. Variable names themselves remain visible and can disclose system design.

## Deliberately small dotenv subset

Supported: UTF-8 with optional BOM, one assignment per line, ASCII variable names, surrounding whitespace, `export`, blank lines, comments, single/double quotes on a single line, and `=` inside values.

```dotenv
export PORT=3000
DEBUG=false # comment
LABEL="literal # inside quotes"
```

- Variable names follow `[A-Za-z_][A-Za-z0-9_]*` and are case-sensitive.
- `#` outside quotes starts a comment even without a preceding space.
- Quoted whitespace is preserved. Whitespace-only values count as empty.
- Duplicate assignments stop the check instead of first/last-value guessing.
- Multiline quoted values, escaped content inside quotes and quotes inside unquoted values are rejected. No escape decoding.
- `${NAME}` and `$(command)` remain literal text. They are never expanded or run. Avoid these forms if you expect another runtime to expand them.

Dotenv has no single cross-platform formal specification. This subset is **not** a drop-in replacement for Node dotenv, bash, Docker or every framework loader. Validate the representation your app actually consumes. Process mode is useful when another trusted loader has already populated it.

## CI and app startup

A POSIX-shell startup gate after your normal environment setup:

```sh
python3 env_contract.py my-contract.json --process && python3 app.py
```

Your app still needs its own runtime validation. Do not put literal secrets in shell commands or committed workflows; supply them through your existing secret manager/CI environment. This checker is not a secret manager.

The included [workflow](.github/workflows/test.yml) runs offline tests and both fictional demos on Python 3.10, 3.11, 3.12 and 3.13, on GitHub's standard public-repo Ubuntu runner. Action versions are pinned to commit IDs, permissions are read-only, and no deployment or secrets are requested.

```sh
python3 -m unittest -v
```

81 regression tests cover syntax, types, contracts, duplicate keys, size limits, CLI behavior, process isolation and sentinel-value non-disclosure. Local tests passed on Python 3.10.12. Check the Actions page for actual matrix results rather than assuming every platform is tested.

## Problem evidence and alternatives

This category already has good tools. This is an independent implementation, not copied upstream code and not a claim of universal superiority.

- [dotenv issue #405](https://github.com/motdotla/dotenv/issues/405): a user reports new variables breaking teammates and staging because config falls out of sync. The issue is historical and closed after an existing solution was suggested, not a claim that dotenv is currently defective.
- [dotenv issue #549](https://github.com/motdotla/dotenv/issues/549): illustrates confusion moving environment configuration from local development to CI. This checker does not load GitHub secrets or solve secret injection.
- [clean-dotenv](https://github.com/hija/clean-dotenv): documents forgetting to update example variables and generates example files. Prefer it when generation is the task; this tool never rewrites config.
- [dotenv-safe](https://github.com/rolodato/dotenv-safe/blob/master/README.markdown): an established Node option for required variables after loading `.env`. Prefer it for integrated Node runtime loading; this tool is a language-independent preflight CLI with explicit typed rules.
- [Node's dotenv documentation](https://nodejs.org/api/environment_variables.html): names, comments and quotes reference, plus the lack of one formal dotenv specification. This tool intentionally supports less syntax.
- [Twelve-Factor config guidance](https://12factor.net/config): separation of config from code and deploy-specific environment values.

These sources establish expressed problems, not adoption counts, prevalence estimates or guaranteed outage prevention.

## Safety and limits

Read [SECURITY.md](SECURITY.md). No telemetry or network code; no persistent output files. Inputs and values are held in memory. Limits: 1 MiB per env file, 256 KiB per contract, 512 variables. Contracts must be trusted and must not include secret choice values. This is not an audit, sandbox, secret scanner or guarantee against every leak. It cannot verify remote services, tokens, application-specific constraints or environment-loader behavior.

[Contributing guide](CONTRIBUTING.md) | [MIT license](LICENSE)
