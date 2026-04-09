from openai import OpenAI

client = OpenAI(
    api_key="d177a2b9dd11494089bfaaae1d313c86.nen8jEX2bgDa6ViW",
    base_url="https://open.bigmodel.cn/api/coding/paas/v4"
)

stream = client.chat.completions.create(
    model="glm-5",
    messages=[
        {"role": "user", "content": "写一首关于人工智能的诗"}
    ],
    stream=True,
    temperature=0.8
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="", flush=True)

print()  # 换行