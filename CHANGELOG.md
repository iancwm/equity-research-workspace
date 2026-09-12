# Changelog

All notable changes follow [Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-09-12

### Added

- Sector primer skill for explaining industry structure, sector analytics, and comparable companies.
- Persistent sector workspace initializer and structural validator.
- Automated tests for sector workspace creation and validation paths.

## [2.0.0] - 2026-09-10

### Added

- Canonical Agent Skills package with Claude plugin and Codex UI metadata.
- Dependency-free workspace initialization and validation.
- Normative JSON Schemas, reproducible packaging, offline tests, and behavioral eval cases.
- Non-destructive v1 migration utility and cross-platform installation documentation.

### Changed

- Moved mutable company research outside the installed skill.
- Replaced YAML state and the CSV source registry with JSON and JSONL.
- Reworked prompts into vendor-neutral, progressively disclosed references.

### Removed

- Vendor-specific model routing and Work-mode assumptions.
- The tracked runtime AAPL workspace and root-level duplicate skill resources.
