import asyncio
from typing import Optional, Dict
from fastapi import WebSocket
from tqdm import tqdm

from app.models import ProgressMessage


class ProgressTracker:
    """同时支持 tqdm 显示和 WebSocket 推送的进度追踪器"""

    STAGES = {
        "pending": (0, "等待处理"),
        "extracting_audio": (0, "提取音频"),
        "transcribing": (20, "语音转录"),
        "analyzing": (60, "AI 分析爆点"),
        "clipping": (80, "裁剪视频"),
        "completed": (100, "处理完成"),
        "failed": (-1, "处理失败"),
    }

    def __init__(self, total: float, task_id: str, websocket: Optional[WebSocket] = None):
        self.total = total
        self.task_id = task_id
        self.websocket = websocket
        self.current = 0
        self.stage = "pending"
        self.status = "pending"
        self.message = "等待处理"
        # tqdm 用于本地控制台显示
        self.pbar = tqdm(total=total, desc="处理进度", unit="sec")

    def update(self, increment: float, stage: str, message: str = ""):
        """更新进度"""
        self.current += increment
        self.stage = stage
        self.status = "processing"
        self.message = message or f"{stage}"

        self.pbar.update(increment)
        self.pbar.set_description(f"{stage}: {message or f'{self.current:.0f}%'}")

        # WebSocket 推送
        if self.websocket:
            progress = int((self.current / self.total) * 100) if self.total > 0 else 0
            asyncio.create_task(self._send_websocket(progress, stage, message or f"{progress}%"))

    def set_progress(self, progress: int, stage: str, message: str = ""):
        """直接设置进度（0-100）"""
        self.stage = stage
        self.status = "processing"
        self.message = message

        self.pbar.set_description(f"{stage}: {message}")

        # WebSocket 推送
        if self.websocket:
            asyncio.create_task(self._send_websocket(progress, stage, message or f"{progress}%"))

    async def _send_websocket(self, progress: int, stage: str, message: str):
        """发送 WebSocket 消息"""
        try:
            if self.websocket:
                await self.websocket.send_json({
                    "task_id": self.task_id,
                    "status": self.status,
                    "progress": progress,
                    "stage": stage,
                    "message": message
                })
        except Exception as e:
            print(f"WebSocket 发送失败: {e}")

    def close(self):
        self.pbar.close()

    def complete(self, message: str = "处理完成"):
        """标记完成"""
        self.status = "completed"
        self.stage = "completed"
        self.message = message
        if self.websocket:
            asyncio.create_task(self._send_websocket(100, "completed", message))
        self.close()

    def fail(self, error: str):
        """标记失败"""
        self.status = "failed"
        self.stage = "failed"
        self.message = error
        if self.websocket:
            asyncio.create_task(self._send_websocket(-1, "failed", error))
        self.close()


class ProgressManager:
    """管理所有任务的进度追踪器"""

    def __init__(self):
        self._trackers: Dict[str, ProgressTracker] = {}

    def add_tracker(self, task_id: str, tracker: ProgressTracker):
        self._trackers[task_id] = tracker

    def get_tracker(self, task_id: str) -> Optional[ProgressTracker]:
        return self._trackers.get(task_id)

    def remove_tracker(self, task_id: str):
        if task_id in self._trackers:
            del self._trackers[task_id]


# 全局进度管理器
progress_manager = ProgressManager()
