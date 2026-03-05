import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 基础路径
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

# 创建目录
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# API 配置
API_KEY = os.getenv("API_KEY", "")
API_URL = os.getenv("API_URL", "https://open.bigmodel.cn/api/paas/v4")

# 服务配置
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# 模型配置
MODEL_NAME = os.getenv("MODEL_NAME", "small")
LANGUAGE = os.getenv("LANGUAGE", "zh")
GROUP_SIZE = int(os.getenv("GROUP_SIZE", "8"))

# 系统提示词
SYSTEM_PROMPT = """你是一个视频内容分析专家。你的任务是从转录文本中识别出最精彩、最有爆点（吸引眼球、引发讨论）的片段。

请分析以下转录文本，识别出3-5个最可能有爆点的片段。每个片段需要包含：
1. start: 开始时间（秒）
2. end: 结束时间（秒）
3. title: 简短有吸引力的标题（15字以内）
4. reason: 为什么这个片段是爆点（50字以内）

判断爆点的标准：
- 有争议性的观点或话题
- 幽默有趣的表达
- 令人惊讶的信息或反转
- 情感强烈的表达
- 有独到见解的内容
- 引发思考的金句

请以JSON数组格式返回结果，格式如下：
[
  {"start": 0.0, "end": 30.5, "title": "标题1", "reason": "原因1"},
  {"start": 45.0, "end": 80.2, "title": "标题2", "reason": "原因2"}
]

注意：
- 时间戳必须准确，基于提供的start和end
- 对于长视频，每个片段要涵盖完整的观点或信息点
- 标题要简洁有力，能吸引观众
- 原因要说明为什么这个片段吸引人
- 只返回JSON数组，不要其他内容
"""
