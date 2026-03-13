# 归属与格式规范

> [English](attribution.md) | **中文**

## Schema 归属信息

CapsuleMemory 生成的每个胶囊均携带以下元数据：

| 字段 | 值 |
|------|-----|
| `schema_version` | `capsule-schema/1.0+4240ea9f` |
| `capsule_id` 前缀 | 包含协议指纹 |
| `checksum` | HMAC-SHA256 完整性校验 |
| `metadata.capsule_created_by` | `capsule-memory` |
| `metadata.capsule_project_url` | `https://github.com/Musenn/capsule-memory` |

## 使用要求

CapsuleMemory 基于 Apache-2.0 许可证发布。使用本库时：

1. **保留归属元数据** — 不要从导出的胶囊中移除 `capsule_created_by` 或 `capsule_project_url` 字段。
2. **保留校验和** — `checksum` 字段用于完整性验证。篡改胶囊内容而不重新计算校验和将导致验证失败。
3. **Schema 兼容性** — 消费胶囊文件的第三方工具应尊重 `schema_version` 字段，并优雅地处理未知字段。

## 验证胶囊完整性

```python
from capsule_memory.transport.schema_validator import verify_checksum

capsule_dict = capsule.model_dump()  # 或从 JSON 文件加载
is_valid = verify_checksum(capsule_dict)
```

`verify_checksum()` 函数重新计算 HMAC-SHA256 校验和，并与存储的值进行比较。
