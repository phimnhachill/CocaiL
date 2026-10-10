import os
import json
import feedparser
import requests
from google import genai

# Lấy các biến bí mật từ môi trường GitHub Secrets
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_META")
HISTORY_FILE = "database/meta_history.json"

# Danh sách kênh Meta Hàn Quốc
CHANNELS = [
    {
        "name": "Nexon FC Online Official",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC9otskL_kd-0CDib_5Lj-mQ"
    },
    {
        "name": "Shin Bo-seok Meta KR",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCY5Xbo2lSFqdDQGZJTXfFZA"
    }
]

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def summarize_with_gemini(title, description):
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = f"""
    Bạn là chuyên gia phân tích meta FC Online.
    Dưới đây là thông tin video mới từ máy chủ Nexon Hàn Quốc:
    - Tiêu đề: {title}
    - Mô tả: {description}

    Nhiệm vụ:
    1. Dịch tiêu đề sang tiếng Việt chuẩn thuật ngữ game FC Online.
    2. Tóm tắt nội dung chính trong 3-4 gạch đầu dòng (thay đổi gameplay, sút ZD, tạt bóng, mùa thẻ mới, hoặc lịch bảo trì).
    3. Đưa ra 1 lời khuyên ngắn gọn cho game thủ Việt Nam.

    Xuất định dạng Markdown ngắn gọn, súc tích.
    """
    
    # Sử dụng model Gemini Pro mới nhất
    response = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=prompt
    )
    return response.text

def send_discord(channel_name, video_title, video_url, summary):
    embed = {
        "title": f"🚨 [TIN META HÀN] {channel_name}",
        "url": video_url,
        "description": summary,
        "color": 3447003,  # Màu xanh radar
        "footer": {
            "text": "FC Online KR Intelligence Bot • Phân tích bởi Gemini Pro"
        }
    }
    payload = {"embeds": [embed]}
    res = requests.post(DISCORD_WEBHOOK, json=payload)
    if res.status_code == 204:
        print(f"-> Đã gửi thành công lên Discord: {video_title}")
    else:
        print(f"-> Lỗi gửi Discord: {res.status_code} - {res.text}")

def main():
    history = load_history()
    new_history = list(history)

    for ch in CHANNELS:
        feed = feedparser.parse(ch["url"])
        if not feed.entries:
            continue

        latest_entry = feed.entries[0]
        video_id = latest_entry.yt_videoid
        video_url = latest_entry.link
        video_title = latest_entry.title
        video_desc = getattr(latest_entry, "summary", "")

        # Kiểm tra xem video này đã xử lý chưa
        if video_id not in history:
            print(f"Phát hiện video mới từ {ch['name']}: {video_title}")
            try:
                summary = summarize_with_gemini(video_title, video_desc)
                send_discord(ch["name"], video_title, video_url, summary)
                new_history.append(video_id)
            except Exception as e:
                print(f"Lỗi xử lý video {video_id}: {e}")

    save_history(new_history)

if __name__ == "__main__":
    main()
