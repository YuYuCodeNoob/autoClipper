from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.task_manager import task_manager, TaskStatus

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{task_id}/clips.zip")
async def download_result(task_id: str):
    """下载处理结果 ZIP 文件"""
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务尚未完成")

    zip_path = task.output_dir / "clips.zip"

    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")

    return FileResponse(
        path=str(zip_path),
        filename=f"clips_{task_id}.zip",
        media_type="application/zip"
    )


@router.get("/{task_id}/{filename}")
async def download_file(task_id: str, filename: str):
    """下载单个结果文件"""
    task = task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    file_path = task.output_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        path=str(file_path),
        filename=filename
    )
