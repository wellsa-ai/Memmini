# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No changes yet.

## [0.4.0] - 2026-08-05

### Added
- Optional `MemvidStorage` backend for portable single-file L2 snapshots.
- `[memvid]` extra with `memvid-sdk>=2.0.160,<3.0` isolated from the default install.
- Embedded-frame/WAL verification, source-ref restore, and snapshot copy/restore helpers.
- Memvid backend example plus unit, optional SDK e2e, and deterministic micro-benchmark coverage.
- Relationship event replay for both fallback and native SDK Memvid backends.

### Changed
- Version bumped to 0.4.0 for the optional backend API surface.
- Storage package exports `MemvidStorage` while keeping `FileStorage` as the default path.

## [0.3.0] - 2026-07-31

### Added
- Symbolic context offload for long short-term task context (`refs/*.jsonl`).
- Deterministic `node_id` and `source_ref` fields for file-backed memory records.
- `resolve_source_ref()` drill-down API for original source recovery.
- Rule-based `extract_scenarios()` and `extract_persona()` APIs with provenance.
- Public provenance/offload example.

### Changed
- Search results now include provenance fields for file-backed storage.
- Version bumped to 0.3.0 for the provenance/offload API surface.

## [0.2.0] - 2026-06-09

### Added
- Initial public release
- L0/L1/L2 hierarchical memory system
- MemoryCore API with 60-80% token savings
- FileStorage backend (JSON + Markdown files)
- VectorStorage backend (ChromaDB)
- HybridStorage combining both
- LayerGenerator with LLM and rule-based modes
- CLI tool (`memmini`)
- OpenClaw adapter
- Local test suite for the runtime package

### Fixed
- VectorStorage empty metadata handling

## [0.1.0] - 2026-02-15

### Initial Features

**Core Memory Management:**
- Add, retrieve, update, delete memories
- Namespace isolation (user/agent separation)
- TTL-based memory expiration
- Automatic layer generation

**Storage Backends:**
- File-based storage with SQLite
- Vector storage with ChromaDB
- Hybrid storage combining both

**Token Optimization:**
- L0: One-line summary (~100 tokens)
- L1: Key summary (~500 words)
- L2: Full content
- 60-80% token savings verified

**Developer Experience:**
- Simple API (`MemoryCore`)
- CLI tool for quick operations
- Type hints and docstrings
- Focused coverage for core modules

**Documentation:**
- README with quick start
- API documentation
- User guide
- Design documents

---

[Unreleased]: https://github.com/wellsa-ai/Memmini/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/wellsa-ai/Memmini/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/wellsa-ai/Memmini/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/wellsa-ai/Memmini/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wellsa-ai/Memmini/releases/tag/v0.1.0
