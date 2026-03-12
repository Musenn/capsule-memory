# LangChain Integration

> **English** | [中文](langchain_zh.md)

## CapsuleMemoryLangChainMemory

Drop-in replacement for `ConversationBufferMemory`:

```python
from capsule_memory import CapsuleMemory
from capsule_memory.adapters.langchain import CapsuleMemoryLangChainMemory

cm = CapsuleMemory()
memory = CapsuleMemoryLangChainMemory(cm=cm, user_id="user_123")

# Use with LangChain chains
from langchain.chains import LLMChain
chain = LLMChain(llm=llm, prompt=prompt, memory=memory)
chain.run("Hello!")

# Seal when done
memory.seal(title="My Session", tags=["langchain"])
```

See `examples/integrate_langchain.py` for a complete runnable example.
