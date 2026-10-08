from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import gradio as gr
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.document_loaders import CSVLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
import time
import os

# ====================== 配置区（必须修改API_KEY） ======================
API_KEY = "sk-你的阿里百炼密钥"
COMPATIBLE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
VECTOR_DB_PATH = "faiss_onepiece_store"
# 知识库文件
FILE_CHAR = "onepiece_人物库.csv"
FILE_EVENT = "onepiece_重大事件时间线.csv"
FILE_WORLD = "onepiece_世界观框架.txt"
# ====================================================================

# FastAPI 实例
app = FastAPI(title="海贼王知识库问答API", version="1.0")

# 跨域允许，浏览器前端正常访问接口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化大模型与Embedding
llm = ChatOpenAI(
    model="qwen3-max",
    base_url=COMPATIBLE_URL,
    api_key=API_KEY,
    temperature=0.1
)
embedding = OpenAIEmbeddings(
    base_url=COMPATIBLE_URL,
    openai_api_key=API_KEY
)

# 构建/加载向量库
def build_vector_store():
    if not os.path.exists(VECTOR_DB_PATH):
        print("首次启动：加载知识库构建向量库...")
        loader1 = CSVLoader(FILE_CHAR, encoding="utf-8")
        loader2 = CSVLoader(FILE_EVENT, encoding="utf-8")
        loader3 = TextLoader(FILE_WORLD, encoding="utf-8")
        docs = loader1.load() + loader2.load() + loader3.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=80)
        split_docs = splitter.split_documents(docs)
        db = FAISS.from_documents(split_docs, embedding)
        db.save_local(VECTOR_DB_PATH)
        print("向量库构建完成！")
    else:
        print("加载本地缓存向量库...")
        db = FAISS.load_local(VECTOR_DB_PATH, embedding, allow_dangerous_deserialization=True)
    return db

vector_db = build_vector_store()
retriever = vector_db.as_retriever(search_kwargs={"k": 4})

# 问答约束提示词
prompt_rule = PromptTemplate(
    input_variables=["context", "question"],
    template="""
你是海贼王专属知识库问答机器人，只允许使用下面提供的知识库内容回答。
硬性规则：
1. 如果知识库没有对应信息，直接回复：【暂无相关知识库资料，无法解答】，绝对不能编造人物、果实、剧情。
2. 查询人物：分点输出姓名、阵营、身份、恶魔果实、能力、悬赏、梦想、关键剧情。
3. 查询事件/世界观：分段清晰，逻辑通顺。
4. 一次性询问多个人物，逐条分开介绍。

知识库参考内容：
{context}

用户提问：{question}
"""
)

# 问答链
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=retriever,
    return_source_documents=True,
    chain_type_kwargs={"prompt": prompt_rule}
)

# 核心问答函数
def get_answer(user_question: str) -> str:
    if not user_question.strip():
        return "请输入海贼王相关问题！"
    result = qa_chain.invoke({"query": user_question})
    ans = result["result"]
    # 保存对话日志
    log = f"""[{time.strftime('%Y-%m-%d %H:%M:%S')}]
提问：{user_question}
回答：{ans}
————————————————————————————————
"""
    with open("对话日志.txt", "a", encoding="utf-8") as f:
        f.write(log)
    return ans

# ===================== FastAPI 接口 =====================
@app.get("/api/chat")
def api_chat(question: str):
    """GET接口：问答接口"""
    res = get_answer(question)
    return {"code": 200, "msg": "success", "data": res}

@app.post("/api/chat")
def api_chat_post(question: str):
    """POST接口：问答接口"""
    res = get_answer(question)
    return {"code": 200, "msg": "success", "data": res}

# ===================== Gradio 网页界面（挂载到FastAPI） =====================
def create_gradio_ui():
    with gr.Blocks(title="海贼王问答系统", theme=gr.themes.Default()) as web_app:
        gr.Markdown("# 🏴‍☠️ 海贼王本地知识库问答系统（FastAPI后端）")
        gr.Markdown("支持人物、剧情大事件、世界设定查询，仅基于本地资料回答，无虚构内容")

        question_input = gr.Textbox(
            label="输入你的问题",
            placeholder="例如：路飞的悬赏和果实能力、顶上战争过程、古代三大兵器",
            lines=2
        )
        answer_output = gr.Textbox(label="AI回答结果", lines=12)

        with gr.Row():
            submit_btn = gr.Button("提交提问", variant="primary")
            clear_btn = gr.Button("清空输入输出")

        submit_btn.click(fn=get_answer, inputs=[question_input], outputs=[answer_output])
        question_input.submit(fn=get_answer, inputs=[question_input], outputs=[answer_output])
        clear_btn.click(lambda: ("", ""), outputs=[question_input, answer_output])
    return web_app

# 将Gradio页面挂载到FastAPI根路由
ui = create_gradio_ui()
app = gr.mount_gradio_app(app, ui, path="/")

# 程序入口
if __name__ == "__main__":
    # 0.0.0.0 允许局域网所有设备访问，端口8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)