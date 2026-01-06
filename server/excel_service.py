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
    預期格式：Markdown 格式，標題為 ###，後接發布時間、摘要和 URL（用反引號包裹）
    
    Args:
        content: 文件內容（Markdown 格式）
        
    Returns:
        新聞列表，每個元素包含 title, date, summary, link
    """
    news_items = []
    
    # 先移除文末的總結區塊（通常以 "## 摘要" 或 "## 期間重點" 等開頭）
    # 這些區塊會干擾最後一則新聞的摘要提取
    summary_section_pattern = r'\n##\s+(摘要|期間重點|覆蓋度|缺口|後續建議|Credit Memo).*$'
    content = re.sub(summary_section_pattern, '', content, flags=re.DOTALL)
    
    # 按 ### 標題分割新聞項目
    sections = re.split(r'\n###\s+', content)
    
    for section in sections:
        section = section.strip()
        if not section or len(section) < 20:
            continue
        
        # 跳過非新聞標題（如 "回覆重點"、"越南（Vietnam）" 等國家標題）
        first_line = section.split('\n')[0].strip()
        if any(keyword in first_line for keyword in ['回覆重點', '越南', '泰國', '印尼', '菲律賓', '柬埔寨', 'Vietnam', 'Thailand', 'Indonesia', 'Philippines', 'Cambodia']):
            continue
        if first_line.startswith('#') or first_line.startswith('【'):
            continue
        
        news_item = {
            'title': '',
            'date': '',
            'summary': '',
            'link': ''
        }
        
        # 提取標題（第一行）
        lines = section.split('\n')
        if lines:
            news_item['title'] = lines[0].strip()
        
        # 提取發布時間（格式：發布時間：YYYY-MM-DD 或其他日期格式）
        date_pattern = r'發布時間[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)'
        date_match = re.search(date_pattern, section)
        if date_match:
            news_item['date'] = date_match.group(1).replace('年', '-').replace('月', '-').replace('日', '')
        
        # 提取連結（用反引號包裹的 URL，格式：`https://...`）
        link_pattern = r'`(https?://[^`]+)`'
        link_match = re.search(link_pattern, section)
        if link_match:
            news_item['link'] = link_match.group(1).strip()
        else:
            # 嘗試提取未用反引號包裹的 URL
            plain_link_match = re.search(r'(https?://[^\s\)]+)', section)
            if plain_link_match:
                news_item['link'] = plain_link_match.group(1).strip()
        
        # 提取摘要（移除標題、日期、URL 後的文字）
        summary_text = section
        
        # 移除標題行
        if lines:
            summary_text = '\n'.join(lines[1:])
        
        # 移除發布時間行
        summary_text = re.sub(r'發布時間[：:][^\n]+', '', summary_text)
        
        # 移除分隔線和後續的國家標題（如 "---\n## 泰國"）
        summary_text = re.sub(r'---+.*$', '', summary_text, flags=re.DOTALL)
        
        # 移除 Markdown 連結格式（如 [text](url)，包括不完整的）
        summary_text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', summary_text)
        # 移除殘留的不完整連結格式
        summary_text = re.sub(r'\([^\)]*https?://[^\)]*\)', '', summary_text)
        summary_text = re.sub(r'\[[^\]]*\]', '', summary_text)
        
        # 移除 URL（包括反引號包裹的和普通的）
        summary_text = re.sub(r'`https?://[^`]+`', '', summary_text)
        summary_text = re.sub(r'https?://[^\s]+', '', summary_text)
        
        # 移除 Markdown 標題符號
        summary_text = re.sub(r'#+\s*', '', summary_text)
        
        # 清理多餘的括號
        summary_text = re.sub(r'\(\s*\)', '', summary_text)
        
        # 清理多餘空白和換行
        summary_text = re.sub(r'\n+', ' ', summary_text)
        summary_text = re.sub(r'\s+', ' ', summary_text)
        summary_text = summary_text.strip()
        
        news_item['summary'] = summary_text[:500] if summary_text else ''
        
        # 只有標題和摘要都存在時才加入列表
        if news_item['title'] and news_item['summary']:
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
