import os
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Query
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.models import (
    TaskCheckRequest,
    TaskCheckResponse,
    TaskCreateResponse,
    TaskStatusResponse,
)
from app.config import UPLOAD_DIR
from app.services.task_manager import task_manager, TaskStatus
from app.services.processor import process_video_task_background
from app.utils.file_utils import calculate_file_hash

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# 后台线程池
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="task_processor_")


@router.get("/list")
async def list_tasks(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取任务列表（分页）"""
    tasks = task_manager.get_all_tasks(limit=limit, offset=offset)
    total = task_manager.get_tasks_count()

    base_url = ""
    if request:
        base_url = f"{request.url.scheme}://{request.url.hostname}"

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "tasks": [task.to_dict(base_url) for task in tasks]
    }


@router.post("/check", response_model=TaskCheckResponse)
async def check_task_hash(request: TaskCheckRequest):
    """校验 hash 是否存在，返回已有任务或允许提交"""
    # 查找是否有已完成的任务
    existing_task = task_manager.get_task_by_hash(request.file_hash)

    if existing_task and existing_task.status == TaskStatus.COMPLETED:
        return TaskCheckResponse(
            exists=True,
            task_id=existing_task.task_id,
            status="completed",
            result_url=f"/api/files/{existing_task.task_id}/clips.zip"
        )

    # 如果任务存在但未完成，也返回已存在
    if existing_task:
        return TaskCheckResponse(
            exists=True,
            task_id=existing_task.task_id,
            status=existing_task.status.value
        )

    return TaskCheckResponse(
        exists=False,
        upload_url="/api/tasks"
    )


@router.post("", response_model=TaskCreateResponse)
async def create_task(
    request: Request,
    file: UploadFile = File(...),
    model_name: str = "small",
    language: str = "zh",
    group_size: int = 8,
):
    """提交新任务 - 使用后台线程处理，不阻塞主线程"""
    # 保存上传的文件
    file_path = UPLOAD_DIR / file.filename
    content = await file.read()

    # 检查文件是否为空
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")

    with open(file_path, "wb") as f:
        f.write(content)

    # 计算文件 hash
    file_hash = await calculate_file_hash(str(file_path))

    # 创建任务
    task = task_manager.create_task(
        file_path=str(file_path),
        file_hash=file_hash,
        model_name=model_name,
        language=language,
        group_size=group_size,
    )

    # 获取 host 构建 WebSocket URL
    host = request.url.hostname or "localhost"
    ws_url = f"ws://{host}/ws/{task.task_id}"

    # 使用后台线程处理任务，不阻塞主线程
    _executor.submit(process_video_task_background, task.task_id)

    return TaskCreateResponse(
        task_id=task.task_id,
        status="processing",
        ws_url=ws_url
    )


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str, request: Request = None):
    """查询任务状态"""
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    base_url = ""
    if request:
        base_url = f"{request.url.scheme}://{request.url.hostname}"

    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status.value,
        progress=task.progress,
        stage=task.stage,
        message=task.message,
        result_url=f"{base_url}/api/files/{task.task_id}/clips.zip" if task.status == TaskStatus.COMPLETED else None,
        error=task.error
    )


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_manager.delete_task(task_id)

    return {"message": "任务已删除"}
