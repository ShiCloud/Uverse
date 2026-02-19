"""
文件存储模型 - 记录 S3 文件信息
真实文件存储在 RustFS (S3 兼容存储) 中
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from core.database import Base


class FileType(str, enum.Enum):
    """文件类型"""
    UPLOAD = "upload"           # 上传的原始文件
    MARKDOWN = "markdown"       # 转换后的 Markdown
    IMAGE = "image"             # 图片资源
    OTHER = "other"             # 其他类型


class FileStatus(str, enum.Enum):
    """文件状态"""
    PENDING = "pending"         # 等待处理
    PROCESSING = "processing"   # 处理中
    COMPLETED = "completed"     # 完成
    FAILED = "failed"           # 失败


class StorageRecord(Base):
    """S3 文件存储记录表 - 真实文件存储在 RustFS 中"""
    __tablename__ = "storage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # S3 定位信息
    bucket = Column(String(100), nullable=False, comment="S3存储桶")
    object_key = Column(String(500), nullable=False, comment="S3对象键")
    
    # 文件基本信息
    filename = Column(String(255), nullable=False, comment="原始文件名")
    file_type = Column(SQLEnum(FileType), nullable=False, comment="文件类型")
    mime_type = Column(String(100), comment="MIME类型")
    size = Column(Integer, default=0, comment="文件大小(字节)")
    etag = Column(String(100), comment="文件ETag")
    
    # 关联信息
    source_id = Column(UUID(as_uuid=True), comment="源文件ID(用于转换后的文件)")
    doc_id = Column(String(50), comment="文档ID")
    
    # 处理状态
    status = Column(SQLEnum(FileStatus), default=FileStatus.PENDING, comment="处理状态")
    error_message = Column(Text, comment="错误信息")
    
    # 元数据 (JSON格式)
    meta_data = Column(Text, comment="JSON格式的元数据")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    @property
    def s3_url(self) -> str:
        """生成 S3 预签名访问 URL（7天有效，接近永久）"""
        from services.rustfs_storage import get_rustfs_storage
        try:
            storage = get_rustfs_storage()
            # 7天 = 604800 秒，这是 AWS S3 预签名 URL 的最大有效期
            url = storage.get_presigned_url(self.bucket, self.object_key, expires=604800)
            return url or f"http://127.0.0.1:9000/{self.bucket}/{self.object_key}"
        except:
            return f"http://127.0.0.1:9000/{self.bucket}/{self.object_key}"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "bucket": self.bucket,
            "object_key": self.object_key,
            "s3_url": self.s3_url,
            "filename": self.filename,
            "file_type": self.file_type.value if self.file_type else None,
            "mime_type": self.mime_type,
            "size": self.size,
            "etag": self.etag,
            "source_id": str(self.source_id) if self.source_id else None,
            "doc_id": self.doc_id,
            "status": self.status.value if self.status else None,
            "error_message": self.error_message,
            "meta_data": self.meta_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
