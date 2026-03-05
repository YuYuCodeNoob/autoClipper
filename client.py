#!/usr/bin/env python3
"""
交互式测试客户端 - 用于测试 FastAPI 视频爆点提取服务
"""
import os
import sys
import json
import hashlib
import asyncio
import websockets
import requests
from pathlib import Path

# 配置
API_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"


def calculate_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """计算文件 hash"""
    hash_obj = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            hash_obj.update(chunk)
    return f"{algorithm}:{hash_obj.hexdigest()}"


def check_health():
    """检查服务健康状态"""
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        data = resp.json()
        print(f"\n{'='*50}")
        print("服务状态:")
        print(f"  状态: {data.get('status')}")
        print(f"  模型已加载: {data.get('model_loaded')}")
        print(f"  模型名称: {data.get('model_name')}")
        print(f"{'='*50}\n")
        return True
    except Exception as e:
        print(f"服务连接失败: {e}")
        return False


def check_hash(file_hash: str):
    """检查文件 hash 是否已存在"""
    print(f"\n检查 hash: {file_hash}")
    resp = requests.post(
        f"{API_BASE}/api/tasks/check",
        json={"file_hash": file_hash},
        timeout=10
    )
    data = resp.json()
    print(f"  exists: {data.get('exists')}")
    if data.get('exists'):
        print(f"  task_id: {data.get('task_id')}")
        print(f"  status: {data.get('status')}")
        if data.get('result_url'):
            print(f"  result_url: {data.get('result_url')}")
    else:
        print(f"  upload_url: {data.get('upload_url')}")
    return data


def upload_video(video_path: str, model_name: str = "small", language: str = "zh", group_size: int = 8):
    """上传视频文件"""
    if not os.path.exists(video_path):
        print(f"文件不存在: {video_path}")
        return None

    print(f"\n上传视频: {video_path}")
    print(f"  模型: {model_name}, 语言: {language}, 分组: {group_size}")

    with open(video_path, 'rb') as f:
        files = {'file': (os.path.basename(video_path), f, 'video/mp4')}
        data = {
            'model_name': model_name,
            'language': language,
            'group_size': group_size
        }
        resp = requests.post(
            f"{API_BASE}/api/tasks",
            files=files,
            data=data,
            timeout=60
        )

    if resp.status_code != 200:
        print(f"上传失败: {resp.text}")
        return None

    data = resp.json()
    print(f"  task_id: {data.get('task_id')}")
    print(f"  status: {data.get('status')}")
    print(f"  ws_url: {data.get('ws_url')}")
    return data


def get_task_status(task_id: str):
    """查询任务状态"""
    resp = requests.get(f"{API_BASE}/api/tasks/{task_id}", timeout=10)
    if resp.status_code == 404:
        print("任务不存在")
        return None
    data = resp.json()
    print(f"\n任务状态: {task_id}")
    print(f"  status: {data.get('status')}")
    print(f"  progress: {data.get('progress')}")
    print(f"  stage: {data.get('stage')}")
    print(f"  message: {data.get('message')}")
    if data.get('result_url'):
        print(f"  result_url: {data.get('result_url')}")
    if data.get('error'):
        print(f"  error: {data.get('error')}")
    return data


async def listen_progress(task_id: str):
    """监听 WebSocket 进度"""
    ws_url = f"{WS_BASE}/ws/{task_id}"
    print(f"\n连接 WebSocket: {ws_url}")

    try:
        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                data = json.loads(message)
                print(f"\n[{data.get('stage')}] {data.get('message')}")
                print(f"  进度: {data.get('progress')}%")

                if data.get('status') in ['completed', 'failed']:
                    if data.get('result_url'):
                        print(f"\n结果下载: {data.get('result_url')}")
                    break
    except Exception as e:
        print(f"WebSocket 错误: {e}")


def download_result(task_id: str, output_path: str = None):
    """下载结果文件"""
    url = f"{API_BASE}/api/files/{task_id}/clips.zip"
    output_path = output_path or f"clips_{task_id}.zip"

    print(f"\n下载结果: {url}")
    resp = requests.get(url, timeout=60)

    if resp.status_code != 200:
        print(f"下载失败: {resp.text}")
        return False

    with open(output_path, 'wb') as f:
        f.write(resp.content)
    print(f"已保存到: {output_path}")
    return True


def interactive_mode():
    """交互式模式"""
    print("\n" + "="*60)
    print("视频爆点提取服务 - 交互式测试客户端")
    print("="*60)

    # 检查服务健康
    if not check_health():
        return

    while True:
        print("\n选择操作:")
        print("  1. 上传视频并处理")
        print("  2. 检查文件 hash")
        print("  3. 查询任务状态")
        print("  4. 监听任务进度")
        print("  5. 下载结果")
        print("  0. 退出")

        choice = input("\n请选择 [0-5]: ").strip()

        if choice == '0':
            print("再见!")
            break

        elif choice == '1':
            video_path = input("视频路径: ").strip()
            if not video_path:
                continue

            # 先计算 hash
            file_hash = calculate_file_hash(video_path)
            result = check_hash(file_hash)

            if result.get('exists'):
                if result.get('status') == 'completed':
                    print("该文件已处理完成，是否重新处理? [y/N]: ", end="")
                    if input().strip().lower() != 'y':
                        continue
                else:
                    print(f"任务 {result.get('task_id')} 正在处理中")
                    continue

            # 上传文件
            task_info = upload_video(video_path)
            if task_info:
                task_id = task_info.get('task_id')
                print(f"\n任务已创建: {task_id}")

                # 监听进度
                asyncio.run(listen_progress(task_id))

        elif choice == '2':
            file_path = input("文件路径: ").strip()
            if file_path:
                file_hash = calculate_file_hash(file_path)
                check_hash(file_hash)

        elif choice == '3':
            task_id = input("任务ID: ").strip()
            if task_id:
                get_task_status(task_id)

        elif choice == '4':
            task_id = input("任务ID: ").strip()
            if task_id:
                asyncio.run(listen_progress(task_id))

        elif choice == '5':
            task_id = input("任务ID: ").strip()
            output_path = input("保存路径 (可选): ").strip() or None
            if task_id:
                download_result(task_id, output_path)

        else:
            print("无效选择")


if __name__ == "__main__":
    interactive_mode()
