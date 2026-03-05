import hashlib
import aiofiles
from pathlib import Path


async def calculate_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """计算文件 hash"""
    hash_obj = hashlib.new(algorithm)

    async with aiofiles.open(file_path, 'rb') as f:
        while chunk := await f.read(8192):
            hash_obj.update(chunk)

    return f"{algorithm}:{hash_obj.hexdigest()}"


def get_file_extension(filename: str) -> str:
    """获取文件扩展名"""
    return Path(filename).suffix.lower()


def is_video_file(filename: str) -> bool:
    """判断是否为视频文件"""
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm']
    return get_file_extension(filename) in video_extensions


def is_audio_file(filename: str) -> bool:
    """判断是否为音频文件"""
    audio_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg']
    return get_file_extension(filename) in audio_extensions


def safe_filename(filename: str) -> str:
    """生成安全的文件名"""
    import re
    # 替换不安全的字符
    safe = re.sub(r'[^\w\s.-]', '', filename)
    return safe.strip()
