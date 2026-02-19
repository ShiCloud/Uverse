"""
RustFS 存储服务 - 提供 S3 兼容的对象存储功能
"""
import os
import json
import subprocess
import boto3
import json
from botocore.exceptions import ClientError
from pathlib import Path
from typing import Optional, BinaryIO, Dict, Any
from datetime import datetime
import uuid
import urllib.parse

from config.rustfs import RUSTFS_CONFIG, get_s3_config


def encode_metadata_value(value: str) -> str:
    """编码 metadata 值，处理非 ASCII 字符"""
    if isinstance(value, str):
        return urllib.parse.quote(value, safe='')
    return str(value)


def decode_metadata_value(value: str) -> str:
    """解码 metadata 值"""
    try:
        return urllib.parse.unquote(value)
    except:
        return value


class RustFSStorage:
    """RustFS 存储服务类"""
    
    _instance = None
    _process = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._init_client()
    
    def _init_client(self):
        """初始化 S3 客户端"""
        from botocore.config import Config
        
        config = get_s3_config()
        # 配置代理：对本地地址禁用代理
        botocore_config = Config(
            proxies={},
        )
        
        self._client = boto3.client(
            's3',
            endpoint_url=config["endpoint_url"],
            aws_access_key_id=config["aws_access_key_id"],
            aws_secret_access_key=config["aws_secret_access_key"],
            region_name=config["region_name"],
            config=botocore_config,
        )
    
    @classmethod
    def start_server(cls) -> bool:
        """启动 RustFS 服务器"""
        # 检查可执行文件是否存在
        binary_path = Path(RUSTFS_CONFIG["binary_path"])
        if not binary_path.exists():
            print(f"[WARN] RustFS 可执行文件不存在: {binary_path}")
            return False
        
        try:
            # 确保数据目录存在
            data_dir = Path(RUSTFS_CONFIG["data_dir"])
            data_dir.mkdir(parents=True, exist_ok=True)
            
            # 构建启动命令
            cmd = [
                str(binary_path),
                str(data_dir),
                "--address", RUSTFS_CONFIG["address"],
                "--access-key", RUSTFS_CONFIG["access_key"],
                "--secret-key", RUSTFS_CONFIG["secret_key"],
                "--region", RUSTFS_CONFIG["region"],
            ]
            
            if RUSTFS_CONFIG["console_enable"]:
                cmd.extend(["--console-enable", "--console-address", RUSTFS_CONFIG["console_address"]])
            
            # 启动进程
            cls._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            print(f"RustFS 服务器启动中... PID: {cls._process.pid}")
            
            # 等待服务就绪
            import time
            time.sleep(2)
            
            # 初始化存储桶
            storage = cls()
            storage._init_buckets()
            
            return True
            
        except Exception as e:
            print(f"启动 RustFS 服务器失败: {e}")
            return False
    
    @classmethod
    def stop_server(cls):
        """停止 RustFS 服务器"""
        if cls._process:
            cls._process.terminate()
            cls._process = None
            print("RustFS 服务器已停止")
    
    def _init_buckets(self):
        """初始化存储桶并设置公开访问权限"""
        for bucket_name in RUSTFS_CONFIG["buckets"].keys():
            try:
                # 尝试创建存储桶（如果不存在）
                try:
                    self._client.create_bucket(Bucket=bucket_name)
                    print(f"创建存储桶: {bucket_name}")
                except ClientError as e:
                    if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
                        print(f"存储桶已存在: {bucket_name}")
                    else:
                        raise
                
                # 设置存储桶策略为公开读取（无论新建还是已存在）
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": ["*"]},
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                        }
                    ]
                }
                
                self._client.put_bucket_policy(
                    Bucket=bucket_name,
                    Policy=json.dumps(policy)
                )
                print(f"设置存储桶 {bucket_name} 访问策略为公开读取")
                
            except Exception as e:
                print(f"初始化存储桶失败 {bucket_name}: {e}")
    
    def upload_file(
        self, 
        file_data: BinaryIO, 
        filename: str, 
        bucket: str = None,
        content_type: str = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        上传文件到 RustFS
        
        Args:
            file_data: 文件数据流
            filename: 文件名
            bucket: 存储桶名称，默认使用 uploads
            content_type: MIME类型
            metadata: 元数据
            
        Returns:
            上传结果信息
        """
        import time
        start_time = time.time()
        
        bucket = bucket or "uploads"
        object_key = f"{datetime.now().strftime('%Y/%m/%d')}/{uuid.uuid4().hex[:8]}_{filename}"
        
        print(f"[RustFS] 开始上传: {filename} -> bucket={bucket}, key={object_key}")
        
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
            print(f"[RustFS] 使用提供的 Content-Type: {content_type}")
        elif filename:
            # 根据文件名自动检测 Content-Type
            detected_type = self._get_content_type(filename)
            extra_args['ContentType'] = detected_type
            print(f"[RustFS] 自动检测 Content-Type: {detected_type}")
        if metadata:
            # S3 metadata 只支持 ASCII 字符，需要对非 ASCII 字符进行 URL 编码
            encoded_metadata = {}
            for k, v in metadata.items():
                if isinstance(v, str):
                    # URL 编码非 ASCII 字符
                    encoded_metadata[k] = urllib.parse.quote(v, safe='')
                else:
                    encoded_metadata[k] = str(v)
            extra_args['Metadata'] = encoded_metadata
        
        try:
            print(f"[RustFS] 调用 upload_fileobj 开始传输...")
            upload_start = time.time()
            
            self._client.upload_fileobj(
                file_data,
                bucket,
                object_key,
                ExtraArgs=extra_args
            )
            
            upload_duration = time.time() - upload_start
            print(f"[RustFS] upload_fileobj 完成，耗时: {upload_duration:.2f}s")
            
            # 获取文件信息
            response = self._client.head_object(Bucket=bucket, Key=object_key)
            
            total_duration = time.time() - start_time
            print(f"[RustFS] 上传完成: {filename}, size={response.get('ContentLength', 0)} bytes, 总耗时: {total_duration:.2f}s")
            
            return {
                "success": True,
                "bucket": bucket,
                "object_key": object_key,
                "etag": response.get('ETag', '').strip('"'),
                "size": response.get('ContentLength', 0),
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    def _get_content_type(self, file_path: str) -> str:
        """根据文件扩展名获取 Content-Type"""
        import mimetypes
        content_type, _ = mimetypes.guess_type(file_path)
        
        # 如果没有识别到，根据扩展名设置默认值
        if not content_type:
            ext = Path(file_path).suffix.lower()
            content_type_map = {
                '.md': 'text/markdown; charset=utf-8',
                '.markdown': 'text/markdown; charset=utf-8',
                '.txt': 'text/plain; charset=utf-8',
                '.json': 'application/json; charset=utf-8',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.webp': 'image/webp',
                '.pdf': 'application/pdf',
            }
            content_type = content_type_map.get(ext, 'application/octet-stream')
        
        # 对于文本类型，确保包含 charset=utf-8
        if content_type and content_type.startswith('text/') and 'charset' not in content_type:
            content_type += '; charset=utf-8'
        
        return content_type or 'application/octet-stream'
    
    def upload_file_from_path(
        self,
        file_path: str,
        bucket: str = None,
        object_key: str = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        从本地路径上传文件
        
        Args:
            file_path: 本地文件路径
            bucket: 存储桶名称
            object_key: 对象键，默认自动生成
            metadata: 元数据
            
        Returns:
            上传结果信息
        """
        bucket = bucket or "uploads"
        
        if object_key is None:
            filename = Path(file_path).name
            object_key = f"{datetime.now().strftime('%Y/%m/%d')}/{uuid.uuid4().hex[:8]}_{filename}"
        
        extra_args = {
            'ContentType': self._get_content_type(file_path)
        }
        if metadata:
            # S3 metadata 只支持 ASCII 字符，需要对非 ASCII 字符进行 URL 编码
            extra_args['Metadata'] = {k: encode_metadata_value(v) for k, v in metadata.items()}
        
        try:
            self._client.upload_file(
                file_path,
                bucket,
                object_key,
                ExtraArgs=extra_args
            )
            
            response = self._client.head_object(Bucket=bucket, Key=object_key)
            
            return {
                "success": True,
                "bucket": bucket,
                "object_key": object_key,
                "etag": response.get('ETag', '').strip('"'),
                "size": response.get('ContentLength', 0),
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    def download_file(self, bucket: str, object_key: str, file_path: str) -> bool:
        """
        下载文件到本地
        
        Args:
            bucket: 存储桶名称
            object_key: 对象键
            file_path: 本地保存路径
            
        Returns:
            是否成功
        """
        try:
            self._client.download_file(bucket, object_key, file_path)
            return True
        except ClientError as e:
            print(f"下载文件失败: {e}")
            return False
    
    def get_file_content(self, bucket: str, object_key: str) -> Optional[bytes]:
        """
        获取文件内容
        
        Args:
            bucket: 存储桶名称
            object_key: 对象键
            
        Returns:
            文件内容字节
        """
        try:
            response = self._client.get_object(Bucket=bucket, Key=object_key)
            return response['Body'].read()
        except ClientError as e:
            print(f"获取文件内容失败: {e}")
            return None
    
    def delete_file(self, bucket: str, object_key: str) -> bool:
        """
        删除文件
        
        Args:
            bucket: 存储桶名称
            object_key: 对象键
            
        Returns:
            是否成功
        """
        try:
            self._client.delete_object(Bucket=bucket, Key=object_key)
            return True
        except ClientError as e:
            print(f"删除文件失败: {e}")
            return False
    
    def list_files(self, bucket: str, prefix: str = "") -> list:
        """
        列出文件
        
        Args:
            bucket: 存储桶名称
            prefix: 前缀过滤
            
        Returns:
            文件列表
        """
        try:
            response = self._client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix
            )
            return response.get('Contents', [])
        except ClientError as e:
            print(f"列出文件失败: {e}")
            return []
    
    def get_presigned_url(self, bucket: str, object_key: str, expires: int = 3600) -> Optional[str]:
        """
        获取预签名URL
        
        Args:
            bucket: 存储桶名称
            object_key: 对象键
            expires: 过期时间（秒）
            
        Returns:
            预签名URL
        """
        try:
            url = self._client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': object_key},
                ExpiresIn=expires
            )
            return url
        except ClientError as e:
            print(f"生成预签名URL失败: {e}")
            return None


# 全局存储服务实例
_rustfs_storage = None


def get_rustfs_storage() -> RustFSStorage:
    """获取 RustFS 存储服务实例"""
    global _rustfs_storage
    if _rustfs_storage is None:
        _rustfs_storage = RustFSStorage()
    return _rustfs_storage


def start_rustfs_server() -> bool:
    """启动 RustFS 服务器"""
    return RustFSStorage.start_server()


def stop_rustfs_server():
    """停止 RustFS 服务器"""
    RustFSStorage.stop_server()
