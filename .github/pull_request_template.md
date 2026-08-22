name: Pull request
description: Submit a change to the HP Printers integration
body:
  - type: markdown
    attributes:
      content: |
        Thanks for contributing. Please run the verification steps in `AGENTS.md`
        before opening a PR, and attach diagnostics or screenshots for any
        printer-side change.
  - type: checkboxes
    id: verification
    attributes:
      label: Verification
      options:
        - label: I ran `./.venv/bin/ruff check --config ruff_ha.toml custom_components/hp_printers tests` and it passed
        - label: I ran `./.venv/bin/ruff format --check --config ruff_ha.toml custom_components/hp_printers tests` and it passed
        - label: I ran `./.venv/bin/python -m compileall -q custom_components/hp_printers tests` and it passed
        - label: I ran `./.venv/bin/python -m pytest -q` and it passed
  - type: checkboxes
    id: tests
    attributes:
      label: Test coverage
      description: Functional changes must ship with tests. Confirm one of the following.
      options:
        - label: This PR adds new functionality and includes a test in `tests/`
        - label: This PR fixes a bug and includes a regression test in `tests/`
        - label: This PR is documentation, CI, or a refactor with no behaviour change, and the existing tests still cover it
  - type: dropdown
    id: change
    attributes:
      label: Type of change
      options:
        - Bug fix
        - New feature
        - Documentation
        - Maintenance
    validations:
      required: true
  - type: textarea
    id: testing
    attributes:
      label: How did you verify it?
    validations:
      required: true
