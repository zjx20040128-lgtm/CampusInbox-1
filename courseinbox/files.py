"""Local extraction: Windows OCR, optional pypdf, and UTF-8 text."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from .core import ValidationError

MAX_UPLOAD = 8 * 1024 * 1024

def normalize_ocr(text):
    # Windows Chinese OCR can add spaces between every ideograph and even date digits.
    text=re.sub(r'(?<=[\u4e00-\u9fff0-9《》【】：、，。])[^\S\r\n]+(?=[\u4e00-\u9fff0-9《》【】：、，。])','',text)
    return text.strip()

def extract_file(name, data, root):
    if len(data)>MAX_UPLOAD or not data:
        raise ValidationError('文件为空或超过 8 MB。')
    suffix=Path(name).suffix.lower()
    if suffix in ('.txt','.md'):
        try: return data.decode('utf-8-sig'), 'utf8-text'
        except UnicodeDecodeError: raise ValidationError('文本文件需为 UTF-8 编码。') from None
    if suffix=='.pdf':
        try: from pypdf import PdfReader
        except ImportError: raise ValidationError('PDF 文本提取需安装可选依赖 pypdf；也可直接复制文本。') from None
        import io
        try:
            reader=PdfReader(io.BytesIO(data))
            if reader.is_encrypted: raise ValidationError('暂不支持加密 PDF。')
            if len(reader.pages)>30: raise ValidationError('PDF 最多 30 页，请按通知拆分。')
            text='\n\n'.join(page.extract_text() or '' for page in reader.pages)
        except ValidationError: raise
        except Exception: raise ValidationError('PDF 无法读取，请检查文件。') from None
        if not text.strip(): raise ValidationError('扫描 PDF 没有可提取文本，请导入页面截图或复制文本。')
        return text,'pdf-text'
    if suffix not in ('.png','.jpg','.jpeg','.bmp'):
        raise ValidationError('支持 PNG/JPG/BMP 截图、UTF-8 文本和文本 PDF。')
    if os.name!='nt': raise ValidationError('此基础版的截图 OCR 使用 Windows，请在 Windows 运行或粘贴截图文字。')
    # Never execute the uploaded name. The temporary file has an application-generated path.
    script=Path(root)/'scripts'/'windows-ocr.ps1'
    powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
    with tempfile.TemporaryDirectory(prefix='courseinbox-ocr-') as directory:
        target=Path(directory)/('image'+suffix)
        target.write_bytes(data)
        try:
            result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-Path',str(target)],capture_output=True,timeout=40,creationflags=0x08000000)
        except (OSError,subprocess.TimeoutExpired):
            raise ValidationError('Windows OCR 启动失败或超时，请复制文字导入。') from None
        if result.returncode:
            raise ValidationError('截图识别失败，请检查图片尺寸、文件格式和 Windows OCR 语言。')
        try: payload=json.loads(result.stdout.decode('utf-8-sig').strip())
        except (UnicodeDecodeError,ValueError): raise ValidationError('OCR 返回格式无效，请复制文字导入。') from None
        text=normalize_ocr(payload.get('text',''))
        if not text: raise ValidationError('截图中未识别到文字，请使用更清晰的截图。')
        return text,'windows-ocr/'+payload.get('language','')
