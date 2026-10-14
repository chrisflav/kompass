"""The package a section's finance rules import from.

One module lives here, :mod:`kompass.rules`, and it is the only thing a
ruleset may import from Kompass. Keeping it under its own short name — rather
than letting rulesets import ``finance.rules_api`` — is what lets the import
whitelist name one allowed module, and what lets a section type-check its
rules against the same name the running instance offers them.
"""
