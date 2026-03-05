from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from app.config import HOST, PORT
from app.routes import tasks, files
from app.services.task_manager import task_manager, TaskStatus
from app.services.processor import ProgressQueue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print(f"服务启动: http://{HOST}:{PORT}")
    print("使用懒加载模型（首次请求时加载）")
    yield


app = FastAPI(
    title="视频爆点提取服务",
    description="FastAPI 视频爆点提取服务，供 SpringBoot 内网调用",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(tasks.router)
app.include_router(files.router)


@app.get("/health")
async def health_check():
    """健康检查"""
    from app.services.processor import LazyModel
    return {
        "status": "healthy",
        "service": "video-highlight-extractor",
        "model_loaded": LazyModel.is_loaded(),
        "model_name": LazyModel.get_model_name()
    }


@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket 实时进度推送 - 通过队列非阻塞获取进度"""
    await websocket.accept()

    # 验证任务是否存在
    task = task_manager.get_task(task_id)
    if not task:
        await websocket.send_json({
            "task_id": task_id,
            "status": "failed",
            "progress": -1,
            "stage": "error",
            "message": "任务不存在"
        })
        await websocket.close()
        return

    # 发送初始状态
    await websocket.send_json({
        "task_id": task_id,
        "status": task.status.value,
        "progress": task.progress,
        "stage": task.stage,
        "message": task.message
    })

    try:
        # 通过队列监听进度（非阻塞）
        while task.status == TaskStatus.PROCESSING:
            # 从队列获取进度消息
            msg = ProgressQueue.get(task_id, timeout=0.5)

            if msg:
                await websocket.send_json({
                    "task_id": task_id,
                    "status": "processing",
                    "progress": msg.get("progress", 0),
                    "stage": msg.get("stage", ""),
                    "message": msg.get("message", "")
                })

            # 重新获取任务状态
            task = task_manager.get_task(task_id)
            if not task:
                break

        # 发送最终状态
        if task:
            final_msg = {
                "task_id": task_id,
                "status": task.status.value,
                "progress": task.progress,
                "stage": task.stage,
                "message": task.message
            }
            if task.status == TaskStatus.COMPLETED:
                final_msg["result_url"] = f"/api/files/{task_id}/clips.zip"
            await websocket.send_json(final_msg)

    except WebSocketDisconnect:
        print(f"WebSocket 断开: {task_id}")
    except Exception as e:
        print(f"WebSocket 错误: {e}")
        try:
            await websocket.send_json({
                "task_id": task_id,
                "status": "failed",
                "progress": -1,
                "stage": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        await websocket.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
