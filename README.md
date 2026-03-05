# 视频爆点提取工具

自动识别视频中的精彩片段，提取爆点并裁剪成短视频。

## 功能特性

- 视频转音频自动提取
- Whisper 语音转文本（支持中文）
- AI 分析识别爆点片段
- 自动裁剪生成短视频
- 支持命令行和 API 两种使用方式

## 环境要求

- Python 3.10+
- CUDA (可选，用于 GPU 加速)
- ffmpeg

## 安装步骤

### 1. 克隆项目

```bash
git clone git@github.com:YuYuCodeNoob/autoClipper.git
cd autoClipper
```

### 2. 创建 conda 环境

```bash
# 创建环境
conda create -n whisper python=3.10

# 激活环境
conda activate whisper
```

### 3. 安装 Python 依赖

```bash
# 安装依赖
pip install -r requirements.txt

# 或手动安装
pip install faster-whisper tqdm openai python-dotenv
```

### 4. 安装 ffmpeg

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install ffmpeg
```

#### macOS

```bash
brew install ffmpeg
```

#### Windows

**方法一：直接下载**
1. 下载地址：https://github.com/BtbN/FFmpeg-Builds/releases/
2. 选择 win64 版本解压到固定位置
3. 设置环境变量

**方法二：使用 winget（Win10/11）**
```cmd
winget install ffmpeg
```

**方法三：使用 Chocolatey**
```cmd
choco install ffmpeg
```

验证安装：
```bash
ffmpeg -version
```

### 5. 配置 API

创建 `.env` 文件：

```bash
# .env
API_KEY=你的API密钥
API_URL=https://open.bigmodel.cn/api/paas/v4
```

---

## 使用方法

### 方式一：命令行脚本（推荐）

```bash
conda activate whisper
python main.py -v <视频文件> [-o <输出目录>] [-g <分组大小>]
```

**参数说明：**

| 参数 | 简写 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--video` | `-v` | 是 | - | 输入视频文件路径 |
| `--output` | `-o` | 否 | `./output` | 输出目录 |
| `--group` | `-g` | 否 | `8` | 合并多少句为一段（方便可视化） |

**使用示例：**

```bash
# 基本用法
python main.py -v video.mp4

# 指定输出目录
python main.py -v video.mp4 -o ./output

# 指定分组大小（每 10 句合并为一段）
python main.py -v video.mp4 -o ./output -g 10
```

**查看帮助：**

```bash
python main.py --help
```

---

### 方式二：FastAPI 服务

启动 API 服务：

```bash
conda activate whisper
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `POST /api/tasks/check` | POST | 校验文件 hash 是否已处理 |
| `POST /api/tasks` | POST | 提交视频处理任务 |
| `GET /api/tasks/{task_id}` | GET | 查询任务状态 |
| `GET /api/tasks/list` | GET | 获取任务列表（分页） |
| `GET /api/files/{task_id}/clips.zip` | GET | 下载处理结果 |
| `WS /ws/{task_id}` | WebSocket | 实时进度推送 |
| `GET /health` | GET | 健康检查 |

**使用示例：**

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 提交任务
curl -X POST http://localhost:8000/api/tasks \
  -F "file=@video.mp4" \
  -F "model_name=small" \
  -F "language=zh" \
  -F "group_size=8"

# 3. 查询任务状态
curl http://localhost:8000/api/tasks/{task_id}

# 4. 获取任务列表
curl "http://localhost:8000/api/tasks/list?limit=10&offset=0"

# 5. 下载结果
curl -o result.zip http://localhost:8000/api/files/{task_id}/clips.zip
```

**使用交互式客户端测试：**

```bash
python client.py
```

---

### 3. 查看结果

运行完成后，在输出目录下查看：

```
output/
├── audio_extract.mp3           # 提取的音频
├── transcription_raw.json      # 原始转录结果
├── transcription_merged.json   # 合并后的转录
├── highlights.json             # 爆点分析结果
├── clip_1_xxx.mp4             # 裁剪的视频片段
├── clip_2_xxx.mp4
└── ...
```

---

## 配置说明

### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| -v, --video | 输入视频文件 | (必需) |
| -o, --output | 输出目录 | ./output |
| -g, --group | 每多少句合并为一段 | 8 |

### 环境变量

| 变量 | 说明 |
|------|------|
| API_KEY | AI API 密钥 |
| API_URL | API 地址 |
| HOST | 服务监听地址 (FastAPI) |
| PORT | 服务监听端口 (FastAPI) |
| MODEL_NAME | Whisper 模型名称 |
| LANGUAGE | 识别语言 |
| GROUP_SIZE | 分组大小 |

---

## Whisper 模型选择

| 模型 | 大小 | 速度 | 推荐场景 |
|------|------|------|----------|
| tiny | ~75MB | 最快 | 测试 |
| base | ~75MB | 快 | CPU 使用 |
| small | ~250MB | 中等 | 推荐配置 |
| medium | ~1.5GB | 较慢 | 高精度 |
| large | ~3GB | 最慢 | 最高精度 |

---

## 常见问题

### Q: 显存不足怎么办？
A: 使用更小的模型（tiny/base），或使用 CPU 模式：
```python
model = WhisperModel("small", device="cpu", compute_type="int8")
```

### Q: 转录结果不准确？
A: 尝试使用更大的模型，或调整 `beam_size` 参数。

### Q: Windows 上找不到 ffmpeg？
A: 确保已将 ffmpeg 添加到系统环境变量 PATH，重启终端后再试。

### Q: 如何使用其他 AI API？
A: 修改 `.env` 中的 `API_URL` 和 `API_KEY`。

### Q: API 服务如何调用？
A: 参考上方 API 接口文档，或使用 `python client.py` 进行交互式测试。
