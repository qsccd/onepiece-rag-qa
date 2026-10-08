# config.py
# 项目配置文件
#
# 安全约定：API Key 不写在代码里，而是从 .env 或系统环境变量读取。
# 换机器 / 别人接手时，复制 .env.example 为 .env 并填入自己的密钥即可。
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # 未安装 python-dotenv 时退化为只读系统环境变量
    pass

# 路径配置
DATA_PATH = "./data"
VECTORSTORE_PATH = "./chroma_onepiece_vsdb"

# 支持的文件类型
SUPPORTED_EXTENSIONS = ['.txt', '.pdf', '.csv']

# 分割参数
CHUNK_SIZE = 700
CHUNK_OVERLAP = 80

# 检索参数
TOP_K = 50

# LLM 模型配置
OPENAI_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
OPENAI_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
MODEL_NAME = "qwen3-max"
EMBED_MODEL = "text-embedding-v3"

if not OPENAI_API_KEY:
    raise RuntimeError(
        "未找到 API Key。\n"
        "请在项目根目录创建 .env 文件（可复制 .env.example 改名），内容为：\n"
        "DASHSCOPE_API_KEY=你的阿里百炼密钥\n"
        "DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
