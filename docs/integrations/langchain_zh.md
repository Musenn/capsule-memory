# LangChain 集成

> [English](langchain.md) | **中文**

## CapsuleMemoryLangChainMemory

`ConversationBufferMemory` 的即插即用替代：

```python
from capsule_memory import CapsuleMemory
from capsule_memory.adapters.langchain import CapsuleMemoryLangChainMemory

cm = CapsuleMemory()
memory = CapsuleMemoryLangChainMemory(cm=cm, user_id="user_123")

# 配合 LangChain Chain 使用
from langchain.chains import LLMChain
chain = LLMChain(llm=llm, prompt=prompt, memory=memory)
chain.run("你好！")

# 完成后封存
memory.seal(title="我的会话", tags=["langchain"])
```

完整可运行示例参见 `examples/integrate_langchain.py`。
