# file_parser - 文件解析

## 概述

`file_parser.py` 提供本地文件的文本提取能力，支持 PDF、Word、PowerPoint、Excel、纯文本和代码文件等多种格式。所有方法均为 `FileParser` 类的静态方法。

## 核心类

### FileParser

纯静态方法集合，不维护状态。

```python
class FileParser:
    @staticmethod
    def parse_file(file_path, filename=None, max_chars=50000)
    @staticmethod
    def get_parser_type(filename)
    @staticmethod
    def get_file_metadata(file_path, filename=None)
    @staticmethod
    def is_code_file(filename)
```

## 支持格式

| 格式 | 解析类型 | 后端库 |
|------|----------|--------|
| .pdf | pdf | pdfplumber（主），PyPDF2（备） |
| .docx, .doc | docx | python-docx |
| .pptx, .ppt | pptx | python-pptx |
| .xlsx, .xls | excel | openpyxl |
| .txt, .csv, .md, .rtf | txt / csv / markdown / rtf | 文本读取 |
| .py, .js, .ts, .java, .go, .rs, ... | code | 文本读取（共 50+ 种扩展名） |

## 方法说明

### parse_file(file_path, filename, max_chars)

解析文件并提取文本内容。自动检测文件类型，调用对应的解析器。

```python
result = FileParser.parse_file("report.pdf")
# → {"success": True, "content": "...", "type": "pdf", "pages": 12, ...}
```

返回字段：`success`, `content`, `filename`, `type`, `original_length`, `extracted_length`, `truncated`, `file_size`，格式特定字段（pages / paragraphs / slides / sheets）。

失败返回 `{"success": False, "error": "..."}`。

### get_parser_type(filename)

返回文件的解析类型：`code` / `pdf` / `docx` / `pptx` / `excel` / `txt` / `unsupported`。

### get_file_metadata(file_path, filename)

不解析全文，快速获取文件元信息。

```python
meta = FileParser.get_file_metadata("presentation.pptx")
# → {"success": True, "filename": "...", "type": "pptx",
#     "extension": ".pptx", "size": 204800, "size_str": "200.0 KB",
#     "slides": 15}
```

## 解析器内部实现

- **PDF** - 逐页提取文本，页间用 `[第 N/M 页]` 分隔，超限提前截断
- **DOCX** - 提取段落文本和表格内容（`[表格内容]` 标记），先验证 zip 结构
- **PPTX** - 逐幻灯片提取标题和文本框内容
- **Excel** - 逐工作表提取单元格值（`|` 分隔），每表最多 1000 行
- **代码/文本** - UTF-8 读取，`max_chars` 截断

## 全局单例

```python
from nbot.core.file_parser import file_parser

result = file_parser.parse_file("data.xlsx")
```

## 设计原则

1. **轻量依赖** - 按需导入后端库，缺失时返回明确错误
2. **安全截断** - 所有解析器受 `max_chars`（默认 50000）保护
3. **统一格式** - 解析结果使用一致的结构化字典
4. **代码优先** - 代码文件使用纯文本解析而非文档解析器
