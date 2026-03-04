# 视频爆点提取工具

自动识别视频中的精彩片段，提取爆点并裁剪成短视频。

## 功能特性

- 视频转音频自动提取
- Whisper 语音转文本（支持中文）
- AI 分析识别爆点片段
- 自动裁剪生成短视频
- 进度条显示

## 环境要求

- Python 3.8+
- CUDA (可选，用于 GPU 加速)
- ffmpeg

## 安装步骤

### 1. 克隆项目

```bash
git clone git@github.com:YuYuCodeNoob/autoClipper.git
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
# 安装核心依赖
pip install faster-whisper tqdm openai python-dotenv

# 如果使用 OpenAI 官方接口（可选）
# pip install openai
```

### 4. 安装 ffmpeg

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install ffmpeg
```

#### macOS

```bash
# 使用 Homebrew
brew install ffmpeg
```

#### Windows

**方法一：直接下载**
1. 下载地址：https://github.com/BtbN/FFmpeg-Builds/releases/
2. 选择win64版本解压到固定位置
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

## 使用方法

### 1. 修改配置文件

编辑 `main.py` 顶部的配置：

```python
# 输入文件（支持视频或音频）
INPUT_PATH = "test.mp4"  # 或 test.mp3

# 输出目录
OUTPUT_DIR = "output"

# Whisper 模型：tiny, base, small, medium, large
MODEL_NAME = "small"

# 语言：zh, en 等
LANGUAGE = "zh"

# 合并段落大小
GROUP_SIZE = 8
```

### 2. 运行程序

```bash
conda activate whisper
python main.py
```

### 3. 查看结果

运行完成后，在 `output` 目录下查看：

```
output/
├── audio_extract.mp3       # 提取的音频
├── transcription_raw.json  # 原始转录结果
├── transcription_merged.json # 合并后的转录
├── highlights.json         # 爆点分析结果
├── clip_1_xxx.mp4          # 裁剪的视频片段
├── clip_2_xxx.mp4
└── ...
```

## 配置说明

| 配置项 | 说明 | 可选值 |
|--------|------|--------|
| INPUT_PATH | 输入文件路径 | 视频: .mp4, .avi, .mov 等<br>音频: .mp3, .wav 等 |
| OUTPUT_DIR | 输出目录 | 默认 "output" |
| MODEL_NAME | Whisper 模型大小 | tiny, base, small, medium, large<br>越大越准确但越慢 |
| LANGUAGE | 语音语言 | zh (中文), en (英文) 等 |
| GROUP_SIZE | 每多少句合并一个段落 | 数字，越大段落越长 |

## Whisper 模型选择

| 模型 | 大小 | 速度 | 推荐场景 |
|------|------|------|----------|
| tiny | ~75MB | 最快 | 测试 |
| base | ~75MB | 快 | CPU 使用 |
| small | ~250MB | 中等 | 推荐配置 |
| medium | ~1.5GB | 较慢 | 高精度 |
| large | ~3GB | 最慢 | 最高精度 |

## 常见问题

### Q: 显存不足怎么办？
A: 将 `MODEL_NAME` 改为 "tiny" 或 "base"，或使用 CPU 模式：
```python
model = WhisperModel("small", device="cpu", compute_type="int8")
```

### Q: 转录结果不准确？
A: 尝试使用更大的模型，或调整 `beam_size` 参数。

### Q: Windows 上找不到 ffmpeg？
A: 确保已将 ffmpeg 添加到系统环境变量 PATH，重启终端后再试。

### Q: 如何使用其他 AI API？
A: 修改 `get_api_client()` 函数中的 `base_url` 和模型名称。
