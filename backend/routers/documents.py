"""
文档管理路由 - PDF 解析和向量存储 (集成 RustFS)
"""
import os
import sys
import uuid
import shutil
import json
import asyncio
import re
import zipfile
import io
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from core.database import get_db
from core.storage import StorageRecord, FileType, FileStatus
from services.rustfs_storage import get_rustfs_storage


def get_temp_dir() -> Path:
    """获取临时目录路径 - 优先使用环境变量 TEMP_DIR"""
    temp_dir_env = os.getenv('TEMP_DIR')
    if temp_dir_env:
        temp_path = Path(temp_dir_env)
    else:
        # 默认使用用户可写目录
        if os.name == 'nt':  # Windows
            base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
        elif os.uname().sysname == 'Darwin':  # macOS
            base_dir = Path.home() / 'Library' / 'Application Support'
        else:  # Linux
            base_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
        temp_path = base_dir / 'Uverse' / 'temp'
    
    temp_path.mkdir(parents=True, exist_ok=True)
    return temp_path

# 导入 PDF 解析服务
try:
    from services.pdf_parser import get_pdf_parser
    from core.parse_file_logger import get_parse_file_logger
    MINERU_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] PDF 解析服务不可用: {e}")
    MINERU_AVAILABLE = False

# 导入 Word 解析服务
try:
    from services.word_parser import get_word_parser
    WORD_PARSER_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Word 解析服务不可用: {e}")
    WORD_PARSER_AVAILABLE = False

# 导入 TXT/CSV 解析服务
try:
    from services.text_parser import get_text_parser
    TEXT_PARSER_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] 文本解析服务不可用: {e}")
    TEXT_PARSER_AVAILABLE = False

router = APIRouter()

# 解析任务存储（生产环境应使用 Redis 等）
parse_tasks = {}

# 活跃的后台任务集合，防止被垃圾回收
_active_tasks = set()

# 任务取消标志字典：task_id -> asyncio.Event
_cancel_events = {}


def _check_and_fix_processing_status(record: StorageRecord) -> bool:
    """
    检查并修复异常的处理中状态
    
    如果文件状态为 PROCESSING 但找不到对应的解析任务（可能由于服务重启），
    将状态改为 PENDING，允许重新解析。
    
    Args:
        record: 文件记录
        
    Returns:
        bool: 如果状态被修复返回 True，否则返回 False
    """
    if record.status != FileStatus.PROCESSING:
        return False
    
    # 检查是否有对应的解析任务
    # 使用 doc_id 或 record.id 作为 task_id 检查
    task_exists = False
    if record.doc_id and record.doc_id in parse_tasks:
        task_exists = True
    if str(record.id) in parse_tasks:
        task_exists = True
    
    if not task_exists:
        # 没有找到对应的解析任务，状态异常，改为 PENDING
        print(f"[StatusFix] 文件 {record.id} ({record.filename}) 状态为 PROCESSING 但找不到对应任务，改为 PENDING")
        record.status = FileStatus.PENDING
        return True
    
    return False

class ParseStatus(BaseModel):
    """解析状态模型"""
    task_id: str
    status: str
    filename: str
    total_pages: Optional[int] = None
    current_page: Optional[int] = None
    progress: int = 0
    message: str = ""
    output_file: Optional[str] = None
    error: Optional[str] = None


class StopParseResponse(BaseModel):
    """停止解析响应模型"""
    task_id: str
    status: str
    message: str


class FileInfo(BaseModel):
    """文件信息模型"""
    id: str
    filename: str
    file_type: str
    size: int
    bucket: str
    object_key: str
    s3_url: str
    status: str
    created_at: str
    doc_id: Optional[str] = None


class LogEntryResponse(BaseModel):
    """日志条目响应模型"""
    timestamp: str
    level: str
    message: str


def get_file_extension(filename: str) -> str:
    """获取文件扩展名（小写）"""
    return Path(filename).suffix.lower()

def is_pdf_file(filename: str) -> bool:
    """检查是否是 PDF 文件"""
    return get_file_extension(filename) == '.pdf'

def is_word_file(filename: str) -> bool:
    """检查是否是 Word 文件"""
    return get_file_extension(filename) == '.docx'

def is_text_file(filename: str) -> bool:
    """检查是否是 TXT 文件"""
    return get_file_extension(filename) == '.txt'

def is_csv_file(filename: str) -> bool:
    """检查是否是 CSV 文件"""
    return get_file_extension(filename) == '.csv'

def is_parseable_file(filename: str) -> bool:
    """检查文件是否支持解析（目前只有 PDF 需要解析）"""
    ext = get_file_extension(filename)
    return ext in ['.pdf']

def is_supported_file(filename: str) -> bool:
    """检查文件是否受支持（可以上传）"""
    ext = get_file_extension(filename)
    return ext in ['.pdf', '.docx', '.txt', '.csv']


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    上传文档到 RustFS 存储
    支持文件类型: PDF, Word (.docx), TXT, CSV
    """
    import time
    start_time = time.time()
    
    print(f"[Upload] 收到上传请求: {file.filename}")
    
    # 生成文档 ID
    doc_id = str(uuid.uuid4())[:8]
    
    # 检查文件类型
    filename_lower = file.filename.lower() if file.filename else ""
    
    print(f"[Upload] 文件名: {file.filename}, content_type: {file.content_type}")
    
    # 直接读取文件内容到内存
    try:
        content = await file.read()
        file_size = len(content)
        print(f"[Upload] 读取到文件内容: {file_size} bytes")
    except Exception as e:
        print(f"[Upload] 读取文件失败: {e}")
        import traceback
        print(f"[Upload] 错误堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"读取文件失败: {str(e)}")
    
    # 获取 RustFS 存储服务
    storage = get_rustfs_storage()
    
    # 上传文件到 RustFS
    try:
        from io import BytesIO
        file_buffer = BytesIO(content)
        print(f"[Upload] 开始调用 storage.upload_file...")
        
        result = storage.upload_file(
            file_data=file_buffer,
            filename=file.filename,
            bucket="uploads",
            content_type=file.content_type or "application/octet-stream",
            metadata={"doc_id": doc_id, "original_name": file.filename}
        )
        
        upload_time = time.time() - start_time
        print(f"[Upload] 文件上传到存储成功: {file.filename}, 耗时: {upload_time:.2f}s")
        
    except Exception as e:
        import traceback
        print(f"[Upload] 文件上传到存储失败: {file.filename}, 错误: {e}")
        print(f"[Upload] 错误堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")
    
    if not result["success"]:
        print(f"[Upload] 文件上传失败: {result.get('error')}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {result.get('error')}")
    
    # 确定文件状态
    if is_parseable_file(filename_lower):
        # 可解析文件设置为待处理状态
        status = FileStatus.PENDING
    else:
        # 其他文件直接标记为完成
        status = FileStatus.COMPLETED
    
    # 创建数据库记录
    storage_record = StorageRecord(
        id=uuid.uuid4(),
        bucket=result["bucket"],
        object_key=result["object_key"],
        filename=file.filename,
        file_type=FileType.UPLOAD,
        mime_type=file.content_type,
        size=result["size"],
        etag=result["etag"],
        doc_id=doc_id,
        status=status,
        meta_data=json.dumps({"original_name": file.filename})
    )
    
    db.add(storage_record)
    await db.commit()
    
    response = {
        "filename": file.filename,
        "doc_id": doc_id,
        "file_id": str(storage_record.id),
        "status": "uploaded",
        "size": result["size"],
        "bucket": result["bucket"],
        "object_key": result["object_key"],
        "s3_url": storage_record.s3_url,
    }
    
    # 根据文件类型返回不同的消息
    if is_pdf_file(filename_lower):
        response["message"] = "PDF 上传成功，请点击解析按钮转换为 Markdown"
        response["file_type"] = "pdf"
        response["needs_parse"] = True
    elif is_word_file(filename_lower):
        response["message"] = "Word 文档上传成功，已保存到存储"
        response["file_type"] = "docx"
        response["needs_parse"] = False
    elif is_text_file(filename_lower):
        response["message"] = "TXT 文件上传成功，已保存到存储"
        response["file_type"] = "txt"
        response["needs_parse"] = False
    elif is_csv_file(filename_lower):
        response["message"] = "CSV 文件上传成功，已保存到存储"
        response["file_type"] = "csv"
        response["needs_parse"] = False
    else:
        response["message"] = "文档上传成功（不支持的文件类型，仅保存）"
        response["file_type"] = "unknown"
        response["needs_parse"] = False
    
    return response


async def _run_parse_task_with_cleanup(
    task_id: str, 
    bucket: str, 
    object_key: str, 
    filename: str, 
    doc_id: str, 
    source_id: str
):
    """包装解析任务，确保完成后从活跃集合中移除。解析失败时删除数据库记录和存储文件。"""
    try:
        await parse_pdf_task(task_id, bucket, object_key, filename, doc_id, source_id)
    except Exception as e:
        # 捕获所有未处理的异常
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        print(f"[ParseTask] 任务 {task_id} 发生未捕获的异常: {error_msg}")
        print(f"[ParseTask] 错误堆栈:\n{error_trace}")
        
        # 更新任务状态为失败
        if task_id in parse_tasks:
            parse_tasks[task_id].status = "failed"
            parse_tasks[task_id].message = "解析失败"
            parse_tasks[task_id].error = error_msg
        
        # 记录日志
        try:
            logger = get_parse_file_logger()
            logger.add_log(task_id, "ERROR", f"解析任务异常: {error_msg}")
            logger.add_log(task_id, "ERROR", f"错误堆栈: {error_trace}")
        except:
            pass
        
        # 解析失败：删除数据库记录和存储文件
        print(f"[ParseTask] 解析失败，清理数据库记录和存储文件...")
        try:
            from core.database import AsyncSessionLocal
            from core.storage import StorageRecord
            from sqlalchemy import select, and_
            
            async with AsyncSessionLocal() as db:
                # 查找并删除源文件记录
                result = await db.execute(
                    select(StorageRecord).where(
                        and_(
                            StorageRecord.bucket == bucket,
                            StorageRecord.object_key == object_key
                        )
                    )
                )
                source_record = result.scalar_one_or_none()
                if source_record:
                    await db.delete(source_record)
                    print(f"[ParseTask] 已删除数据库记录: {source_id}")
                
                # 删除关联的解析结果记录（如 Markdown）
                result = await db.execute(
                    select(StorageRecord).where(StorageRecord.source_id == uuid.UUID(source_id))
                )
                related_records = result.scalars().all()
                for record in related_records:
                    await db.delete(record)
                    print(f"[ParseTask] 已删除关联记录: {record.id}")
                
                await db.commit()
                print(f"[ParseTask] 数据库记录清理完成")
        except Exception as db_err:
            print(f"[ParseTask] 清理数据库记录失败: {db_err}")
        
        # 删除存储中的文件
        try:
            storage = get_rustfs_storage()
            storage.delete_file(bucket, object_key)
            print(f"[ParseTask] 已删除存储文件: {bucket}/{object_key}")
        except Exception as storage_err:
            print(f"[ParseTask] 删除存储文件失败: {storage_err}")
    finally:
        # 任务完成，从活跃集合中移除
        _active_tasks.discard(task_id)


@router.post("/parse/{doc_id}")
async def start_parse(
    doc_id: str, 
    filename: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    开始解析 PDF 为 Markdown（仅支持 PDF 文件）
    
    MinerU 会自动检测 PDF 类型并选择最佳解析方式：
    - 对于文本型 PDF：直接提取文本，速度快
    - 对于扫描件/图片型 PDF：自动启用 OCR 进行识别
    
    Args:
        doc_id: 文档 ID
        filename: 文件名（可选）
    """
    if not MINERU_AVAILABLE:
        raise HTTPException(status_code=503, detail="PDF 解析服务不可用")
    
    # 查询数据库获取文件信息
    result = await db.execute(
        select(StorageRecord).where(
            and_(
                StorageRecord.doc_id == doc_id,
                StorageRecord.file_type == FileType.UPLOAD
            )
        )
    )
    storage_record = result.scalar_one_or_none()
    
    if not storage_record:
        raise HTTPException(status_code=404, detail="文档未找到")
    
    # 检查文件类型（仅支持 PDF）
    actual_filename = filename or storage_record.filename
    filename_lower = actual_filename.lower()
    
    if not is_pdf_file(filename_lower):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件的解析，Word/TXT/CSV 文件可直接下载查看")
    
    # 检查是否已有正在进行的任务
    if doc_id in parse_tasks:
        task = parse_tasks[doc_id]
        if task.status == "parsing" or task.status == "processing" or task.status == "pending":
            raise HTTPException(status_code=409, detail="解析任务正在进行中")
    
    # 清除之前的日志（如果是重新解析）
    logger = get_parse_file_logger()
    logger.clear_logs(doc_id)
    
    # 清除之前的取消标志（如果存在）
    if doc_id in _cancel_events:
        del _cancel_events[doc_id]
    
    # 创建新的解析任务
    task_id = doc_id
    parse_tasks[task_id] = ParseStatus(
        task_id=task_id,
        status="pending",
        filename=actual_filename,
        message="等待解析..."
    )
    
    # 创建日志记录器
    logger.create_task_logger(task_id)
    logger.add_log(task_id, "INFO", f"开始解析任务: {actual_filename}")
    
    # 更新文件状态为处理中
    storage_record.status = FileStatus.PROCESSING
    await db.commit()
    
    # 创建取消事件
    _cancel_events[task_id] = asyncio.Event()
    
    # 使用 asyncio.create_task 创建后台任务（比 BackgroundTasks 更可靠）
    task = asyncio.create_task(
        _run_parse_task_with_cleanup(
            task_id, 
            storage_record.bucket,
            storage_record.object_key,
            storage_record.filename,
            doc_id,
            str(storage_record.id)
        )
    )
    
    # 保存任务引用，防止被垃圾回收
    _active_tasks.add(task_id)
    
    return {
        "task_id": task_id,
        "status": "started",
        "message": "PDF 解析任务已启动"
    }


@router.post("/parse/stop/{doc_id}", response_model=StopParseResponse)
async def stop_parse(
    doc_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    停止正在进行的解析任务
    
    Args:
        doc_id: 文档 ID
    """
    if doc_id not in parse_tasks:
        raise HTTPException(status_code=404, detail="未找到解析任务")
    
    task = parse_tasks[doc_id]
    
    # 检查任务状态
    if task.status not in ["pending", "parsing", "processing"]:
        return StopParseResponse(
            task_id=doc_id,
            status="already_stopped",
            message=f"任务已经处于 {task.status} 状态，无需停止"
        )
    
    # 设置取消标志
    if doc_id in _cancel_events:
        _cancel_events[doc_id].set()
    
    # 使用新的进程池终止功能
    try:
        from workers.pool import stop_parse_process
        stopped = stop_parse_process(doc_id)
        if stopped:
            print(f"[StopParse] 已终止解析进程 {doc_id}")
        else:
            print(f"[StopParse] 未找到运行中的进程 {doc_id}")
    except Exception as e:
        print(f"[StopParse] 终止进程时出错: {e}")
    
    # 更新任务状态
    task.status = "stopped"
    task.message = "用户已停止解析"
    
    # 记录日志
    logger = get_parse_file_logger()
    logger.add_log(doc_id, "WARNING", "解析任务已被用户停止")
    
    # 更新数据库状态
    try:
        result = await db.execute(
            select(StorageRecord).where(
                and_(
                    StorageRecord.doc_id == doc_id,
                    StorageRecord.file_type == FileType.UPLOAD
                )
            )
        )
        storage_record = result.scalar_one_or_none()
        if storage_record:
            storage_record.status = FileStatus.FAILED
            storage_record.error_message = "用户停止解析"
            await db.commit()
    except Exception as e:
        print(f"[StopParse] 更新数据库状态失败: {e}")
    
    # 从活跃集合中移除
    _active_tasks.discard(doc_id)
    
    return StopParseResponse(
        task_id=doc_id,
        status="stopped",
        message="解析任务已停止"
    )


def check_cancelled(task_id: str) -> bool:
    """检查任务是否被取消"""
    if task_id in _cancel_events:
        return _cancel_events[task_id].is_set()
    return False


async def parse_pdf_task(
    task_id: str, 
    bucket: str, 
    object_key: str, 
    filename: str,
    doc_id: str,
    source_id: str
):
    """后台解析 PDF 任务
    
    MinerU 会自动检测 PDF 类型并选择最佳解析方式。"""
    temp_file = None
    logger = get_parse_file_logger()
    
    # 设置日志记录器的事件循环（必须在开头设置，确保后续日志能正确推送）
    try:
        current_loop = asyncio.get_event_loop()
        logger.set_event_loop(current_loop)
    except RuntimeError:
        # 如果获取不到事件循环，创建一个新的
        current_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(current_loop)
        logger.set_event_loop(current_loop)
    
    try:
        # 检查是否已取消
        if check_cancelled(task_id):
            logger.add_log(task_id, "WARNING", "任务在开始执行前被取消")
            parse_tasks[task_id].status = "stopped"
            parse_tasks[task_id].message = "任务已取消"
            return
        
        parse_tasks[task_id].status = "parsing"
        parse_tasks[task_id].message = "正在从存储下载文件..."
        logger.add_log(task_id, "INFO", "正在从存储下载文件...")
        
        # 获取存储服务
        storage = get_rustfs_storage()
        
        # 创建临时文件 - 使用可写目录
        temp_dir = get_temp_dir()
        temp_file = temp_dir / f"{doc_id}_{filename}"
        
        # 从 RustFS 下载文件
        success = storage.download_file(bucket, object_key, str(temp_file))
        if not success:
            raise Exception("从存储下载文件失败")
        
        parse_tasks[task_id].message = "正在初始化解析器..."
        
        # 获取解析器
        parser = get_pdf_parser()
        
        # 获取总页数
        total_pages = parser.get_pdf_page_count(str(temp_file))
        parse_tasks[task_id].total_pages = total_pages
        
        # 检查是否已取消
        if check_cancelled(task_id):
            logger.add_log(task_id, "WARNING", "任务在获取页数后被取消")
            parse_tasks[task_id].status = "stopped"
            parse_tasks[task_id].message = "任务已取消"
            return
        
        # 定义进度回调
        def progress_callback(current: int, total: int, status: str):
            # 检查是否已取消
            if check_cancelled(task_id):
                return
            progress = int((current / total) * 100) if total > 0 else 0
            parse_tasks[task_id].current_page = current
            parse_tasks[task_id].progress = min(progress, 99)
            parse_tasks[task_id].message = status
        
        # 定义日志回调 - 使用同步方法记录日志
        def log_callback(level: str, message: str):
            logger.add_log(task_id, level, message)
        
        # 定义取消检查回调
        def cancel_check():
            return check_cancelled(task_id)
        
        # 执行解析 - 使用线程池隔离 MinerU，避免阻塞主进程的事件循环
        # 无论是开发环境还是打包环境，统一使用线程池方式
        from workers.pool import parse_pdf_in_process
        from services.pdf_parser import get_mineru_config_path
        
        logger.add_log(task_id, "INFO", "开始 PDF 解析...")
        parse_tasks[task_id].message = "正在解析 PDF..."
        
        print(f"[ParseTask] 调用 parse_pdf_in_process, task_id={task_id}")
        
        try:
            result = await parse_pdf_in_process(
                pdf_path=str(temp_file),
                doc_id=doc_id,
                task_id=task_id,
                output_dir=str(parser.output_dir),
                config_path=get_mineru_config_path(),
                device=os.environ.get("MINERU_DEVICE", "cpu"),
                backend=os.environ.get("MINERU_BACKEND", "pipeline"),
                filename=filename
            )
            print(f"[ParseTask] parse_pdf_in_process 返回, success={result.get('success')}, cancelled={result.get('cancelled')}")
        except Exception as e:
            print(f"[ParseTask] parse_pdf_in_process 异常: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # 检查是否被取消
        if result.get('cancelled'):
            logger.add_log(task_id, "WARNING", "解析任务被用户取消")
            parse_tasks[task_id].status = "stopped"
            parse_tasks[task_id].message = "任务已取消"
            return
        
        if not result["success"]:
            raise Exception(f"解析失败: {result.get('error', '未知错误')}")
        
        parse_result = result
        
        # 检查是否已取消
        if check_cancelled(task_id):
            logger.add_log(task_id, "WARNING", "解析任务被取消")
            parse_tasks[task_id].status = "stopped"
            parse_tasks[task_id].message = "任务已取消"
            return
        
        logger.add_log(task_id, "INFO", "PDF 解析完成，正在处理结果...")
        
        # 上传解析结果到 RustFS
        parse_tasks[task_id].message = "正在保存解析结果..."
        
        # 1. 先上传图片资源（如果有）
        output_dir = Path(parse_result['output_dir'])
        
        # 获取图片目录（可能是嵌套路径）
        images_dir_path = parse_result.get('images_dir')
        if images_dir_path:
            images_dir = Path(images_dir_path)
        else:
            # 尝试默认路径
            images_dir = output_dir / "images"
        
        image_url_map = {}  # 存储本地路径到 S3 URL 的映射
        
        if images_dir.exists():
            parse_tasks[task_id].message = "正在上传图片资源..."
            logger.add_log(task_id, "INFO", f"发现图片目录，开始上传图片...")
            for img_file in images_dir.rglob("*"):
                if img_file.is_file():
                    rel_path = img_file.relative_to(images_dir)
                    s3_object_key = f"{doc_id}/{rel_path}"
                    
                    # 上传图片到 S3
                    img_result = storage.upload_file_from_path(
                        file_path=str(img_file),
                        bucket="images",
                        object_key=s3_object_key,
                        metadata={
                            "doc_id": doc_id,
                            "source_id": source_id,
                            "type": "image"
                        }
                    )
                    
                    # 生成图片的 S3 URL
                    if img_result.get("success"):
                        s3_url = storage.get_presigned_url("images", s3_object_key, expires=604800)
                        if s3_url:
                            # 存储映射关系：相对路径 -> S3 URL
                            rel_path_str = str(rel_path).replace('\\', '/')  # 统一使用正斜杠
                            image_url_map[rel_path_str] = s3_url
                            image_url_map[f"images/{rel_path_str}"] = s3_url  # 也存储带 images/ 前缀的版本
                            # 同时存储文件名，用于模糊匹配
                            image_url_map[img_file.name] = s3_url
            
            logger.add_log(task_id, "INFO", f"图片上传完成，共 {len(image_url_map)} 张")
        
        # 2. 处理 Markdown 文件，替换图片链接
        parse_tasks[task_id].message = "正在处理 Markdown 文件..."
        logger.add_log(task_id, "INFO", "正在处理 Markdown 文件...")
        markdown_path = Path(parse_result['markdown_file'])
        
        # 读取原始 Markdown 内容
        with open(markdown_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # 替换 Markdown 中的图片链接
        # MinerU 生成的图片链接格式通常是: ![...](images/xxx.png) 或 ![...](xxx.png)
        
        def replace_image_link(match):
            """替换图片链接为 S3 URL"""
            alt_text = match.group(1)  # 图片替代文本
            img_path = match.group(2)  # 图片路径
            
            # 尝试查找对应的 S3 URL
            # 移除开头的 ./ 或 /
            clean_path = img_path.lstrip('./').lstrip('/')
            
            if clean_path in image_url_map:
                return f"![{alt_text}]({image_url_map[clean_path]})"
            
            # 尝试只使用文件名部分匹配
            img_name = Path(clean_path).name
            for key, url in image_url_map.items():
                if key.endswith(img_name):
                    return f"![{alt_text}]({url})"
            
            # 如果没有找到对应的 S3 URL，保持原样
            return match.group(0)
        
        # 替换 Markdown 图片语法: ![alt](path)
        md_content = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_image_link, md_content)
        
        # 替换 HTML 图片语法: <img src="path" ...>
        def replace_html_img(match):
            """替换 HTML 图片标签的 src"""
            prefix = match.group(1)  # <img ... src="
            img_path = match.group(2)  # 图片路径
            suffix = match.group(3)  # " ...>
            
            clean_path = img_path.lstrip('./').lstrip('/')
            
            if clean_path in image_url_map:
                return f'{prefix}{image_url_map[clean_path]}{suffix}'
            
            # 尝试只使用文件名部分匹配
            img_name = Path(clean_path).name
            for key, url in image_url_map.items():
                if key.endswith(img_name):
                    return f'{prefix}{url}{suffix}'
            
            return match.group(0)
        
        md_content = re.sub(r'(<img[^>]+src=["\'])([^"\']+)(["\'][^>]*>)', replace_html_img, md_content)
        
        # 保存修改后的 Markdown 文件
        modified_md_path = output_dir / f"{doc_id}_modified.md"
        with open(modified_md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        # 3. 上传修改后的 Markdown 文件
        # 生成与原文件同名的 Markdown 文件名（只改扩展名）
        original_base_name = Path(filename).stem  # 获取原文件名（不含扩展名）
        md_filename = f"{original_base_name}.md"
        
        md_result = storage.upload_file_from_path(
            file_path=str(modified_md_path),
            bucket="markdowns",
            object_key=f"{doc_id}/{md_filename}",
            metadata={
                "doc_id": doc_id,
                "source_id": source_id,
                "total_pages": str(parse_result['total_pages']),
                "batches": str(parse_result['batches']),
                "images_replaced": str(len(image_url_map)),
                "original_filename": filename
            }
        )
        
        logger.add_log(task_id, "INFO", f"Markdown 文件上传完成: {md_filename}")
        
        # 创建 Markdown 文件的数据库记录
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            md_record = StorageRecord(
                id=uuid.uuid4(),
                bucket=md_result["bucket"],
                object_key=md_result["object_key"],
                filename=md_filename,
                file_type=FileType.MARKDOWN,
                mime_type="text/markdown",
                size=md_result.get("size", 0),
                etag=md_result.get("etag"),
                source_id=uuid.UUID(source_id),
                doc_id=doc_id,
                status=FileStatus.COMPLETED,
                meta_data=json.dumps({
                    "total_pages": parse_result['total_pages'],
                    "batches": parse_result['batches'],
                    "original_filename": filename
                })
            )
            db.add(md_record)
            
            # 更新原文件状态
            result = await db.execute(
                select(StorageRecord).where(
                    and_(
                        StorageRecord.bucket == bucket,
                        StorageRecord.object_key == object_key
                    )
                )
            )
            source_record = result.scalar_one_or_none()
            if source_record:
                source_record.status = FileStatus.COMPLETED
            
            await db.commit()
        
        # 更新任务状态
        parse_tasks[task_id].status = "completed"
        parse_tasks[task_id].progress = 100
        parse_tasks[task_id].message = f"解析完成，共 {parse_result['total_pages']} 页"
        parse_tasks[task_id].output_file = parse_result['markdown_file']
        
        logger.add_log(task_id, "INFO", f"解析任务完成！共 {parse_result['total_pages']} 页")
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        print(f"PDF 解析错误: {e}")
        print(f"错误堆栈:\n{error_trace}")
        
        # 安全地更新任务状态
        if task_id in parse_tasks:
            parse_tasks[task_id].status = "failed"
            parse_tasks[task_id].message = "解析失败"
            parse_tasks[task_id].error = error_msg
        else:
            print(f"[警告] 任务 {task_id} 不存在，无法更新状态")
        
        try:
            logger.add_log(task_id, "ERROR", f"解析失败: {error_msg}")
            logger.add_log(task_id, "ERROR", f"错误堆栈: {error_trace}")
            # 立即刷新错误日志到文件
            logger.flush_task_buffer(task_id)
        except Exception as log_err:
            print(f"[ParseTask] 记录错误日志失败: {log_err}")
        
        # 更新数据库状态
        try:
            from core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(StorageRecord).where(
                        and_(
                            StorageRecord.bucket == bucket,
                            StorageRecord.object_key == object_key
                        )
                    )
                )
                source_record = result.scalar_one_or_none()
                if source_record:
                    source_record.status = FileStatus.FAILED
                    source_record.error_message = error_msg
                    await db.commit()
        except Exception as db_err:
            print(f"更新数据库状态失败: {db_err}")
    
    finally:
        # 清理临时文件
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
                logger.add_log(task_id, "INFO", "临时文件已清理")
            except:
                pass


async def parse_word_task(
    task_id: str, 
    bucket: str, 
    object_key: str, 
    filename: str,
    doc_id: str,
    source_id: str
):
    """后台解析 Word 文档任务"""
    temp_file = None
    logger = get_parse_file_logger()
    
    try:
        parse_tasks[task_id].status = "parsing"
        parse_tasks[task_id].message = "正在从存储下载文件..."
        logger.add_log(task_id, "INFO", "正在从存储下载文件...")
        
        # 获取存储服务
        storage = get_rustfs_storage()
        
        # 创建临时文件
        temp_dir = get_temp_dir()
        temp_file = temp_dir / f"{doc_id}_{filename}"
        
        # 从 RustFS 下载文件
        success = storage.download_file(bucket, object_key, str(temp_file))
        if not success:
            raise Exception("从存储下载文件失败")
        
        parse_tasks[task_id].message = "正在初始化 Word 解析器..."
        
        # 获取 Word 解析器
        parser = get_word_parser()
        
        # 设置日志记录器的事件循环
        logger.set_event_loop(asyncio.get_event_loop())
        
        # 定义进度回调
        def progress_callback(current: int, total: int, status: str):
            progress = int((current / total) * 100) if total > 0 else 0
            parse_tasks[task_id].progress = min(progress, 99)
            parse_tasks[task_id].message = status
        
        # 定义日志回调
        def log_callback(level: str, message: str):
            logger.add_log(task_id, level, message)
        
        # 执行解析
        loop = asyncio.get_event_loop()
        parse_result = await loop.run_in_executor(
            None,
            lambda: parser.parse_docx(str(temp_file), doc_id, progress_callback, log_callback)
        )
        
        logger.add_log(task_id, "INFO", "Word 文档解析完成，正在保存结果...")
        parse_tasks[task_id].message = "正在保存解析结果..."
        
        # 上传 Markdown 文件到 RustFS
        md_path = Path(parse_result['markdown_file'])
        original_base_name = Path(filename).stem
        md_filename = f"{original_base_name}.md"
        
        md_result = storage.upload_file_from_path(
            file_path=str(md_path),
            bucket="markdowns",
            object_key=f"{doc_id}/{md_filename}",
            metadata={
                "doc_id": doc_id,
                "source_id": source_id,
                "total_pages": str(parse_result['total_pages']),
                "paragraph_count": str(parse_result.get('paragraph_count', 0)),
                "table_count": str(parse_result.get('table_count', 0)),
                "original_filename": filename,
                "file_type": "docx"
            }
        )
        
        logger.add_log(task_id, "INFO", f"Markdown 文件上传完成: {md_filename}")
        
        # 创建 Markdown 文件的数据库记录
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            md_record = StorageRecord(
                id=uuid.uuid4(),
                bucket=md_result["bucket"],
                object_key=md_result["object_key"],
                filename=md_filename,
                file_type=FileType.MARKDOWN,
                mime_type="text/markdown",
                size=md_result.get("size", 0),
                etag=md_result.get("etag"),
                source_id=uuid.UUID(source_id),
                doc_id=doc_id,
                status=FileStatus.COMPLETED,
                meta_data=json.dumps({
                    "total_pages": parse_result['total_pages'],
                    "paragraph_count": parse_result.get('paragraph_count', 0),
                    "table_count": parse_result.get('table_count', 0),
                    "original_filename": filename,
                    "file_type": "docx"
                })
            )
            db.add(md_record)
            
            # 更新原文件状态
            result = await db.execute(
                select(StorageRecord).where(
                    and_(
                        StorageRecord.bucket == bucket,
                        StorageRecord.object_key == object_key
                    )
                )
            )
            source_record = result.scalar_one_or_none()
            if source_record:
                source_record.status = FileStatus.COMPLETED
            
            await db.commit()
        
        # 更新任务状态
        parse_tasks[task_id].status = "completed"
        parse_tasks[task_id].progress = 100
        parse_tasks[task_id].message = f"解析完成，共 {parse_result['paragraph_count']} 个段落，{parse_result['table_count']} 个表格"
        parse_tasks[task_id].output_file = str(md_path)
        
        logger.add_log(task_id, "INFO", f"Word 文档解析完成！共 {parse_result['paragraph_count']} 个段落，{parse_result['table_count']} 个表格")
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        parse_tasks[task_id].status = "failed"
        parse_tasks[task_id].message = "解析失败"
        parse_tasks[task_id].error = error_msg
        print(f"Word 解析错误: {e}")
        print(f"错误堆栈:\n{error_trace}")
        
        logger.add_log(task_id, "ERROR", f"解析失败: {error_msg}")
        logger.add_log(task_id, "ERROR", f"错误堆栈: {error_trace}")
        
        # 更新数据库状态
        try:
            from core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(StorageRecord).where(
                        and_(
                            StorageRecord.bucket == bucket,
                            StorageRecord.object_key == object_key
                        )
                    )
                )
                source_record = result.scalar_one_or_none()
                if source_record:
                    source_record.status = FileStatus.FAILED
                    source_record.error_message = error_msg
                    await db.commit()
        except Exception as db_err:
            print(f"更新数据库状态失败: {db_err}")
    
    finally:
        # 清理临时文件
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
                logger.add_log(task_id, "INFO", "临时文件已清理")
            except:
                pass


async def parse_text_task(
    task_id: str, 
    bucket: str, 
    object_key: str, 
    filename: str,
    doc_id: str,
    source_id: str
):
    """后台解析 TXT/CSV 文件任务"""
    temp_file = None
    logger = get_parse_file_logger()
    
    try:
        parse_tasks[task_id].status = "parsing"
        parse_tasks[task_id].message = "正在从存储下载文件..."
        logger.add_log(task_id, "INFO", "正在从存储下载文件...")
        
        # 获取存储服务
        storage = get_rustfs_storage()
        
        # 创建临时文件
        temp_dir = get_temp_dir()
        temp_file = temp_dir / f"{doc_id}_{filename}"
        
        # 从 RustFS 下载文件
        success = storage.download_file(bucket, object_key, str(temp_file))
        if not success:
            raise Exception("从存储下载文件失败")
        
        parse_tasks[task_id].message = "正在初始化文本解析器..."
        
        # 获取文本解析器
        parser = get_text_parser()
        
        # 设置日志记录器的事件循环
        logger.set_event_loop(asyncio.get_event_loop())
        
        # 确定文件类型
        ext = Path(filename).suffix.lower()
        
        # 定义进度回调
        def progress_callback(current: int, total: int, status: str):
            progress = int((current / total) * 100) if total > 0 else 0
            parse_tasks[task_id].progress = min(progress, 99)
            parse_tasks[task_id].message = status
        
        # 定义日志回调
        def log_callback(level: str, message: str):
            logger.add_log(task_id, level, message)
        
        # 执行解析
        loop = asyncio.get_event_loop()
        
        if ext == '.csv':
            parse_result = await loop.run_in_executor(
                None,
                lambda: parser.parse_csv(str(temp_file), doc_id, progress_callback, log_callback)
            )
            file_type_label = "CSV"
            result_info = f"{parse_result['row_count']} 行，{parse_result['col_count']} 列"
        else:  # TXT
            parse_result = await loop.run_in_executor(
                None,
                lambda: parser.parse_txt(str(temp_file), doc_id, progress_callback, log_callback)
            )
            file_type_label = "TXT"
            result_info = f"{parse_result['line_count']} 行"
        
        logger.add_log(task_id, "INFO", f"{file_type_label} 文件解析完成，正在保存结果...")
        parse_tasks[task_id].message = "正在保存解析结果..."
        
        # 上传 Markdown 文件到 RustFS
        md_path = Path(parse_result['markdown_file'])
        original_base_name = Path(filename).stem
        md_filename = f"{original_base_name}.md"
        
        md_result = storage.upload_file_from_path(
            file_path=str(md_path),
            bucket="markdowns",
            object_key=f"{doc_id}/{md_filename}",
            metadata={
                "doc_id": doc_id,
                "source_id": source_id,
                "total_pages": str(parse_result['total_pages']),
                "encoding": parse_result.get('encoding', 'utf-8'),
                "original_filename": filename,
                "file_type": ext.lstrip('.')
            }
        )
        
        logger.add_log(task_id, "INFO", f"Markdown 文件上传完成: {md_filename}")
        
        # 创建 Markdown 文件的数据库记录
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            md_record = StorageRecord(
                id=uuid.uuid4(),
                bucket=md_result["bucket"],
                object_key=md_result["object_key"],
                filename=md_filename,
                file_type=FileType.MARKDOWN,
                mime_type="text/markdown",
                size=md_result.get("size", 0),
                etag=md_result.get("etag"),
                source_id=uuid.UUID(source_id),
                doc_id=doc_id,
                status=FileStatus.COMPLETED,
                meta_data=json.dumps({
                    "total_pages": parse_result['total_pages'],
                    "encoding": parse_result.get('encoding', 'utf-8'),
                    "original_filename": filename,
                    "file_type": ext.lstrip('.')
                })
            )
            db.add(md_record)
            
            # 更新原文件状态
            result = await db.execute(
                select(StorageRecord).where(
                    and_(
                        StorageRecord.bucket == bucket,
                        StorageRecord.object_key == object_key
                    )
                )
            )
            source_record = result.scalar_one_or_none()
            if source_record:
                source_record.status = FileStatus.COMPLETED
            
            await db.commit()
        
        # 更新任务状态
        parse_tasks[task_id].status = "completed"
        parse_tasks[task_id].progress = 100
        parse_tasks[task_id].message = f"解析完成，共 {result_info}"
        parse_tasks[task_id].output_file = str(md_path)
        
        logger.add_log(task_id, "INFO", f"{file_type_label} 文件解析完成！共 {result_info}")
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        parse_tasks[task_id].status = "failed"
        parse_tasks[task_id].message = "解析失败"
        parse_tasks[task_id].error = error_msg
        print(f"文本解析错误: {e}")
        print(f"错误堆栈:\n{error_trace}")
        
        logger.add_log(task_id, "ERROR", f"解析失败: {error_msg}")
        logger.add_log(task_id, "ERROR", f"错误堆栈: {error_trace}")
        
        # 更新数据库状态
        try:
            from core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(StorageRecord).where(
                        and_(
                            StorageRecord.bucket == bucket,
                            StorageRecord.object_key == object_key
                        )
                    )
                )
                source_record = result.scalar_one_or_none()
                if source_record:
                    source_record.status = FileStatus.FAILED
                    source_record.error_message = error_msg
                    await db.commit()
        except Exception as db_err:
            print(f"更新数据库状态失败: {db_err}")
    
    finally:
        # 清理临时文件
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
                logger.add_log(task_id, "INFO", "临时文件已清理")
            except:
                pass


@router.get("/parse/status/{task_id}", response_model=ParseStatus)
async def get_parse_status(task_id: str):
    """获取解析任务状态"""
    if task_id not in parse_tasks:
        raise HTTPException(status_code=404, detail="任务未找到")
    
    return parse_tasks[task_id]


@router.get("/parse/logs/{task_id}")
async def get_parse_logs(
    task_id: str, 
    limit: int = Query(5000, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """获取解析任务的日志 - 从文件读取
    
    Args:
        task_id: 任务ID
        limit: 返回的最大日志条数（默认5000，最大10000）
        offset: 跳过前 offset 条日志（用于增量加载）
    """
    if not MINERU_AVAILABLE:
        raise HTTPException(status_code=503, detail="PDF 解析服务不可用")
    
    logger = get_parse_file_logger()
    
    # 获取日志统计
    stats = logger.get_log_stats(task_id)
    total_lines = stats.get("lines", 0)
    
    # 读取日志
    logs = logger.get_logs(task_id, limit=limit + offset)
    
    # 应用 offset
    if offset > 0:
        logs = logs[offset:]
    
    return {
        "task_id": task_id,
        "logs": [
            {
                "timestamp": log.timestamp,
                "level": log.level,
                "message": log.message
            }
            for log in logs
        ],
        "total": total_lines,
        "returned": len(logs),
        "offset": offset,
        "has_more": total_lines > (offset + len(logs))
    }


@router.get("/parse/logs/{task_id}/stream")
async def stream_parse_logs(task_id: str):
    """
    SSE 流式获取解析日志 - 已弃用，使用轮询替代
    保留此 API 以兼容旧版前端，但内部改为简单轮询
    """
    if not MINERU_AVAILABLE:
        raise HTTPException(status_code=503, detail="PDF 解析服务不可用")
    
    logger = get_parse_file_logger()
    
    async def event_generator():
        """生成 SSE 事件 - 简单轮询模式"""
        last_count = 0
        empty_count = 0
        max_empty = 60  # 最多空轮询 60 次（约 1 分钟）后断开
        
        while empty_count < max_empty:
            logs = logger.get_logs(task_id, limit=1000)
            
            if len(logs) > last_count:
                # 有新日志，发送新增的
                new_logs = logs[last_count:]
                for log in new_logs:
                    yield f"data: {json.dumps({'timestamp': log.timestamp, 'level': log.level, 'message': log.message}, ensure_ascii=False)}\n\n"
                last_count = len(logs)
                empty_count = 0
            else:
                empty_count += 1
            
            # 发送心跳
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            
            # 等待 1 秒
            await asyncio.sleep(1.0)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/parse/result/{task_id}")
async def get_parse_result(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取解析结果内容"""
    if task_id not in parse_tasks:
        raise HTTPException(status_code=404, detail="任务未找到")
    
    task = parse_tasks[task_id]
    
    if task.status != "completed":
        return {
            "task_id": task_id,
            "status": task.status,
            "message": task.message
        }
    
    # 从数据库查询 Markdown 文件
    result = await db.execute(
        select(StorageRecord).where(
            and_(
                StorageRecord.doc_id == task_id,
                StorageRecord.file_type == FileType.MARKDOWN
            )
        )
    )
    md_record = result.scalar_one_or_none()
    
    if not md_record:
        return {
            "task_id": task_id,
            "status": "error",
            "message": "解析结果未找到"
        }
    
    # 从 RustFS 获取文件内容
    storage = get_rustfs_storage()
    content = storage.get_file_content(md_record.bucket, md_record.object_key)
    
    if content is None:
        return {
            "task_id": task_id,
            "status": "error",
            "message": "无法读取解析结果"
        }
    
    return {
        "task_id": task_id,
        "status": "completed",
        "filename": task.filename,
        "total_pages": task.total_pages,
        "content": content.decode('utf-8'),
        "file_id": str(md_record.id),
        "bucket": md_record.bucket,
        "object_key": md_record.object_key,
        "s3_url": md_record.s3_url
    }


@router.get("/")
async def list_documents(db: AsyncSession = Depends(get_db)):
    """获取文档列表"""
    result = await db.execute(
        select(StorageRecord).where(
            StorageRecord.file_type == FileType.UPLOAD
        ).order_by(StorageRecord.created_at.desc())
    )
    records = result.scalars().all()
    
    documents = []
    for record in records:
        # 检查是否有解析任务
        parse_info = None
        if record.doc_id in parse_tasks:
            task = parse_tasks[record.doc_id]
            parse_info = {
                "status": task.status,
                "progress": task.progress,
                "message": task.message
            }
        
        documents.append({
            "doc_id": record.doc_id,
            "file_id": str(record.id),
            "filename": record.filename,
            "size": record.size,
            "upload_time": record.created_at.timestamp() if record.created_at else 0,
            "status": record.status.value if record.status else None,
            "bucket": record.bucket,
            "object_key": record.object_key,
            "s3_url": record.s3_url,
            "parse_info": parse_info
        })
    
    return {
        "documents": documents,
        "total": len(documents)
    }


class FileListResponse(BaseModel):
    """文件列表分页响应模型"""
    files: list[FileInfo]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("/files", response_model=FileListResponse)
async def list_all_files(
    file_type: Optional[str] = None,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db)
):
    """获取所有文件列表（支持分页）"""
    query = select(StorageRecord)
    
    if file_type:
        query = query.where(StorageRecord.file_type == file_type)
    
    # 获取总数
    count_query = select(StorageRecord)
    if file_type:
        count_query = count_query.where(StorageRecord.file_type == file_type)
    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())
    
    # 分页查询
    query = query.order_by(StorageRecord.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    records = result.scalars().all()
    
    # 检查并修复异常的处理中状态
    fixed_records = []
    for r in records:
        if _check_and_fix_processing_status(r):
            fixed_records.append(r)
    
    # 如果有修复的记录，保存到数据库
    if fixed_records:
        await db.commit()
        print(f"[StatusFix] 文件列表中修复了 {len(fixed_records)} 个异常状态")
    
    files = [
        FileInfo(
            id=str(r.id),
            filename=r.filename,
            file_type=r.file_type.value if r.file_type else "unknown",
            size=r.size,
            bucket=r.bucket,
            object_key=r.object_key,
            s3_url=r.s3_url,
            status=r.status.value if r.status else "unknown",
            created_at=r.created_at.isoformat() if r.created_at else "",
            doc_id=r.doc_id
        )
        for r in records
    ]
    
    total_pages = (total + page_size - 1) // page_size
    
    return FileListResponse(
        files=files,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/files/{file_id}")
async def get_file_detail(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取文件详情"""
    from uuid import UUID
    try:
        record = await db.get(StorageRecord, UUID(file_id))
    except:
        raise HTTPException(status_code=400, detail="无效的文件ID")
    
    if not record:
        raise HTTPException(status_code=404, detail="文件未找到")
    
    # 检查并修复异常的处理中状态
    if _check_and_fix_processing_status(record):
        await db.commit()
        print(f"[StatusFix] 文件详情中修复了 {record.id} ({record.filename}) 的异常状态")
    
    # 获取关联的转换后文件
    related_files = []
    related_fixed_count = 0
    if record.file_type == FileType.UPLOAD:
        result = await db.execute(
            select(StorageRecord).where(StorageRecord.source_id == record.id)
        )
        related = result.scalars().all()
        
        # 检查关联文件的状态
        for r in related:
            if _check_and_fix_processing_status(r):
                related_fixed_count += 1
        
        if related_fixed_count > 0:
            await db.commit()
            print(f"[StatusFix] 文件详情的关联文件中修复了 {related_fixed_count} 个异常状态")
        
        related_files = [
            {
                "id": str(r.id),
                "filename": r.filename,
                "file_type": r.file_type.value if r.file_type else None,
                "size": r.size,
                "status": r.status.value if r.status else None,
                "s3_url": r.s3_url,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in related
        ]
    
    return {
        "id": str(record.id),
        "bucket": record.bucket,
        "object_key": record.object_key,
        "s3_url": record.s3_url,
        "filename": record.filename,
        "file_type": record.file_type.value if record.file_type else None,
        "mime_type": record.mime_type,
        "size": record.size,
        "etag": record.etag,
        "source_id": str(record.source_id) if record.source_id else None,
        "doc_id": record.doc_id,
        "status": record.status.value if record.status else None,
        "error_message": record.error_message,
        "meta_data": json.loads(record.meta_data) if record.meta_data else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "related_files": related_files
    }


@router.get("/files/{file_id}/content")
async def get_file_content(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取文件内容"""
    from uuid import UUID
    try:
        record = await db.get(StorageRecord, UUID(file_id))
    except:
        raise HTTPException(status_code=400, detail="无效的文件ID")
    
    if not record:
        raise HTTPException(status_code=404, detail="文件未找到")
    
    storage = get_rustfs_storage()
    content = storage.get_file_content(record.bucket, record.object_key)
    
    if content is None:
        raise HTTPException(status_code=500, detail="无法读取文件内容")
    
    # 根据文件类型返回不同格式
    if record.file_type == FileType.MARKDOWN or record.mime_type == "text/markdown":
        return {"content": content.decode('utf-8'), "type": "text"}
    elif record.mime_type and record.mime_type.startswith("text/"):
        return {"content": content.decode('utf-8'), "type": "text"}
    else:
        import base64
        return {"content": base64.b64encode(content).decode(), "type": "base64"}


class UpdateMarkdownRequest(BaseModel):
    """更新 Markdown 文件请求"""
    content: str


@router.put("/files/{file_id}/content")
async def update_file_content(
    file_id: str,
    request: UpdateMarkdownRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    更新文件内容（仅支持 Markdown 文件）
    
    1. 上传新内容到 S3
    2. 更新数据库记录（大小、etag、更新时间）
    3. 删除旧的 S3 文件
    """
    from uuid import UUID
    from io import BytesIO
    
    try:
        record = await db.get(StorageRecord, UUID(file_id))
    except:
        raise HTTPException(status_code=400, detail="无效的文件ID")
    
    if not record:
        raise HTTPException(status_code=404, detail="文件未找到")
    
    # 只支持 Markdown 文件
    if record.file_type != FileType.MARKDOWN and record.mime_type != "text/markdown":
        raise HTTPException(status_code=400, detail="仅支持 Markdown 文件的编辑")
    
    storage = get_rustfs_storage()
    
    # 保存旧的 object_key，在最后成功后再删除
    old_object_key = record.object_key
    old_bucket = record.bucket
    
    try:
        # 1. 上传新内容到 S3（先生成新文件，确保新文件可用）
        content_bytes = request.content.encode('utf-8')
        new_size = len(content_bytes)
        
        print(f"[UpdateMarkdown] 开始更新文件: {record.filename}, 旧key: {old_object_key}, 新大小: {new_size} bytes")
        
        # 上传新文件（upload_file 会自动生成 object_key）
        file_buffer = BytesIO(content_bytes)
        result = storage.upload_file(
            file_data=file_buffer,
            filename=record.filename,
            bucket=record.bucket,
            content_type="text/markdown",
            metadata={
                "doc_id": record.doc_id,
                "source_id": str(record.source_id) if record.source_id else "",
                "updated": "true"
            }
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=f"上传新文件失败: {result.get('error')}")
        
        new_object_key = result["object_key"]
        print(f"[UpdateMarkdown] 新文件上传成功: {new_object_key}")
        
        # 2. 更新数据库记录（新文件上传成功后才更新数据库）
        record.object_key = new_object_key
        record.size = result["size"]
        record.etag = result["etag"]
        # 更新元数据
        meta_data = json.loads(record.meta_data) if record.meta_data else {}
        meta_data["updated_at"] = datetime.utcnow().isoformat()
        meta_data["previous_size"] = new_size
        record.meta_data = json.dumps(meta_data)
        
        await db.commit()
        
        print(f"[UpdateMarkdown] 数据库记录已更新: {record.id}")
        
        # 3. 数据库更新成功后，删除旧的 S3 文件
        # 这一步即使失败也不会影响数据一致性，只是会残留一个旧文件
        if old_object_key != new_object_key:
            try:
                storage.delete_file(old_bucket, old_object_key)
                print(f"[UpdateMarkdown] 旧文件已删除: {old_object_key}")
            except Exception as e:
                # 删除旧文件失败不影响整体流程，只记录日志
                print(f"[UpdateMarkdown] 删除旧文件失败（非致命，将在后台清理）: {e}")
        
        return {
            "message": "文件更新成功",
            "file_id": file_id,
            "filename": record.filename,
            "size": result["size"],
            "s3_url": record.s3_url,
            "updated_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[UpdateMarkdown] 更新失败: {e}")
        print(f"[UpdateMarkdown] 错误堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"更新文件失败: {str(e)}")


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除文件及其关联文件"""
    from uuid import UUID
    try:
        record = await db.get(StorageRecord, UUID(file_id))
    except:
        raise HTTPException(status_code=400, detail="无效的文件ID")
    
    if not record:
        raise HTTPException(status_code=404, detail="文件未找到")
    
    storage = get_rustfs_storage()
    
    # 删除 RustFS 中的文件
    storage.delete_file(record.bucket, record.object_key)
    
    # 如果是上传文件，同时删除关联的转换文件
    if record.file_type == FileType.UPLOAD:
        result = await db.execute(
            select(StorageRecord).where(StorageRecord.source_id == record.id)
        )
        related_files = result.scalars().all()
        
        for related in related_files:
            storage.delete_file(related.bucket, related.object_key)
            await db.delete(related)
        
        # 删除任务记录和日志
        if record.doc_id in parse_tasks:
            del parse_tasks[record.doc_id]
        
        # 清除日志
        if MINERU_AVAILABLE:
            logger = get_parse_file_logger()
            logger.clear_logs(record.doc_id)
    
    # 删除数据库记录
    await db.delete(record)
    await db.commit()
    
    return {"message": "文件已删除"}


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db)
):
    """通过 doc_id 删除文档"""
    result = await db.execute(
        select(StorageRecord).where(StorageRecord.doc_id == doc_id)
    )
    records = result.scalars().all()
    
    if not records:
        raise HTTPException(status_code=404, detail="文档未找到")
    
    storage = get_rustfs_storage()
    
    for record in records:
        # 删除 RustFS 中的文件
        storage.delete_file(record.bucket, record.object_key)
        # 删除数据库记录
        await db.delete(record)
    
    # 删除任务记录
    if doc_id in parse_tasks:
        del parse_tasks[doc_id]
    
    # 清除日志
    if MINERU_AVAILABLE:
        logger = get_parse_file_logger()
        logger.clear_logs(doc_id)
    
    await db.commit()
    
    return {"message": "文档已删除"}


@router.get("/files/{file_id}/download-with-images")
async def download_markdown_with_images(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    下载 Markdown 文件及其关联的图片，打包成 ZIP 文件
    
    该端点会：
    1. 获取 Markdown 文件内容
    2. 识别并下载所有引用的图片
    3. 将 MD 文件中的图片链接替换为相对路径
    4. 打包成 ZIP 文件返回
    """
    from uuid import UUID
    import traceback
    
    try:
        # 获取文件记录
        record = await db.get(StorageRecord, UUID(file_id))
    except Exception as e:
        print(f"获取文件记录失败: {e}")
        raise HTTPException(status_code=400, detail=f"无效的文件ID: {str(e)}")
    
    if not record:
        raise HTTPException(status_code=404, detail="文件未找到")
    
    # 检查是否是 Markdown 文件
    if record.file_type != FileType.MARKDOWN and record.mime_type != "text/markdown":
        raise HTTPException(status_code=400, detail="该端点仅支持 Markdown 文件")
    
    try:
        # 获取存储服务
        storage = get_rustfs_storage()
        
        # 获取 Markdown 文件内容
        md_content_bytes = storage.get_file_content(record.bucket, record.object_key)
        if md_content_bytes is None:
            raise HTTPException(status_code=500, detail="无法读取 Markdown 文件内容")
        
        md_content = md_content_bytes.decode('utf-8')
        
        # 创建内存中的 ZIP 文件
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 用于存储图片路径映射: 原始 URL -> 相对路径
            image_map = {}
            used_filenames = set()  # 用于检查文件名唯一性
            
            # 提取 Markdown 中的图片链接
            # 匹配 ![alt](url) 格式
            md_image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
            # 匹配 <img src="url" ...> 格式
            html_image_pattern = r'(<img[^>]+src=["\'])([^"\']+)(["\'][^>]*>)'
            
            def is_url(path: str) -> bool:
                """判断是否是 URL（而非本地路径）"""
                return path.startswith('http://') or path.startswith('https://') or path.startswith('data:')
            
            def get_image_filename(url: str, index: int) -> str:
                """从 URL 生成图片文件名"""
                try:
                    from urllib.parse import urlparse, unquote
                    parsed = urlparse(url)
                    path = unquote(parsed.path)
                    filename = os.path.basename(path)
                    
                    # 清理文件名，移除不安全字符
                    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                    
                    # 如果没有文件名或扩展名不合适，使用默认名称
                    valid_exts = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg']
                    if not filename or not any(filename.lower().endswith(ext) for ext in valid_exts):
                        filename = f"image_{index + 1}.png"
                    
                    return filename
                except Exception as e:
                    print(f"生成文件名失败: {e}, URL: {url}")
                    return f"image_{index + 1}.png"
            
            # 收集所有图片 URL
            md_images = re.findall(md_image_pattern, md_content)
            html_images = re.findall(html_image_pattern, md_content)
            
            all_image_urls = set()
            for _, url in md_images:
                if is_url(url):
                    all_image_urls.add(url)
            
            for _, url, _ in html_images:
                if is_url(url):
                    all_image_urls.add(url)
            
            print(f"发现 {len(all_image_urls)} 个图片链接")
            
            # 下载图片并添加到 ZIP
            images_dir = "images"
            for idx, img_url in enumerate(sorted(all_image_urls)):
                try:
                    # 下载图片
                    import urllib.request
                    req = urllib.request.Request(img_url, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    
                    with urllib.request.urlopen(req, timeout=30) as response:
                        img_data = response.read()
                        
                        # 确定文件名
                        img_filename = get_image_filename(img_url, idx)
                        
                        # 确保文件名唯一（只比较文件名，不包括路径）
                        base_name, ext = os.path.splitext(img_filename)
                        counter = 1
                        final_filename = img_filename
                        while final_filename in used_filenames:
                            final_filename = f"{base_name}_{counter}{ext}"
                            counter += 1
                        
                        used_filenames.add(final_filename)
                        
                        # 存储映射关系
                        zip_path = f"{images_dir}/{final_filename}"
                        image_map[img_url] = zip_path
                        
                        # 添加到 ZIP
                        zip_file.writestr(zip_path, img_data)
                        print(f"已添加图片: {zip_path}")
                        
                except Exception as e:
                    print(f"下载图片失败 {img_url}: {e}")
                    # 继续处理其他图片
            
            # 替换 Markdown 中的图片链接为相对路径
            def replace_md_image(match):
                alt_text = match.group(1)
                img_url = match.group(2)
                if img_url in image_map:
                    return f"![{alt_text}]({image_map[img_url]})"
                return match.group(0)
            
            def replace_html_image(match):
                prefix = match.group(1)
                img_url = match.group(2)
                suffix = match.group(3)
                if img_url in image_map:
                    return f"{prefix}{image_map[img_url]}{suffix}"
                return match.group(0)
            
            # 执行替换
            modified_content = re.sub(md_image_pattern, replace_md_image, md_content)
            modified_content = re.sub(html_image_pattern, replace_html_image, modified_content)
            
            # 添加 MD 文件到 ZIP（使用原始文件名）
            md_filename = record.filename
            if not md_filename.endswith('.md'):
                md_filename += '.md'
            
            # 清理文件名中的不安全字符
            safe_md_filename = re.sub(r'[<>:"/\\|?*]', '_', md_filename)
            
            zip_file.writestr(safe_md_filename, modified_content.encode('utf-8'))
            print(f"已添加 Markdown 文件: {safe_md_filename}")
            
            # 添加一个 README 文件说明
            readme_content = f"""# {record.filename}

本压缩包包含:
- {safe_md_filename}: Markdown 文件
- images/: 图片文件夹（包含文档中引用的所有图片）

注意:
- Markdown 文件中的图片链接已修改为相对路径
- 请确保 Markdown 文件与 images 文件夹在同一目录下，图片才能正常显示
"""
            zip_file.writestr("README.txt", readme_content.encode('utf-8'))
        
        # 准备响应
        zip_buffer.seek(0)
        zip_filename = f"{Path(record.filename).stem}.zip"
        
        # 清理 ZIP 文件名中的不安全字符
        safe_zip_filename = re.sub(r'[<>:"/\\|?*]', '_', zip_filename)
        
        # Content-Disposition 头需要特殊处理中文
        # filename 参数只支持 ASCII，中文文件名使用 filename* 参数（RFC 5987）
        from urllib.parse import quote
        
        # 检查是否包含非 ASCII 字符
        try:
            safe_zip_filename.encode('ascii')
            # 纯 ASCII 文件名，直接使用
            content_disposition = f'attachment; filename="{safe_zip_filename}"'
        except UnicodeEncodeError:
            # 包含非 ASCII 字符，使用 RFC 5987 编码
            encoded_filename = quote(safe_zip_filename, safe='')
            # filename 使用通用名称，filename* 使用编码后的名称
            content_disposition = f"attachment; filename=\"document.zip\"; filename*=UTF-8''{encoded_filename}"
        
        print(f"返回 ZIP 文件: {safe_zip_filename}, 大小: {len(zip_buffer.getvalue())} bytes")
        
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": content_disposition,
                "Content-Length": str(len(zip_buffer.getvalue()))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"下载 Markdown 文件失败: {e}")
        print(f"错误堆栈:\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"处理文件时出错: {str(e)}")
