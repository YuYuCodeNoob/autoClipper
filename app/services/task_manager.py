import uuid
import os
import hashlib
from typing import Optional, Dict, List
from datetime import datetime
from pathlib import Path
from enum import Enum

from app.config import UPLOAD_DIR, OUTPUT_DIR


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    """任务模型"""

    def __init__(
        self,
        task_id: str,
        file_path: str,
        file_hash: str,
        model_name: str = "small",
        language: str = "zh",
        group_size: int = 8,
    ):
        self.task_id = task_id
        self.file_path = file_path
        self.file_hash = file_hash
        self.model_name = model_name
        self.language = language
        self.group_size = group_size
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.stage = "等待处理"
        self.message = ""
        self.error = None
        self.created_at = datetime.now()
        self.completed_at = None
        self.output_dir = OUTPUT_DIR / task_id
        self.result_files = []

    def to_dict(self, base_url: str = "") -> dict:
        """转换为字典"""
        result = {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
        }

        if self.status == TaskStatus.COMPLETED:
            result["result_url"] = f"{base_url}/api/files/{self.task_id}/clips.zip" if base_url else None

        if self.error:
            result["error"] = self.error

        return result


class TaskManager:
    """任务管理器"""

    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._hash_map: Dict[str, str] = {}  # file_hash -> task_id

    def create_task(
        self,
        file_path: str,
        file_hash: str,
        model_name: str = "small",
        language: str = "zh",
        group_size: int = 8,
    ) -> Task:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            file_path=file_path,
            file_hash=file_hash,
            model_name=model_name,
            language=language,
            group_size=group_size,
        )
        self._tasks[task_id] = task
        # 存储 hash 映射（简化版：直接存任务ID，实际可存储更复杂信息）
        hash_key = file_hash.split(":")[-1] if ":" in file_hash else file_hash
        self._hash_map[hash_key] = task_id
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self._tasks.get(task_id)

    def get_task_by_hash(self, file_hash: str) -> Optional[Task]:
        """通过 hash 获取任务"""
        hash_key = file_hash.split(":")[-1] if ":" in file_hash else file_hash
        task_id = self._hash_map.get(hash_key)
        if task_id:
            return self._tasks.get(task_id)
        return None

    def get_all_tasks(self, limit: int = 50, offset: int = 0) -> List[Task]:
        """获取所有任务（分页）"""
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return tasks[offset:offset + limit]

    def get_tasks_count(self) -> int:
        """获取任务总数"""
        return len(self._tasks)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: int = 0,
        stage: str = "",
        message: str = "",
        error: str = None,
    ):
        """更新任务状态"""
        task = self._tasks.get(task_id)
        if task:
            task.status = status
            task.progress = progress
            task.stage = stage
            task.message = message
            if error:
                task.error = error
            if status == TaskStatus.COMPLETED:
                task.completed_at = datetime.now()

    def set_task_result(self, task_id: str, result_files: list):
        """设置任务结果文件"""
        task = self._tasks.get(task_id)
        if task:
            task.result_files = result_files

    def delete_task(self, task_id: str):
        """删除任务"""
        task = self._tasks.get(task_id)
        if task:
            # 清理文件
            if task.file_path and os.path.exists(task.file_path):
                try:
                    os.remove(task.file_path)
                except Exception:
                    pass
            if task.output_dir and os.path.exists(task.output_dir):
                try:
                    import shutil
                    shutil.rmtree(task.output_dir)
                except Exception:
                    pass
            # 移除 hash 映射
            hash_key = task.file_hash.split(":")[-1] if ":" in task.file_hash else task.file_hash
            self._hash_map.pop(hash_key, None)
            del self._tasks[task_id]


# 全局任务管理器
task_manager = TaskManager()
