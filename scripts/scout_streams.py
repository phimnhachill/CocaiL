import os
import json
import subprocess
from datetime import datetime
import requests
from google import genai

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_GACHA")
HISTORY_FILE = "database/stream_history.json"
WEEKLY_FILE = "database/current_week.json"

# Chuẩn hóa link chính xác 100% của 3 kênh YouTuber Việt Nam
CHANNELS = [
    {
        "name": "Phúc ZOLA",
        "url": "https://www.youtube.com/@phuc25zola/videos"
    },
    {
        "name": "Vumino",
        "url": "https://www.youtube.com/@vumino9620/videos"
    },
    {
        "name": "Học Sinh Mới",
        "url": "https://www.youtube.com/@H%E1%BB%8DcSinhM%E1%BB%9Bi/videos"
    }
]

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_channel_videos(channel_url):
    """Lấy video mới nhất, giữ nguyên tiêu đề tiếng Việt gốc"""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "-I", "1:2",
        "--extractor-args", "youtube:lang=vi",
        "--print", "%(id)s:::%(title)s:::%(webpage_url)s:::%(description)s",
        channel_url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        videos = []
        for line in res.stdout.strip().split("\n"):
            if ":::" in line:
                parts = line.split(":::", 3)
                videos.append({
                    "id": parts[0].strip(),
                    "title": parts[1].strip(),
                    "url": parts[2].strip(),
                    "desc": parts[3].strip() if len(parts) > 3 else ""
                })
        return videos
    except Exception as e:
        print(f"Lỗi lấy video từ {channel_url}: {e}")
        return []

def analyze_with_gemini(creator, title, description):
    client = genai.Client(api_key=GEMINI_KEY)
    
    # Prompt chặt chẽ: Cấm tuyệt đối bịa đặt số liệu
    prompt = f"""
    Bạn là hệ thống trinh sát FC Online Việt Nam chuyên ghi nhận lịch sử đập thẻ/mở gói.
    Dữ liệu thu thập từ video của streamer {creator}:
    - Tiêu đề video: {title}
    - Nội dung mô tả/thông tin đính kèm:
    {description[:2500] if description else "Không có mô tả chi tiết."}

    QUY TẮC BẮT BUỘC (TUÂN THỦ 100%):
    1. TUYỆT ĐỐI KHÔNG TỰ BỊA ĐẶT số lượng phôi mồi, số BP lời/lỗ hoặc tỷ lệ % nếu trong tiêu đề và mô tả không ghi rõ con số đó.
    2. Nếu trong nội dung có số liệu cụ thể (ví dụ: mở bao nhiêu gói, nổ con gì, đập mốc + mấy lên hay xịt), hãy liệt kê chính xác.
    3. Nếu KHÔNG CÓ số liệu chi tiết, ghi rõ: "⚠️ Streamer không ghi kèm nhật ký số liệu cụ thể cho buổi này."

    Xuất báo cáo theo cấu trúc sau:
    🎯 **Kèo Trọng Điểm**: (Tên các thẻ cầu thủ, mốc cấp thẻ +X được nhắc đến ở tiêu đề/mô tả)
    📊 **Dữ Liệu Bóc Tách Được**: (Chỉ ghi số liệu thực tế được xác nhận, không suy đoán)
    📌 **Ghi Chú Trinh Sát**: (Tóm tắt ngắn gọn nội dung video thể hiện)
    """

    candidates = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
    for c in candidates:
        try:
            res = client.models.generate_content(model=c, contents=prompt)
            return res.text
        except Exception:
            continue
    raise Exception("Lỗi gọi Gemini API")

def send_discord(creator, title, url, report):
    embed = {
        "title": f"🔥 [{creator}] {title}",
        "url": url,
        "description": report[:3900],
        "color": 15158332,
        "footer": {
            "text": "FC Online VN Radar • Trinh sát thực tế"
        }
    }
    requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]})

def main():
    history = load_json(HISTORY_FILE)
    weekly_data = load_json(WEEKLY_FILE)
    new_history = list(history)

    for ch in CHANNELS:
        print(f"Quét kênh: {ch['name']}...")
        videos = get_channel_videos(ch["url"])

        for vid in videos:
            if vid["id"] not in history:
                print(f"Phát hiện video mới từ {ch['name']}: {vid['title']}")
                try:
                    report = analyze_with_gemini(ch["name"], vid["title"], vid["desc"])
                    send_discord(ch["name"], vid["title"], vid["url"], report)

                    new_history.append(vid["id"])
                    weekly_data.append({
                        "id": vid["id"],
                        "creator": ch["name"],
                        "title": vid["title"],
                        "url": vid["url"],
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "report": report
                    })
                except Exception as e:
                    print(f"Lỗi: {e}")

    save_json(HISTORY_FILE, new_history)
    save_json(WEEKLY_FILE, weekly_data)

if __name__ == "__main__":
    main()
