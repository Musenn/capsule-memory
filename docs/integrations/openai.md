# OpenAI Integration

> **English** | [中文](openai_zh.md)

## Direct REST API Integration (No SDK)

```python
import httpx

# Recall memories
async with httpx.AsyncClient() as client:
    resp = await client.get("http://localhost:8000/api/v1/recall",
                            params={"q": "user query", "user_id": "user_123"})
    context = resp.json()["prompt_injection"]

# Inject into OpenAI call
response = await openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": f"Use this context:\n{context}"},
        {"role": "user", "content": "Your question here"},
    ],
)
```

See `examples/integrate_openai_direct.py` for a complete runnable example.
