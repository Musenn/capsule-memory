# OpenAI 集成

> [English](openai.md) | **中文**

## 通过 REST API 直接集成（无需 SDK）

```python
import httpx

# 召回记忆
async with httpx.AsyncClient() as client:
    resp = await client.get("http://localhost:8000/api/v1/recall",
                            params={"q": "用户查询", "user_id": "user_123"})
    context = resp.json()["prompt_injection"]

# 注入到 OpenAI 调用
response = await openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": f"请参考以下上下文:\n{context}"},
        {"role": "user", "content": "你的问题"},
    ],
)
```

完整可运行示例参见 `examples/integrate_openai_direct.py`。
