import os

from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

import config

class OnePieceQA:

    def __init__(self):
        self.embedding_model = DashScopeEmbeddings(
            model=config.EMBED_MODEL,
            dashscope_api_key=config.OPENAI_API_KEY
        )
        self.llm_model = ChatOpenAI(
            model=config.MODEL_NAME,
            base_url=config.OPENAI_BASE_URL,
            api_key=config.OPENAI_API_KEY
        )

    def ask_question(self, question):
        template = PromptTemplate.from_template("""你是海贼王专属知识库问答机器人，只允许使用下面提供的知识库内容回答。
硬性规则：
1. 如果知识库没有对应信息，直接回复：【暂无相关知识库资料，无法解答】，绝对不能编造人物、果实、剧情。
2. 查询人物：分点输出姓名、阵营、身份、恶魔果实、能力、悬赏、梦想、关键剧情。
3. 查询事件/世界观：分段清晰，逻辑通顺。
4. 一次性询问多个人物，逐条分开介绍。

检索到的内容:
{context}

问题: {question}
答案:
""")

        chroma = Chroma(persist_directory=config.VECTORSTORE_PATH, embedding_function=self.embedding_model)
        docs = chroma.similarity_search_with_relevance_scores(question, k=config.TOP_K)
        contents = [doc[0].page_content for doc in docs]
        context = "\n\n".join(contents)
        prompt = template.invoke({"context": context, "question": question})
        result = self.llm_model.invoke(prompt)
        print(result.content)
        return result.content

if __name__ == '__main__':
    OnePieceQA().ask_question("路飞的悬赏金是多少？")
