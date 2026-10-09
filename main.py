"""
海贼王知识库问答助手 — FastAPI 版本
支持流式输出 (Server-Sent Events)
"""
import json
import os
import time
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import CSVLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config

# ── FastAPI 应用 ──────────────────────────────────────────────
app = FastAPI(title="海贼王知识库问答API", description="One Piece QA Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ── 简易限流（公网部署时防止 API 额度被刷爆）──────────────────
# 默认：每个 IP 每 5 分钟最多 20 次提问；可用环境变量 RATE_LIMIT_PER_5MIN 调整
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_5MIN", "20"))
_RATE_WINDOW = 300
_hits = defaultdict(list)


def _client_ip(request: Request) -> str:
    """优先读取代理转发的真实 IP（Render 等平台会带 X-Forwarded-For 头）"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_ok(request: Request) -> bool:
    """滑动窗口限流：返回 False 表示本次请求应被拒绝"""
    now = time.time()
    ip = _client_ip(request)
    recent = [t for t in _hits[ip] if now - t < _RATE_WINDOW]
    if len(recent) >= RATE_LIMIT:
        _hits[ip] = recent
        return False
    recent.append(now)
    _hits[ip] = recent
    return True


# ── 构建向量库 ──────────────────────────────────────────────
def build_vector_store():
    import os
    if not os.path.exists(config.VECTORSTORE_PATH):
        print("首次启动：加载知识库构建向量库...")
        files = {
            "onepiece_人物库.csv": CSVLoader,
            "onepiece_重大事件时间线.csv": CSVLoader,
            "onepiece_恶魔果实.csv": CSVLoader,
            "onepiece_世界观框架.txt": TextLoader,
            "onepiece_四皇完整档案.csv": CSVLoader,
            "onepiece_历代七武海详解.csv": CSVLoader,
            "onepiece_海军高层档案.csv": CSVLoader,
            "onepiece_革命军势力完整档案.csv": CSVLoader,
            "onepiece_各大海贼团.csv": CSVLoader,
            "onepiece_地下黑暗世界帝王 & 黑暗势力.csv": CSVLoader
        }
        docs = []
        for filename, loader_class in files.items():
            file_path = os.path.join(config.DATA_PATH, filename)
            if os.path.exists(file_path):
                loader = loader_class(file_path, encoding="utf-8")
                docs.extend(loader.load())
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP
        )
        split_docs = splitter.split_documents(docs)
        
        embeddings = DashScopeEmbeddings(
            model=config.EMBED_MODEL,
            dashscope_api_key=config.OPENAI_API_KEY
        )
        db = Chroma.from_documents(
            documents=split_docs,
            embedding=embeddings,
            persist_directory=config.VECTORSTORE_PATH
        )
        print("向量库构建完成！")
    else:
        print("加载本地缓存向量库...")


# ── 业务逻辑 ──────────────────────────────────────────────
class OnePieceQA:

    def __init__(self):
        self.embeddings_model = DashScopeEmbeddings(
            model=config.EMBED_MODEL,
            dashscope_api_key=config.OPENAI_API_KEY,
        )
        self.chroma = Chroma(
            persist_directory=config.VECTORSTORE_PATH,
            embedding_function=self.embeddings_model,
        )
        self.llm_model = ChatOpenAI(
            model=config.MODEL_NAME,
            base_url=config.OPENAI_BASE_URL,
            api_key=config.OPENAI_API_KEY,
            streaming=True,
            temperature=0.1
        )

    def _get_relevant_docs(self, question: str):
        list_keywords = ["有哪些", "都有谁", "名单", "列表", "全部", "所有", "包含", "哪些"]
        is_list_query = any(kw in question for kw in list_keywords)
        
        if is_list_query:
            docs = self.chroma.similarity_search(question, k=config.LIST_TOP_K)
        else:
            docs = self.chroma.similarity_search(question, k=config.TOP_K)
        
        unique_docs = []
        seen_contents = set()
        for doc in docs:
            content = doc.page_content
            if content not in seen_contents:
                seen_contents.add(content)
                unique_docs.append(doc)
        
        return unique_docs

    def ask_question(self, question: str):
        docs = self._get_relevant_docs(question)
        
        prompt_template = """你是海贼王专属知识库问答机器人，只允许使用下面提供的知识库内容回答。
硬性规则：
1. 如果知识库没有对应信息，直接回复：【暂无相关知识库资料，无法解答】，绝对不能编造人物、果实、剧情。
2. 查询人物：分点输出姓名、阵营、身份、恶魔果实、能力、悬赏、梦想、关键剧情。
3. 查询事件/世界观：分段清晰，逻辑通顺。
4. 一次性询问多个人物，逐条分开介绍。
5. 如果问题涉及列表查询（如"有哪些"、"都有谁"、"完整名单"），请尽可能列出所有相关信息。

知识库参考内容：
{context}

用户提问：{question}
答案：
"""
        contents = [doc.page_content for doc in docs]
        context = "\n\n".join(contents)
        template = PromptTemplate.from_template(prompt_template)
        prompt = template.invoke({"context": context, "question": question})
        result = self.llm_model.invoke(prompt)
        return result.content

    def ask_question_stream(self, question: str):
        docs = self._get_relevant_docs(question)
        
        prompt_template = """你是海贼王专属知识库问答机器人，只允许使用下面提供的知识库内容回答。
硬性规则：
1. 如果知识库没有对应信息，直接回复：【暂无相关知识库资料，无法解答】，绝对不能编造人物、果实、剧情。
2. 查询人物：分点输出姓名、阵营、身份、恶魔果实、能力、悬赏、梦想、关键剧情。
3. 查询事件/世界观：分段清晰，逻辑通顺。
4. 一次性询问多个人物，逐条分开介绍。
5. 如果问题涉及列表查询（如"有哪些"、"都有谁"、"完整名单"），请尽可能列出所有相关信息。

知识库参考内容：
{context}

用户提问：{question}
答案：
"""
        contents = [doc.page_content for doc in docs]
        context = "\n\n".join(contents)
        template = PromptTemplate.from_template(prompt_template)
        prompt = template.invoke({"context": context, "question": question})

        for chunk in self.llm_model.stream(prompt):
            if chunk.content:
                yield chunk.content


# ── 延迟初始化 ──────────────────────────────────────────────
build_vector_store()
_qa_system: OnePieceQA | None = None


def get_qa() -> OnePieceQA:
    global _qa_system
    if _qa_system is None:
        _qa_system = OnePieceQA()
    return _qa_system


# ── 路由 ─────────────────────────────────────────────────────
@app.get("/")
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    question = (data.get("question") or "").strip()

    if not question:
        return {"code": 400, "msg": "问题不能为空", "data": ""}

    if not _rate_ok(request):
        return {"code": 429, "msg": "提问过于频繁，请稍后再试（演示站点设有频率限制）", "data": ""}

    try:
        qa = get_qa()
        answer = qa.ask_question(question)
        return {"code": 200, "msg": "success", "data": answer}
    except Exception as exc:
        return {"code": 500, "msg": str(exc), "data": ""}

@app.post("/api/chat/stream")
async def chat_stream(request: Request):
    data = await request.json()
    question = (data.get("question") or "").strip()

    if not question:
        async def _error():
            yield f"data: {json.dumps({'error': '问题不能为空'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_error(), media_type="text/event-stream")

    if not _rate_ok(request):
        async def _limited():
            yield f"data: {json.dumps({'error': '提问过于频繁，请稍后再试'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_limited(), media_type="text/event-stream")

    qa = get_qa()

    async def _stream():
        try:
            for text in qa.ask_question_stream(question):
                yield f"data: {json.dumps({'content': text}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "海贼王知识库问答助手"}


# ── 启动入口 ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
