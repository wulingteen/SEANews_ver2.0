"""
Email 發送服務
使用 SMTP 發送帶附件的郵件
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, List


def get_smtp_config() -> Dict[str, str]:
    """
    從環境變數獲取 SMTP 設定
    
    Returns:
        包含 SMTP 設定的字典
    """
    return {
        "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "email_address": os.getenv("EMAIL_ADDRESS", ""),
        "email_password": os.getenv("EMAIL_PASSWORD", ""),
    }


def send_email_with_attachment(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: str,
    attachment_name: str
) -> Dict[str, any]:
    """
    發送帶附件的郵件
    
    Args:
        to_email: 收件人郵箱
        subject: 郵件主旨
        body: 郵件內容（HTML 格式）
        attachment_path: 附件檔案路徑
        attachment_name: 附件檔案名稱
        
    Returns:
        包含 success 和 message/error 的字典
    """
    try:
        # 獲取 SMTP 設定
        config = get_smtp_config()
        
        if not config["email_address"] or not config["email_password"]:
            return {
                "success": False,
                "error": "未設定 SMTP 郵箱或密碼，請檢查 .env 檔案"
            }
        
        # 創建郵件對象
        msg = MIMEMultipart()
        msg['From'] = config["email_address"]
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # 添加郵件內容
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        # 添加附件
        if os.path.exists(attachment_path):
            print(f"📎 正在附加檔案: {attachment_path}")
            print(f"📎 檔案名稱: {attachment_name}")
            
            with open(attachment_path, 'rb') as f:
                part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                # 修正檔名格式（移除多餘空格）
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{attachment_name}"'
                )
                msg.attach(part)
                print(f"✅ 附件已加入郵件")
        else:
            print(f"❌ 附件檔案不存在: {attachment_path}")
            return {
                "success": False,
                "error": f"附件檔案不存在: {attachment_path}"
            }
        
        # 連接 SMTP 伺服器並發送
        print(f"🔌 連接 SMTP: {config['smtp_server']}:{config['smtp_port']}")
        
        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.starttls()
            print(f"🔐 登入郵箱: {config['email_address']}")
            server.login(config["email_address"], config["email_password"])
            print(f"📤 發送郵件至: {to_email}")
            server.send_message(msg)
            print(f"✅ 郵件發送成功")
        
        return {
            "success": True,
            "message": f"郵件已成功發送至 {to_email}"
        }
        
    except Exception as e:
        print(f"❌ 發送郵件時發生錯誤: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"發送郵件時發生錯誤: {str(e)}"
        }


def generate_news_report_html(document_name: str, news_items: List[Dict[str, str]]) -> str:
    """
    生成新聞報告的 HTML 郵件內容
    
    Args:
        document_name: 文件名稱
        news_items: 新聞項目列表，每個包含 title, date, summary, link
        
    Returns:
        HTML 格式的郵件內容
    """
    html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Microsoft JhengHei', Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #4472C4; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .news-item {{ margin-bottom: 25px; padding: 15px; border-left: 4px solid #4472C4; background-color: #f9f9f9; }}
            .news-title {{ font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 8px; }}
            .news-date {{ color: #7f8c8d; font-size: 14px; margin-bottom: 8px; }}
            .news-summary {{ color: #34495e; margin-bottom: 10px; }}
            .news-link {{ color: #3498db; text-decoration: none; }}
            .news-link:hover {{ text-decoration: underline; }}
            .footer {{ text-align: center; padding: 20px; color: #7f8c8d; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>東南亞新聞輿情報告</h1>
            <p>{document_name}</p>
        </div>
        <div class="content">
            <p>以下是本次搜尋到的 <strong>{len(news_items)}</strong> 筆新聞：</p>
    """
    
    for idx, news in enumerate(news_items, 1):
        title = news.get('title', '無標題')
        date = news.get('date', '')
        summary = news.get('summary', '無摘要')[:300]
        link = news.get('link', '')
        
        html += f"""
            <div class="news-item">
                <div class="news-title">{idx}. {title}</div>
                {f'<div class="news-date">發布時間：{date}</div>' if date else ''}
                <div class="news-summary">{summary}</div>
                {f'<div><a href="{link}" class="news-link" target="_blank">查看原文 →</a></div>' if link else ''}
            </div>
        """
    
    html += """
        </div>
        <div class="footer">
            <p>此報告由東南亞新聞輿情系統自動生成</p>
            <p>完整報告請參閱附件 Excel 檔案</p>
        </div>
    </body>
    </html>
    """
    
    return html
