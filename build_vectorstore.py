# 存储向量数据的
import os

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader, PyPDFLoader, CSVLoader
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config

class VectorStoreBuilder:
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", "。", ";", "  ", " "],
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP
        )
        self.embedding_model = DashScopeEmbeddings(
            model=config.EMBED_MODEL,
            dashscope_api_key=config.OPENAI_API_KEY
        )

    def build_store(self):
        list_file = os.listdir(config.DATA_PATH)
        all_docs = []
        for file in list_file:
            loader = None
            file_path = os.path.join(config.DATA_PATH, file)
            if file.endswith(".txt"):
                loader = TextLoader(file_path=file_path, encoding="utf-8")
            elif file.endswith(".pdf"):
                loader = PyPDFLoader(file_path=file_path)
            elif file.endswith(".csv"):
                loader = CSVLoader(file_path=file_path, encoding="utf-8")
            
            if loader:
                docs = loader.load()
                all_docs.extend(docs)
        
        if all_docs:
            split_docs = self.splitter.split_documents(all_docs)
            Chroma.from_documents(
                documents=split_docs,
                embedding=self.embedding_model,
                persist_directory=config.VECTORSTORE_PATH
            )
            print(f"向量库构建完成，共处理 {len(all_docs)} 个文档，生成 {len(split_docs)} 个片段")
        else:
            print("未找到任何可处理的文档")




if __name__ == '__main__':
    VectorStoreBuilder().build_store()

