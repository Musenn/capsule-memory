# Attribution & Format Specification

> **English** | [中文](attribution_zh.md)

## Schema Attribution

Every capsule produced by CapsuleMemory carries the following metadata:

| Field | Value |
|-------|-------|
| `schema_version` | `capsule-schema/1.0+4240ea9f` |
| `capsule_id` prefix | Includes protocol fingerprint |
| `checksum` | HMAC-SHA256 integrity seal |
| `metadata.capsule_created_by` | `capsule-memory` |
| `metadata.capsule_project_url` | `https://github.com/Musenn/capsule-memory` |

## Usage Requirements

CapsuleMemory is released under the Apache-2.0 License. When using this library:

1. **Keep attribution metadata intact** — Do not strip `capsule_created_by` or `capsule_project_url` from exported capsules.
2. **Preserve checksums** — The `checksum` field enables integrity verification. Tampering with capsule content without recomputing the checksum will cause validation failures.
3. **Schema compatibility** — Third-party tools that consume capsule files should respect the `schema_version` field and handle unknown fields gracefully.

## Verifying Capsule Integrity

```python
from capsule_memory.models import Capsule

capsule = ...  # loaded from storage or file
is_valid = capsule.verify_checksum()
```

The `verify_checksum()` method recomputes the checksum and compares it against the stored value.
