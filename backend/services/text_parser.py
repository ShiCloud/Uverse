"""
文本文件解析服务 - 支持 TXT、CSV 文件的解析
"""
import os
import io
import csv
import chardet
from pathlib import Path
from typing import Dict, Optional, List


def get_mineru_output_dir() -> Path:
    """获取 MinerU 输出目录 - 优先使用环境变量 MINERU_OUTPUT_DIR"""
    output_dir_env = os.getenv('MINERU_OUTPUT_DIR')
    if output_dir_env:
        return Path(output_dir_env)
    
    # 默认使用用户可写目录
    if os.name == 'nt':  # Windows
        base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif os.uname().sysname == 'Darwin':  # macOS
        base_dir = Path.home() / 'Library' / 'Application Support'
    else:  # Linux
        base_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base_dir / 'Uverse' / 'outputs'


class TextParser:
    """文本文件解析器 - 支持 TXT、CSV 格式"""
    
    def __init__(self, output_dir: str = None):
        if output_dir is None:
            output_dir = str(get_mineru_output_dir())
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def detect_encoding(self, file_path: str) -> str:
        """
        检测文件编码
        
        Args:
            file_path: 文件路径
            
        Returns:
            检测到的编码格式
        """
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            encoding = result.get('encoding', 'utf-8')
            # 处理 GB2312 作为 GB18030 的子集
            if encoding and encoding.lower() == 'gb2312':
                encoding = 'gb18030'
            return encoding or 'utf-8'
    
    def parse_txt(
        self, 
        file_path: str, 
        doc_id: str,
        progress_callback: Optional[callable] = None,
        log_callback: Optional[callable] = None
    ) -> Dict:
        """
        解析 TXT 文件
        
        Args:
            file_path: TXT 文件路径
            doc_id: 文档 ID
            progress_callback: 进度回调函数
            log_callback: 日志回调函数
            
        Returns:
            解析结果字典
        """
        try:
            if log_callback:
                log_callback("INFO", f"开始解析 TXT 文件: {file_path}")
            
            if progress_callback:
                progress_callback(0, 100, "正在检测文件编码...")
            
            # 检测编码
            encoding = self.detect_encoding(file_path)
            
            if log_callback:
                log_callback("INFO", f"检测到文件编码: {encoding}")
            
            if progress_callback:
                progress_callback(20, 100, "正在读取文件内容...")
            
            # 读取内容
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                content = f.read()
            
            # 统计行数
            lines = content.split('\n')
            line_count = len(lines)
            
            if log_callback:
                log_callback("INFO", f"文件共 {line_count} 行")
            
            if progress_callback:
                progress_callback(60, 100, "正在转换为 Markdown...")
            
            # 创建输出目录
            doc_output_dir = self.output_dir / doc_id
            doc_output_dir.mkdir(parents=True, exist_ok=True)
            
            # 转换为 Markdown 格式
            md_content = self._txt_to_markdown(content)
            
            if progress_callback:
                progress_callback(80, 100, "正在保存 Markdown 文件...")
            
            # 保存 Markdown 文件
            original_name = Path(file_path).stem
            md_filename = f"{original_name}.md"
            md_path = doc_output_dir / md_filename
            
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            if log_callback:
                log_callback("INFO", f"Markdown 文件已保存: {md_path}")
            
            if progress_callback:
                progress_callback(100, 100, "解析完成")
            
            return {
                "doc_id": doc_id,
                "file_type": "txt",
                "total_pages": 1,
                "line_count": line_count,
                "encoding": encoding,
                "output_dir": str(doc_output_dir),
                "markdown_file": str(md_path),
                "images_dir": None,
                "content": content,
            }
            
        except Exception as e:
            error_msg = f"解析 TXT 文件失败: {str(e)}"
            if log_callback:
                log_callback("ERROR", error_msg)
            raise Exception(error_msg)
    
    def parse_csv(
        self, 
        file_path: str, 
        doc_id: str,
        progress_callback: Optional[callable] = None,
        log_callback: Optional[callable] = None
    ) -> Dict:
        """
        解析 CSV 文件
        
        Args:
            file_path: CSV 文件路径
            doc_id: 文档 ID
            progress_callback: 进度回调函数
            log_callback: 日志回调函数
            
        Returns:
            解析结果字典
        """
        try:
            if log_callback:
                log_callback("INFO", f"开始解析 CSV 文件: {file_path}")
            
            if progress_callback:
                progress_callback(0, 100, "正在检测文件编码...")
            
            # 检测编码
            encoding = self.detect_encoding(file_path)
            
            if log_callback:
                log_callback("INFO", f"检测到文件编码: {encoding}")
            
            if progress_callback:
                progress_callback(20, 100, "正在读取 CSV 数据...")
            
            # 读取 CSV 内容
            rows: List[List[str]] = []
            headers: List[str] = []
            delimiter = ','
            
            with open(file_path, 'r', encoding=encoding, errors='ignore', newline='') as f:
                # 尝试检测分隔符
                sample = f.read(8192)
                f.seek(0)
                
                # 使用 csv.Sniffer 检测分隔符
                try:
                    dialect = csv.Sniffer().sniff(sample)
                    delimiter = dialect.delimiter
                    if log_callback:
                        log_callback("INFO", f"检测到分隔符: '{delimiter}'")
                except:
                    # 检测失败，使用逗号作为默认分隔符
                    if log_callback:
                        log_callback("INFO", "使用默认分隔符: ','")
                
                reader = csv.reader(f, delimiter=delimiter)
                
                try:
                    headers = next(reader)
                    headers = [h.strip() for h in headers]
                except StopIteration:
                    headers = []
                
                if progress_callback:
                    progress_callback(40, 100, "正在解析数据行...")
                
                for i, row in enumerate(reader):
                    rows.append([cell.strip() for cell in row])
                    
                    # 每 1000 行更新一次进度
                    if i % 1000 == 0 and progress_callback:
                        progress = 40 + min(int((i / max(i + 100, 1)) * 40), 40)
                        progress_callback(progress, 100, f"已解析 {i} 行...")
            
            row_count = len(rows)
            col_count = len(headers) if headers else (len(rows[0]) if rows else 0)
            
            if log_callback:
                log_callback("INFO", f"CSV 文件包含 {col_count} 列，{row_count} 行数据")
            
            if progress_callback:
                progress_callback(70, 100, "正在转换为 Markdown 表格...")
            
            # 创建输出目录
            doc_output_dir = self.output_dir / doc_id
            doc_output_dir.mkdir(parents=True, exist_ok=True)
            
            # 转换为 Markdown 表格格式
            md_content = self._csv_to_markdown(headers, rows)
            
            if progress_callback:
                progress_callback(80, 100, "正在保存 Markdown 文件...")
            
            # 保存 Markdown 文件
            original_name = Path(file_path).stem
            md_filename = f"{original_name}.md"
            md_path = doc_output_dir / md_filename
            
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            if log_callback:
                log_callback("INFO", f"Markdown 文件已保存: {md_path}")
            
            if progress_callback:
                progress_callback(100, 100, "解析完成")
            
            return {
                "doc_id": doc_id,
                "file_type": "csv",
                "total_pages": 1,
                "row_count": row_count,
                "col_count": col_count,
                "encoding": encoding,
                "delimiter": delimiter,
                "headers": headers,
                "output_dir": str(doc_output_dir),
                "markdown_file": str(md_path),
                "images_dir": None,
                "content": md_content,
            }
            
        except Exception as e:
            error_msg = f"解析 CSV 文件失败: {str(e)}"
            if log_callback:
                log_callback("ERROR", error_msg)
            raise Exception(error_msg)
    
    def _txt_to_markdown(self, content: str) -> str:
        """
        将 TXT 内容转换为 Markdown 格式
        
        使用启发式规则检测标题、列表等格式
        """
        lines = content.split('\n')
        md_lines = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                md_lines.append('')
                continue
            
            # 检测一级标题：全大写且较短
            if line.isupper() and 5 < len(line) < 100:
                md_lines.append(f"# {line}")
                continue
            
            # 检测二级标题：以冒号结尾
            if line.endswith(('：', ':')) and len(line) < 80:
                md_lines.append(f"## {line.rstrip('：:').strip()}")
                continue
            
            # 检测中文序号标题
            if line[:3] in ['一、', '二、', '三、', '四、', '五、', 
                            '六、', '七、', '八、', '九、', '十、']:
                md_lines.append(f"## {line}")
                continue
            
            if line[:4] in ['（一）', '（二）', '（三）', '（四）', '（五）',
                            '（六）', '（七）', '（八）', '（九）', '（十）']:
                md_lines.append(f"### {line}")
                continue
            
            # 检测数字标题
            if len(line) > 3 and line[0].isdigit() and line[1:3] in '.、':
                md_lines.append(f"### {line}")
                continue
            
            # 检测列表项
            if line.startswith(('•', '-', '*', '·', '○', '●')):
                md_lines.append(f"- {line[1:].strip()}")
                continue
            
            # 检测括号数字
            if line[:2] in ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩']:
                md_lines.append(f"- {line}")
                continue
            
            # 普通段落
            md_lines.append(line)
        
        return '\n\n'.join(md_lines)
    
    def _csv_to_markdown(self, headers: List[str], rows: List[List[str]]) -> str:
        """
        将 CSV 数据转换为 Markdown 表格
        
        Args:
            headers: 表头列表
            rows: 数据行列表
            
        Returns:
            Markdown 表格格式的字符串
        """
        if not headers and not rows:
            return "_空 CSV 文件_"
        
        md_lines = []
        
        # 获取最大列数
        max_cols = max(len(headers) if headers else 0, 
                       max((len(row) for row in rows), default=0))
        
        # 处理表头
        if headers:
            # 补齐列数
            header_row = headers + [''] * (max_cols - len(headers))
            header_row = header_row[:max_cols]
            md_lines.append('| ' + ' | '.join(header_row) + ' |')
        else:
            # 没有表头，生成默认列名
            header_row = [f"列{i+1}" for i in range(max_cols)]
            md_lines.append('| ' + ' | '.join(header_row) + ' |')
        
        # 分隔行
        md_lines.append('|' + '|'.join(['---' for _ in range(max_cols)]) + '|')
        
        # 处理数据行（最多显示 1000 行，避免文件过大）
        display_rows = rows[:1000]
        for row in display_rows:
            # 补齐列数
            row_data = row + [''] * (max_cols - len(row))
            row_data = row_data[:max_cols]
            # 转义管道符
            row_data = [cell.replace('|', '\\|') for cell in row_data]
            md_lines.append('| ' + ' | '.join(row_data) + ' |')
        
        # 如果有更多行，添加提示
        if len(rows) > 1000:
            md_lines.append('')
            md_lines.append(f"*... 还有 {len(rows) - 1000} 行数据未显示 ...*")
        
        # 添加统计信息
        md_lines.append('')
        md_lines.append(f"**总计: {len(rows)} 行, {max_cols} 列**")
        
        return '\n'.join(md_lines)


# 全局解析器实例
_text_parser = None


def get_text_parser() -> TextParser:
    """获取文本解析器实例"""
    global _text_parser
    if _text_parser is None:
        _text_parser = TextParser()
    return _text_parser
