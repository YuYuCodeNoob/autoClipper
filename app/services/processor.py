import json
import os
import subprocess
import re
import zipfile
import asyncio
from pathlib import Path
from typing import Optional
from threading import Lock
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

from faster_whisper import WhisperModel
from openai import OpenAI
from tqdm import tqdm

from app.config import API_KEY, API_URL, SYSTEM_PROMPT, MODEL_NAME
from app.services.task_manager import task_manager, TaskStatus


# ============ 消息队列（用于线程间通信）===========
class ProgressQueue:
    """进度消息队列"""
    _queues: dict = {}
    _lock = Lock()

    @classmethod
    def get_queue(cls, task_id: str) -> Queue:
        with cls._lock:
            if task_id not in cls._queues:
                cls._queues[task_id] = Queue()
            return cls._queues[task_id]

    @classmethod
    def put(cls, task_id: str, message: dict):
        cls.get_queue(task_id).put(message)

    @classmethod
    def get(cls, task_id: str, timeout: float = 0.5) -> Optional[dict]:
        try:
            return cls.get_queue(task_id).get(timeout=timeout)
        except:
            return None

    @classmethod
    def remove(cls, task_id: str):
        with cls._lock:
            if task_id in cls._queues:
                del cls._queues[task_id]


# ============ 模型懒加载（线程安全，线程内加载）===========
class LazyModel:
    """懒加载 Whisper 模型 - 在独立线程中加载"""
    _model: Optional[WhisperModel] = None
    _model_name: str = ""
    _lock = Lock()
    _loading = False
    _loaded_event = None  # 加载完成事件

    @classmethod
    def get_model(cls, model_name: str = MODEL_NAME, device: str = "cuda", compute_type: str = "float16", task_id: str = None):
        """获取模型（懒加载，在线程中加载）"""
        with cls._lock:
            if cls._model is not None and cls._model_name == model_name:
                return cls._model

            # 如果正在加载，等待加载完成
            if cls._loading:
                pass  # 继续等待

            # 标记开始加载
            cls._loading = True

        # 在独立线程中加载模型
        if task_id:
            ProgressQueue.put(task_id, {"progress": 22, "stage": "加载模型", "message": "首次加载模型中..."})

        print(f"[懒加载] 首次加载 Whisper 模型: {model_name}...")
        cls._model = WhisperModel(model_name, device=device, compute_type=compute_type)
        cls._model_name = model_name
        cls._loading = False
        print(f"[懒加载] 模型加载完成: {model_name}")

        if task_id:
            ProgressQueue.put(task_id, {"progress": 25, "stage": "加载模型", "message": "模型加载完成"})

        return cls._model

    @classmethod
    def get_model_async(cls, model_name: str = MODEL_NAME, device: str = "cuda", compute_type: str = "float16", task_id: str = None):
        """异步获取模型（在后台线程中加载）"""
        # 如果已加载，直接返回
        if cls._model is not None and cls._model_name == model_name:
            return cls._model

        with cls._lock:
            if cls._loading:
                # 正在加载中，不需要重复触发
                pass
            else:
                cls._loading = True

        # 使用线程池加载模型
        def load_in_thread():
            if task_id:
                ProgressQueue.put(task_id, {"progress": 22, "stage": "加载模型", "message": "首次加载模型中..."})

            print(f"[懒加载] 首次加载 Whisper 模型: {model_name}...")
            model = WhisperModel(model_name, device=device, compute_type=compute_type)

            with cls._lock:
                cls._model = model
                cls._model_name = model_name
                cls._loading = False

            print(f"[懒加载] 模型加载完成: {model_name}")

            if task_id:
                ProgressQueue.put(task_id, {"progress": 25, "stage": "加载模型", "message": "模型加载完成"})

            return model

        # 提交到全局线程池
        return _model_loader_executor.submit(load_in_thread).result()

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._model is not None

    @classmethod
    def get_model_name(cls) -> str:
        return cls._model_name


# 全局线程池
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="video_processor_")
_model_loader_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model_loader_")
_analyze_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analyze_")


# ============ 工具函数 ============
def is_video(file_path: str) -> bool:
    """判断文件是否为视频"""
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm']
    ext = os.path.splitext(file_path)[1].lower()
    return ext in video_extensions


def get_duration(file_path: str) -> float:
    """获取媒体文件时长"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def video_to_audio(video_path: str, audio_path: str, task_id: str = None):
    """使用 ffmpeg 将视频转换为音频"""
    print(f"正在将视频转换为音频...")
    ProgressQueue.put(task_id, {"progress": 5, "stage": "提取音频", "message": "正在提取音频..."})

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "libmp3lame",
        "-q:a", "2",
        audio_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"音频已提取: {audio_path}")
        ProgressQueue.put(task_id, {"progress": 20, "stage": "提取音频", "message": "音频提取完成"})
        return audio_path
    else:
        print(f"音频提取失败: {result.stderr}")
        raise Exception("视频转音频失败")


def transcribe_audio(
    audio_path: str,
    task_id: str = None,
    model_name: str = MODEL_NAME,
    language: str = "zh"
) -> list:
    """转录音频文件 - 懒加载模型（在独立线程中加载）"""
    # 懒加载模型（首次调用时在独立线程中加载）
    model = LazyModel.get_model_async(model_name, task_id=task_id)

    ProgressQueue.put(task_id, {"progress": 28, "stage": "转录中", "message": "开始转录..."})

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

    print(f"检测语言: {info.language}")

    results = []
    pbar = tqdm(total=total_duration, unit="sec", desc="转录进度")

    for s in segments:
        results.append({
            "start": round(s.start, 2),
            "end": round(s.end, 2),
            "text": s.text.strip()
        })
        pbar.update(s.end - pbar.n)

        # 推送进度
        prog = int((s.end / total_duration) * 40) + 30  # 30-70%
        ProgressQueue.put(task_id, {
            "progress": prog,
            "stage": "转录中",
            "message": f"转录中 {s.end:.0f}s/{total_duration:.0f}s"
        })

    pbar.close()

    ProgressQueue.put(task_id, {"progress": 60, "stage": "转录完成", "message": "转录完成"})

    return results


def merge_by_count(segments: list, group_size: int = 8, sep: str = " ") -> list:
    """将转录结果按数量合并成段落"""
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


def analyze_highlights(merged_segments: list, task_id: str = None) -> list:
    """调用 API 分析爆点 - 在独立线程中运行"""
    ProgressQueue.put(task_id, {"progress": 65, "stage": "AI分析中", "message": "准备分析爆点..."})

    # 获取当前事件循环，在子线程中创建新的
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # 在线程池中运行异步 API 调用
        highlights = loop.run_until_complete(_analyze_async(merged_segments, task_id))
        return highlights
    finally:
        loop.close()


async def _analyze_async(merged_segments: list, task_id: str = None):
    """异步调用 AI API 分析爆点"""
    ProgressQueue.put(task_id, {"progress": 68, "stage": "AI分析中", "message": "正在调用 AI 分析..."})

    client = OpenAI(api_key=API_KEY, base_url=API_URL)

    # 构建提示文本
    segments_text = "\n".join([
        f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}"
        for seg in merged_segments
    ])

    print("\n正在分析爆点...")

    # 模拟进度推送（API 调用过程中）
    ProgressQueue.put(task_id, {"progress": 70, "stage": "AI分析中", "message": "AI 正在分析内容..."})

    response = client.chat.completions.create(
        model="glm-5",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是视频转录文本：\n\n{segments_text}"}
        ],
        temperature=0.7
    )

    ProgressQueue.put(task_id, {"progress": 75, "stage": "AI分析中", "message": "AI 分析完成，解析结果..."})

    result_text = response.choices[0].message.content

    # 解析 JSON 结果
    try:
        json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
        if json_match:
            highlights = json.loads(json_match.group())
        else:
            highlights = json.loads(result_text)

        print(f"分析完成，找到 {len(highlights)} 个爆点")
        ProgressQueue.put(task_id, {"progress": 78, "stage": "AI分析完成", "message": f"找到 {len(highlights)} 个爆点"})
        return highlights

    except json.JSONDecodeError as e:
        print(f"解析 API 返回结果失败: {e}")
        return []


def analyze_highlights_in_thread(merged_segments: list, task_id: str = None) -> list:
    """在独立线程中分析爆点"""
    return _analyze_executor.submit(analyze_highlights, merged_segments, task_id).result()


def clip_video(video_path: str, start: float, end: float, output_path: str):
    """使用 ffmpeg 裁剪视频片段"""
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


def process_video_task_sync(task_id: str):
    """同步处理视频任务（在后台线程中运行）"""
    task = task_manager.get_task(task_id)
    if not task:
        print(f"任务 {task_id} 不存在")
        return

    output_dir = task.output_dir
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 更新任务状态
        task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 0, "提取音频", "开始处理...")

        # 判断输入类型，并提取音频
        original_video_path = task.file_path

        if is_video(task.file_path):
            print("=" * 50)
            print("步骤 0: 视频转音频")
            print("=" * 50)
            audio_path = os.path.join(output_dir, "audio_extract.mp3")
            video_to_audio(task.file_path, audio_path, task_id)
            audio_for_transcribe = audio_path
        else:
            audio_for_transcribe = task.file_path

        # 1. 转录（模型会在独立线程中加载）
        print("=" * 50)
        print("步骤 1: 语音转录")
        print("=" * 50)

        transcription_results = transcribe_audio(
            audio_for_transcribe,
            task_id=task_id,
            model_name=task.model_name,
            language=task.language
        )

        # 保存原始转录结果
        transcription_path = os.path.join(output_dir, "transcription_raw.json")
        with open(transcription_path, "w", encoding="utf-8") as f:
            json.dump(transcription_results, f, ensure_ascii=False, indent=2)

        # 2. 合并段落
        merged_segments = merge_by_count(transcription_results, group_size=task.group_size)

        # 保存合并后的转录
        merged_path = os.path.join(output_dir, "transcription_merged.json")
        with open(merged_path, "w", encoding="utf-8") as f:
            json.dump(merged_segments, f, ensure_ascii=False, indent=2)

        # 3. 分析爆点 - 使用独立线程池
        print("\n" + "=" * 50)
        print("步骤 2: 分析爆点")
        print("=" * 50)

        highlights = analyze_highlights_in_thread(transcription_results, task_id)

        if not highlights:
            print("未找到爆点，取消裁剪")
            task_manager.update_task_status(task_id, TaskStatus.FAILED, -1, "分析失败", "未找到爆点")
            ProgressQueue.put(task_id, {"progress": -1, "stage": "failed", "message": "未找到爆点"})
            ProgressQueue.remove(task_id)
            return

        # 保存爆点分析结果
        highlights_path = os.path.join(output_dir, "highlights.json")
        with open(highlights_path, "w", encoding="utf-8") as f:
            json.dump(highlights, f, ensure_ascii=False, indent=2)

        # 4. 裁剪视频
        print("\n" + "=" * 50)
        print("步骤 3: 裁剪视频片段")
        print("=" * 50)

        total_clips = len(highlights)
        for i, highlight in enumerate(highlights, 1):
            start = highlight["start"]
            end = highlight["end"]
            title = highlight.get("title", f"clip_{i}")

            safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:30]
            output_path = os.path.join(output_dir, f"clip_{i}_{safe_title}.mp4")

            clip_video(original_video_path, start, end, output_path)

            # 更新进度
            prog = 80 + int((i / total_clips) * 15)  # 80-95%
            ProgressQueue.put(task_id, {
                "progress": prog,
                "stage": "裁剪中",
                "message": f"裁剪第 {i}/{total_clips} 个片段"
            })

        # 创建 ZIP 包
        print("\n" + "=" * 50)
        print("步骤 4: 打包结果")
        print("=" * 50)

        zip_path = os.path.join(output_dir, "clips.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in output_dir.glob("clip_*.mp4"):
                zipf.write(file, file.name)

        result_files = [str(f) for f in output_dir.glob("clip_*.mp4")]
        task_manager.set_task_result(task_id, result_files)

        print("\n" + "=" * 50)
        print("处理完成!")
        print("=" * 50)

        task_manager.update_task_status(task_id, TaskStatus.COMPLETED, 100, "完成", "处理完成")
        ProgressQueue.put(task_id, {"progress": 100, "stage": "completed", "message": "处理完成"})
        ProgressQueue.remove(task_id)

    except Exception as e:
        print(f"处理失败: {e}")
        task_manager.update_task_status(task_id, TaskStatus.FAILED, -1, "处理失败", str(e))
        ProgressQueue.put(task_id, {"progress": -1, "stage": "failed", "message": str(e)})
        ProgressQueue.remove(task_id)


def process_video_task_background(task_id: str):
    """后台线程处理入口"""
    process_video_task_sync(task_id)
