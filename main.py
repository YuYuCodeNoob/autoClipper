#!/usr/bin/env python3
"""
视频爆点提取脚本
用法: python main.py -v <视频文件> [-o <输出目录>] [-g <分组大小>]
"""
import argparse
import json
from faster_whisper import WhisperModel
from tqdm import tqdm
import subprocess
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("API_KEY")
API_URL = os.getenv("API_URL")

# ============ 配置 ============
MODEL_NAME = "small"  # tiny, base, small, medium, large
LANGUAGE = "zh"

# ============ SYSTEM_PROMPT ============
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

# ============ API 客户端 ============
def get_api_client():
    """获取 API 客户端"""
    return OpenAI(
        api_key=API_KEY,
        base_url=API_URL
    )


# ============ 媒体转换函数 ============
def is_video(file_path: str) -> bool:
    """判断文件是否为视频"""
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm']
    ext = os.path.splitext(file_path)[1].lower()
    return ext in video_extensions


def video_to_audio(video_path: str, audio_path: str) -> str:
    """
    使用 ffmpeg 将视频转换为音频

    Args:
        video_path: 视频文件路径
        audio_path: 输出音频路径

    Returns:
        str: 生成的音频文件路径
    """
    print(f"正在将视频转换为音频...")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",  # 不处理视频
        "-acodec", "libmp3lame",
        "-q:a", "2",
        audio_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"音频已提取: {audio_path}")
        return audio_path
    else:
        print(f"音频提取失败: {result.stderr}")
        raise Exception("视频转音频失败")


# ============ 转录相关函数 ============
def get_duration(file_path: str) -> float:
    """获取媒体文件时长"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def transcribe_audio(audio_path: str, model_name: str = MODEL_NAME, language: str = LANGUAGE):
    """
    转录音频文件

    Args:
        audio_path: 音频文件路径
        model_name: Whisper 模型名称
        language: 语言代码

    Returns:
        list: 转录结果列表 [{start, end, text}, ...]
    """
    print(f"正在加载模型: {model_name}...")
    model = WhisperModel(model_name, device="cuda", compute_type="float16")

    total_duration = get_duration(audio_path)
    print(f"开始转录: {audio_path}")
    print(f"总时长: {total_duration:.2f} 秒")

    segments, info = model.transcribe(
        audio_path,
        language=language,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        beam_size=5
    )

    print(f"检测语言: {info.language} (概率: {getattr(info, 'language_probability', None):.2%})")

    results = []
    pbar = tqdm(total=total_duration, unit="sec", desc="转录进度")

    for s in segments:
        results.append({
            "start": round(s.start, 2),
            "end": round(s.end, 2),
            "text": s.text.strip()
        })
        pbar.update(s.end - pbar.n)

    pbar.close()
    return results


def merge_by_count(segments: list[dict], group_size: int = 8, sep: str = " ") -> list[dict]:
    """
    将转录结果按数量合并成段落

    Args:
        segments: 转录结果列表
        group_size: 每多少句合并成一个段落
        sep: 文本分隔符

    Returns:
        list: 合并后的段落列表
    """
    merged = []
    buf = []

    for seg in segments:
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue

        buf.append({
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": txt
        })

        if len(buf) >= group_size:
            merged.append({
                "start": round(buf[0]["start"], 2),
                "end": round(buf[-1]["end"], 2),
                "text": sep.join(x["text"] for x in buf)
            })
            buf = []

    if buf:
        merged.append({
            "start": round(buf[0]["start"], 2),
            "end": round(buf[-1]["end"], 2),
            "text": sep.join(x["text"] for x in buf)
        })

    return merged


# ============ API 分析相关函数 ============
def analyze_highlights(merged_segments: list[dict]) -> list[dict]:
    """
    调用 API 分析爆点

    Args:
        merged_segments: 合并后的段落列表

    Returns:
        list: 爆点列表 [{start, end, title, reason}, ...]
    """
    client = get_api_client()

    # 构建提示文本
    segments_text = "\n".join([
        f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}"
        for seg in merged_segments
    ])

    print("\n正在分析爆点...")

    response = client.chat.completions.create(
        model="glm-5",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是视频转录文本：\n\n{segments_text}"}
        ],
        temperature=0.7
    )

    result_text = response.choices[0].message.content

    # 解析 JSON 结果
    try:
        # 尝试提取 JSON 数组
        import re
        json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
        if json_match:
            highlights = json.loads(json_match.group())
        else:
            highlights = json.loads(result_text)

        print(f"分析完成，找到 {len(highlights)} 个爆点")
        return highlights

    except json.JSONDecodeError as e:
        print(f"解析 API 返回结果失败: {e}")
        print(f"原始返回: {result_text}")
        return []


# ============ 视频裁剪相关函数 ============
def clip_video(video_path: str, start: float, end: float, output_path: str):
    """
    使用 ffmpeg 裁剪视频片段

    Args:
        video_path: 源视频路径
        start: 开始时间（秒）
        end: 结束时间（秒）
        output_path: 输出路径
    """
    duration = end - start

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ss", str(start),
        "-t", str(duration),
        "-c", "copy",
        output_path
    ]

    print(f"正在裁剪: {start:.2f}s -> {end:.2f}s")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"已保存: {output_path}")
    else:
        print(f"裁剪失败: {result.stderr}")


def process_video(video_path: str, output_dir: str, group_size: int):
    """
    完整处理流程：视频转音频 -> 转录 -> 分析 -> 裁剪

    Args:
        video_path: 视频/音频文件路径
        output_dir: 输出目录
        group_size: 每多少句合并成一个段落（方便可视化）
    """
    os.makedirs(output_dir, exist_ok=True)

    # 判断输入类型，并提取音频
    original_video_path = None

    if is_video(video_path):
        # 如果是视频，先转换为音频
        print("=" * 50)
        print("步骤 0: 视频转音频")
        print("=" * 50)
        audio_path = os.path.join(output_dir, "audio_extract.mp3")
        video_to_audio(video_path, audio_path)
        audio_for_transcribe = audio_path
        original_video_path = video_path  # 保存原始视频用于裁剪
    else:
        # 已经是音频文件
        audio_for_transcribe = video_path
        original_video_path = video_path

    # 1. 转录
    print("=" * 50)
    print("步骤 1: 语音转录")
    print("=" * 50)
    transcription_results = transcribe_audio(audio_for_transcribe)

    # 保存原始转录结果
    transcription_path = os.path.join(output_dir, "transcription_raw.json")
    with open(transcription_path, "w", encoding="utf-8") as f:
        json.dump(transcription_results, f, ensure_ascii=False, indent=2)
    print(f"原始转录结果已保存: {transcription_path}")

    # 2. 合并段落
    merged_segments = merge_by_count(transcription_results, group_size=group_size)
    print(f"合并后共 {len(merged_segments)} 个段落（每 {group_size} 句为一段）")

    # 保存合并后的转录
    merged_path = os.path.join(output_dir, "transcription_merged.json")
    with open(merged_path, "w", encoding="utf-8") as f:
        json.dump(merged_segments, f, ensure_ascii=False, indent=2)
    print(f"合并转录已保存: {merged_path}")

    # 3. 分析爆点
    print("\n" + "=" * 50)
    print("步骤 2: 分析爆点")
    print("=" * 50)
    highlights = analyze_highlights(transcription_results)

    if not highlights:
        print("未找到爆点，取消裁剪")
        return

    # 保存爆点分析结果
    highlights_path = os.path.join(output_dir, "highlights.json")
    with open(highlights_path, "w", encoding="utf-8") as f:
        json.dump(highlights, f, ensure_ascii=False, indent=2)
    print(f"爆点分析已保存: {highlights_path}")

    # 4. 裁剪视频
    print("\n" + "=" * 50)
    print("步骤 3: 裁剪视频片段")
    print("=" * 50)

    for i, highlight in enumerate(highlights, 1):
        start = highlight["start"]
        end = highlight["end"]
        title = highlight.get("title", f"clip_{i}")

        # 清理文件名
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:30]
        output_path = os.path.join(output_dir, f"clip_{i}_{safe_title}.mp4")

        # 使用原始视频路径进行裁剪
        clip_video(original_video_path, start, end, output_path)

    print("\n" + "=" * 50)
    print("处理完成!")
    print("=" * 50)


# ============ 主程序 ============
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="视频爆点提取脚本 - 从视频中提取精彩片段",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py -v video.mp4
  python main.py -v video.mp4 -o ./output
  python main.py -v video.mp4 -o ./output -g 10

输出文件:
  - audio_extract.mp3: 提取的音频
  - transcription_raw.json: 原始转录
  - transcription_merged.json: 合并后的转录
  - highlights.json: 爆点分析结果
  - clip_*.mp4: 裁剪后的视频片段
        """
    )

    parser.add_argument(
        "-v", "--video",
        required=True,
        help="输入视频文件路径（必需）"
    )

    parser.add_argument(
        "-o", "--output",
        default="./output",
        help="输出目录（默认: ./output）"
    )

    parser.add_argument(
        "-g", "--group",
        type=int,
        default=8,
        help="合并多少句为一段，方便可视化（默认: 8）"
    )

    args = parser.parse_args()

    # 检查视频文件是否存在
    if not os.path.exists(args.video):
        print(f"错误: 视频文件不存在: {args.video}")
        exit(1)

    print(f"视频文件: {args.video}")
    print(f"输出目录: {args.output}")
    print(f"分组大小: {args.group} 句/段")

    process_video(args.video, args.output, args.group)
