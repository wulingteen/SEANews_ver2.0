"""
Excel 生成服務
從新聞文件內容中解析新聞列表並生成 Excel 報告
"""
import os
import re
from datetime import datetime
from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter


def parse_news_from_content(content: str) -> List[Dict[str, str]]:
    """
    從文件內容中解析新聞列表
    預期格式：Markdown 格式，包含新聞標題、時間、摘要、連結等資訊
    
    Args:
        content: 文件內容（Markdown 格式）
        
    Returns:
        新聞列表，每個元素包含 title, date, summary, link
    """
    news_items = []
    
    # 嘗試多種解析策略
    # 策略 1: 按連結分割（每個新聞通常有一個 URL）
    url_pattern = r'(https?://[^\s\)]+)'
    parts = re.split(url_pattern, content)
    
    current_news = {}
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        
        # 如果是 URL
        if re.match(url_pattern, part):
            if current_news.get('title'):
                current_news['link'] = part
                news_items.append(current_news)
                current_news = {}
        else:
            # 提取標題（通常是 ### 或 ** 包圍）
            title_match = re.search(r'###?\s+(.+?)(?:\n|$)', part) or \
                         re.search(r'\*\*(.+?)\*\*', part)
            
            if title_match and not current_news.get('title'):
                current_news['title'] = title_match.group(1).strip()
                
                # 提取日期
                date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)', part)
                if date_match:
                    current_news['date'] = date_match.group(1)
                else:
                    current_news['date'] = ''
                
                # 提取摘要（移除標題和日期後的文字）
                summary_text = part
                if title_match:
                    summary_text = summary_text.replace(title_match.group(0), '')
                if date_match:
                    summary_text = summary_text.replace(date_match.group(0), '')
                
                # 清理 Markdown 格式
                summary_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', summary_text)
                summary_text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', summary_text)
                summary_text = re.sub(r'\*([^\*]+)\*', r'\1', summary_text)
                summary_text = re.sub(r'#+\s*', '', summary_text)
                summary_text = summary_text.strip()
                
                current_news['summary'] = summary_text[:500]  # 限制長度
                current_news['link'] = ''  # 待後續填入
    
    # 保存最後一個（如果沒有連結）
    if current_news.get('title') and current_news not in news_items:
        news_items.append(current_news)
    
    # 如果第一種策略失敗，嘗試簡單按段落分割
    if not news_items:
        sections = content.split('\n\n')
        for section in sections:
            section = section.strip()
            if not section or len(section) < 20:
                continue
            
            title_match = re.search(r'###?\s+(.+?)(?:\n|$)', section) or \
                         re.search(r'\*\*(.+?)\*\*', section)
            
            if title_match:
                news_item = {
                    'title': title_match.group(1).strip(),
                    'date': '',
                    'summary': section[:300],
                    'link': ''
                }
                
                # 提取日期
                date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)', section)
                if date_match:
                    news_item['date'] = date_match.group(1)
                
                # 提取連結
                link_match = re.search(r'(https?://[^\s\)]+)', section)
                if link_match:
                    news_item['link'] = link_match.group(1)
                
                news_items.append(news_item)
    
    return news_items


def generate_news_excel(
    document_name: str,
    document_content: str,
    output_dir: str = "exports"
) -> Dict[str, Any]:
    """
    從文件內容生成新聞 Excel 報告
    
    Args:
        document_name: 文件名稱
        document_content: 文件內容（包含新聞列表）
        output_dir: 輸出目錄
        
    Returns:
        包含 success, filepath, filename, count, news_items 的字典
    """
    try:
        # 確保輸出目錄存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 解析新聞列表
        news_items = parse_news_from_content(document_content)
        
        if not news_items:
            return {
                "success": False,
                "error": "未能從文件中解析出新聞項目"
            }
        
        # 創建 Excel 工作簿
        wb = Workbook()
        ws = wb.active
        ws.title = "新聞列表"
        
        # 設定標題行
        headers = ["編號", "新聞標題", "發布時間", "新聞摘要", "新聞連結"]
        ws.append(headers)
        
        # 設定標題樣式
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment
        
        # 填入新聞資料
        for idx, news in enumerate(news_items, start=1):
            ws.append([
                idx,
                news.get('title', ''),
                news.get('date', ''),
                news.get('summary', ''),
                news.get('link', '')
            ])
        
        # 設定欄寬
        column_widths = {
            'A': 8,   # 編號
            'B': 40,  # 標題
            'C': 15,  # 時間
            'D': 60,  # 摘要
            'E': 50   # 連結
        }
        
        for col, width in column_widths.items():
            ws.column_dimensions[col].width = width
        
        # 設定資料行樣式
        data_alignment = Alignment(vertical="top", wrap_text=True)
        for row in range(2, len(news_items) + 2):
            for col in range(1, len(headers) + 1):
                cell = ws.cell(row=row, column=col)
                cell.alignment = data_alignment
        
        # 凍結首行
        ws.freeze_panes = "A2"
        
        # 生成檔案名稱
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_doc_name = re.sub(r'[^\w\s-]', '', document_name)[:30]
        filename = f"新聞報告_{safe_doc_name}_{timestamp}.xlsx"
        filepath = os.path.join(output_dir, filename)
        
        # 儲存檔案
        wb.save(filepath)
        
        return {
            "success": True,
            "filepath": filepath,
            "filename": filename,
            "count": len(news_items),
            "news_items": news_items
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"生成 Excel 時發生錯誤: {str(e)}"
        }


def cleanup_old_exports(output_dir: str = "exports", max_age_days: int = 7):
    """
    清理超過指定天數的匯出檔案
    
    Args:
        output_dir: 輸出目錄
        max_age_days: 保留天數
    """
    try:
        if not os.path.exists(output_dir):
            return
        
        current_time = datetime.now()
        max_age_seconds = max_age_days * 24 * 60 * 60
        
        for filename in os.listdir(output_dir):
            filepath = os.path.join(output_dir, filename)
            
            if not os.path.isfile(filepath):
                continue
            
            # 檢查檔案年齡
            file_age = current_time.timestamp() - os.path.getmtime(filepath)
            
            if file_age > max_age_seconds:
                try:
                    os.remove(filepath)
                    print(f"已刪除舊檔案: {filename}")
                except Exception as e:
                    print(f"刪除檔案失敗 {filename}: {e}")
    
    except Exception as e:
        print(f"清理舊檔案時發生錯誤: {e}")
