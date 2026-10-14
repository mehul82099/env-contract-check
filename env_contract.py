#!/usr/bin/env python3
"""Offline environment contract checks. Diagnostics contain names/codes, never values."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

__version__ = "0.1.0"
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
INTEGER = re.compile(r"[+-]?[0-9]+\Z", re.ASCII)
TYPES = {"string", "integer", "boolean", "http_url"}
MAX_ENV_BYTES = 1048576
MAX_SCHEMA_BYTES = 262144


class ConfigError(ValueError):
    """Safe fixed diagnostic code plus optional line number, never input text."""
    def __init__(self, code, line=None):
        self.code, self.line = code, line
        super().__init__(code)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("duplicate_json_key")
        result[key] = value
    return result


def load_contract(text):
    """Validate a versioned JSON contract. Unknown options are errors, not typos ignored."""
    try:
        doc = json.loads(text, object_pairs_hook=no_duplicates)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError("invalid_contract_json") from None
    if not isinstance(doc, dict) or set(doc) != {"version", "variables"}:
        raise ConfigError("invalid_contract_structure")
    if type(doc["version"]) is not int or doc["version"] != 1:
        raise ConfigError("unsupported_contract_version")
    variables = doc["variables"]
    if not isinstance(variables, dict) or not 1 <= len(variables) <= 512:
        raise ConfigError("invalid_variables")
    for name, rule in variables.items():
        if not NAME.fullmatch(name):
            raise ConfigError("invalid_variable_name")
        if not isinstance(rule, dict) or set(rule) - {"type", "required", "allow_empty", "min", "max", "choices"}:
            raise ConfigError("invalid_rule")
        kind = rule.get("type", "string")
        if not isinstance(kind, str) or kind not in TYPES:
            raise ConfigError("invalid_type")
        for flag in ("required", "allow_empty"):
            if flag in rule and type(rule[flag]) is not bool:
                raise ConfigError("invalid_boolean_option")
        for bound in ("min", "max"):
            if bound in rule and (kind != "integer" or type(rule[bound]) is not int):
                raise ConfigError("invalid_integer_bound")
        if "min" in rule and "max" in rule and rule["min"] > rule["max"]:
            raise ConfigError("inverted_integer_bounds")
        if "choices" in rule:
            choices = rule["choices"]
            if not isinstance(choices, list) or not choices or any(not isinstance(v, str) for v in choices):
                raise ConfigError("invalid_choices")
            if len(set(choices)) != len(choices):
                raise ConfigError("duplicate_choices")
    return variables


def parse_env(text):
    """Strict single-line dotenv subset. No execution, expansion, or escape decoding."""
    values = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export ") or stripped.startswith("export\t"):
            stripped = stripped[6:].lstrip()
        if "=" not in stripped:
            raise ConfigError("expected_assignment", number)
        name, value = stripped.split("=", 1)
        name, value = name.strip(), value.strip()
        if not NAME.fullmatch(name):
            raise ConfigError("invalid_variable_name", number)
        if name in values:
            raise ConfigError("duplicate_variable", number)
        if '\x00' in value:
            raise ConfigError("nul_in_value", number)
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0:
                raise ConfigError("unclosed_quote_or_multiline", number)
            tail = value[end + 1:].strip()
            if tail and not tail.startswith("#"):
                raise ConfigError("text_after_quote", number)
            value = value[1:end]
            if '\\' in value:
                raise ConfigError("quoted_escapes_unsupported", number)
        else:
            value = value.split("#", 1)[0].rstrip()
            if '"' in value or "'" in value:
                raise ConfigError("quotes_in_unquoted_value", number)
        values[name] = value
    return values


def read_bounded(path, limit):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ConfigError("file_too_large")
        return raw.decode("utf-8-sig")
    except UnicodeError:
        raise ConfigError("invalid_utf8") from None
    except OSError:
        # Paths and exception messages may contain sensitive user data.
        raise ConfigError("file_unreadable") from None


def validate(variables, values, strict_extra=False):
    """Contract and input must already be parsed. No values appear in the result."""
    errors, warnings = [], []
    def add(name, code):
        errors.append({"name": name, "code": code})
    for name, rule in sorted(variables.items()):
        if name not in values:
            if rule.get("required", True):
                add(name, "missing")
            continue
        value = values[name]
        if not isinstance(value, str):
            raise ConfigError("non_string_input")
        if not value.strip():
            if not rule.get("allow_empty", False):
                add(name, "empty")
            continue
        kind = rule.get("type", "string")
        if kind == "integer":
            # Bound length prevents int-conversion DoS/limits; no raw value in errors.
            if not INTEGER.fullmatch(value) or len(value.lstrip('+-')) > 100:
                add(name, "invalid_integer")
            else:
                number = int(value)
                if "min" in rule and number < rule["min"]:
                    add(name, "below_minimum")
                if "max" in rule and number > rule["max"]:
                    add(name, "above_maximum")
        elif kind == "boolean" and value not in ("true", "false"):
            add(name, "invalid_boolean")
        elif kind == "http_url":
            try:
                url = urlsplit(value)
                valid = (url.scheme in ("http", "https") and url.hostname is not None
                         and not any(c.isspace() or ord(c) < 32 or c == '\\' for c in value)
                         and url.username is None and url.password is None)
                port = url.port
                valid = valid and (port is None or 1 <= port <= 65535)
            except ValueError:
                valid = False
            if not valid:
                add(name, "invalid_http_url")
        if "choices" in rule and value not in rule["choices"]:
            add(name, "not_in_choices")
    for name in sorted(set(values) - set(variables)):
        if not NAME.fullmatch(name):
            raise ConfigError("invalid_variable_name")
        entry = {"name": name, "code": "unexpected"}
        (errors if strict_extra else warnings).append(entry)
    return {"format_version": 1, "ok": not errors,
            "summary": {"declared": len(variables), "errors": len(errors), "warnings": len(warnings)},
            "errors": errors, "warnings": warnings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", help="version-1 JSON rules")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--env-file", help="explicit UTF-8 dotenv file; never sourced")
    source.add_argument("--process", action="store_true", help="check declared names in current process only")
    parser.add_argument("--strict-extra", action="store_true", help="fail for undeclared file keys (not with --process)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        if args.process and args.strict_extra:
            raise ConfigError("strict_extra_requires_file")
        variables = load_contract(read_bounded(args.contract, MAX_SCHEMA_BYTES))
        if args.process:
            values = {name: os.environ[name] for name in variables if name in os.environ}
        else:
            values = parse_env(read_bounded(args.env_file, MAX_ENV_BYTES))
        report = validate(variables, values, args.strict_extra)
        code = 0 if report["ok"] else 1
    except ConfigError as exc:
        report = {"format_version": 1, "ok": False, "input_error": {"code": exc.code}}
        if exc.line is not None:
            report["input_error"]["line"] = exc.line
        code = 2
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    elif "input_error" in report:
        detail = report["input_error"]
        print("INPUT ERROR: " + detail["code"] + (f" (line {detail['line']})" if "line" in detail else ""))
    else:
        print("PASS" if report["ok"] else "FAIL")
        for level in ("errors", "warnings"):
            for item in report[level]:
                print(f"{level[:-1].upper()}: {item['name']}: {item['code']}")
        print(f"{report['summary']['errors']} error(s), {report['summary']['warnings']} warning(s)")
    return code


if __name__ == "__main__":
    sys.exit(main())
