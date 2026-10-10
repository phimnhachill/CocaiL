import os
import json
import glob
import subprocess
from datetime import datetime
import requests
from google import genai

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_GACHA")
HISTORY_FILE = "database/stream_history.json"
WEEKLY_FILE = "database/current_week.json"

CHANNELS = [
    {"name": "Phúc ZOLA", "url": "https://www.youtube.com/@PhucZOLA/videos"},
    {"name": "Vumino", "url": "https://www.youtube.com/@vumino/videos"},
    {"name": "Học Sinh Mới", "url": "https://www.youtube.com/@hocsinhmoi/videos"}
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
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "-I", "1:3",
        "--print", "%(id)s:::%(title)s:::%(webpage_url)s",
        channel_url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        videos = []
        for line in res.stdout.strip().split("\n"):
            if ":::" in line:
                vid, title, url = line.split(":::", 2)
                videos.append({"id": vid.strip(), "title": title.strip(), "url": url.strip()})
        return videos
    except Exception as e:
        print(f"Lỗi lấy video từ {channel_url}: {e}")
        return []

def extract_content(video_url, video_id):
    sub_prefix = f"/tmp/sub_{video_id}"
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--sub-lang", "vi,en",
        "--skip-download",
        "--output", sub_prefix,
        video_url
    ]
    subprocess.run(cmd, capture_output=True, text=True)

    text_content = ""
    sub_files = glob.glob(f"{sub_prefix}*.vtt")
    if sub_files:
        try:
            with open(sub_files[0], "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if not line.startswith(("WEBVTT", "-->", "<")) and line.strip()]
                text_content = " ".join(lines[-4000:])
        except Exception:
            pass

    return text_content[:15000]

def analyze_with_gemini(creator, title, content):
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = f"""
    Bạn là chuyên gia trinh sát tỷ lệ đập thẻ và mở thẻ game FC Online Việt Nam.
    Dưới đây là thông tin buổi stream/video từ YouTuber {creator}:
    - Tiêu đề: {title}
    - Dữ liệu âm thanh/hội thoại bóc tách:
    {content if content else "(Không có transcript chi tiết, hãy phân tích dựa trên tiêu đề và hành vi đặc trưng)"}

    Hãy bóc tách thành bản báo cáo tình báo ngắn gọn theo định dạng:
    1. 🎰 **Tỷ Lệ Mở Gói / Gacha**: (Các gói được mở, tỷ lệ nhả phôi, nổ bom tấn hay xịt)
    2. 🔨 **Bóc Mẽ Bài Đập Thẻ**: (Mốc phôi +5, +7, +8; có dùng phôi mồi không; mồi xịt mấy cây; tỷ lệ thành công)
    3. 💰 **Thiệt Hại & Kinh Tế**: (Tổng kết buổi stream Lời hay Lỗ bao nhiêu BP/tiền mặt)
    4. ⚠️ **Cảnh Báo Cho Người Chơi**: (Đánh giá game hôm nay có đang nhả đồ không, có nên nạp/đập lúc này không)
    """

    candidates = [
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.7-flash"
    ]
    
    try:
        available = [m.name.replace("models/", "") for m in client.models.list()]
        for c in candidates:
            if c in available:
                res = client.models.generate_content(model=c, contents=prompt)
                print(f"-> Phân tích thành công bằng model: {c}")
                return res.text
    except Exception:
        pass

    for c in candidates:
        try:
            res = client.models.generate_content(model=c, contents=prompt)
            print(f"-> Phân tích thành công bằng model: {c}")
            return res.text
        except Exception:
            continue

    raise Exception("Không thể gọi Gemini API.")

def send_discord(creator, title, url, report):
    embed = {
        "title": f"🔥 [TRINH SÁT GACHA & ĐẬP THẺ] {creator}",
        "url": url,
        "description": report[:4000],
        "color": 15158332,
        "footer": {
            "text": "FC Online VN Intelligence • Tự động trinh sát bởi Gemini"
        }
    }
    res = requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]})
    if res.status_code == 204:
        print(f"-> Đã gửi thành công lên Discord: {title}")
    else:
        print(f"-> Lỗi gửi Discord: {res.status_code} - {res.text}")

def main():
    history = load_json(HISTORY_FILE)
    weekly_data = load_json(WEEKLY_FILE)
    new_history = list(history)

    for ch in CHANNELS:
        print(f"Đang quét kênh: {ch['name']}...")
        videos = get_channel_videos(ch["url"])

        for vid in videos:
            if vid["id"] not in history:
                print(f"Phát hiện video mới từ {ch['name']}: {vid['title']}")
                content = extract_content(vid["url"], vid["id"])
                try:
                    report = analyze_with_gemini(ch["name"], vid["title"], content)
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
                    print(f"Lỗi phân tích video {vid['id']}: {e}")

    save_json(HISTORY_FILE, new_history)
    save_json(WEEKLY_FILE, weekly_data)

if __name__ == "__main__":
    main()
