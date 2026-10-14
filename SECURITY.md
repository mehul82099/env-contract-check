# Security model and reporting

This is a configuration validator, not a secret scanner, vault, sandbox or audit.
Use trusted contracts and keep real variable values out of contract choices.

Normal validation output contains variable names, fixed codes and counts, not
values, paths or raw parse errors. Names themselves can disclose system design.
Only the explicit file is read. Process mode reads only declared names. File mode
does not merge process variables. Nothing is sourced, executed, rewritten or sent
over the network. No logs are written by the tool. Input content is held in memory.

Limits: env files at most 1 MiB; contracts at most 256 KiB / 512 variables;
integers at most 100 digits. These are guardrails, not isolation against a hostile
local environment, interpreter, stdout redirection, operating system or dependencies.

If you report a bug publicly, use fictional values. Do not include secrets, tokens,
real environment dumps or customer data. For sensitive details, first open an issue
with only a non-sensitive description and ask for a private reporting route. This
repo does not promise an existing monitored security mailbox or response deadline.
