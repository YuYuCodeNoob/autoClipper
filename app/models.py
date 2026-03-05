from pydantic import BaseModel
from typing import Optional, List, Literal


class TaskCheckRequest(BaseModel):
    """校验 hash 请求"""
    file_hash: str  # 格式: "sha256:xxxxxx"


class TaskCheckResponse(BaseModel):
    """校验 hash 响应"""
    exists: bool
    task_id: Optional[str] = None
    status: Optional[Literal["pending", "processing", "completed", "failed"]] = None
    result_url: Optional[str] = None
    upload_url: Optional[str] = None


class TaskCreateRequest(BaseModel):
    """创建任务请求"""
    model_name: str = "small"
    language: str = "zh"
    group_size: int = 8


class TaskCreateResponse(BaseModel):
    """创建任务响应"""
    task_id: str
    status: Literal["pending", "processing"]
    ws_url: str


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: Optional[int] = None
    stage: Optional[str] = None
    message: Optional[str] = None
    result_url: Optional[str] = None
    error: Optional[str] = None


class ProgressMessage(BaseModel):
    """WebSocket 进度消息"""
    task_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: int
    stage: str
    message: str
