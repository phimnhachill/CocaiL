import os
import json
import glob
import subprocess
import requests
import feedparser  # Đã bổ sung thư viện bắt buộc này
from google import genai

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_META")
HISTORY_FILE = "database/meta_history.json"

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

def extract_korean_subtitles(video_url, video_id):
    """Tải toàn bộ phụ đề lời thoại tiếng Hàn của video để phân tích chính xác"""
    sub_prefix = f"/tmp/meta_sub_{video_id}"
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--sub-lang", "ko",
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
                lines = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith(("WEBVTT", "-->", "<")) and line not in lines[-3:]:
                        lines.append(line)
                text_content = " ".join(lines)
        except Exception as e:
            print(f"Lỗi đọc file phụ đề: {e}")

    for f in sub_files:
        try:
            os.remove(f)
        except Exception:
            pass

    return text_content[:25000]

def analyze_meta_with_gemini(channel_name, title, description, transcript):
    client = genai.Client(api_key=GEMINI_KEY)
    
    prompt = f"""
    Bạn là chuyên gia phân tích meta, gameplay và thị trường chuyển nhượng FC Online hàng đầu.
    Dưới đây là dữ liệu video cập nhật mới từ máy chủ Nexon Hàn Quốc ({channel_name}):
    - Tiêu đề gốc: {title}
    - Mô tả: {description}
    - Lời thoại bóc tách từ video (Tiếng Hàn):
    {transcript if transcript else "(Không có phụ đề chi tiết, hãy phân tích dựa trên văn bản tiêu đề và mô tả)"}

    NHIỆM VỤ PHÂN TÍCH:
    1. 🎯 **Chủ Đề & Dịch Tiêu Đề**: Dịch tiêu đề sang tiếng Việt chuẩn thuật ngữ FC Online.
    2. ⚙️ **Chi Tiết Gameplay (BUFF / NERF)**:
       - Trích xuất từ lời thoại/mô tả xem cơ chế sút bóng (ZD, D chìm), chuyền bóng, tạt cánh, rê dắt thay đổi thế nào?
       - Trọng tài, AI phòng ngự, thủ môn được chỉnh sửa ra sao? (Tuyệt đối không tự bịa nếu không được nhắc đến).
    3. 🃏 **Mùa Thẻ Mới / Sự Kiện Nexon**:
       - Có công bố mùa thẻ mới, cầu thủ mới hay lịch bảo trì không?
    4. 💡 **Lời Khuyên Chiến Thuật Cho Server Việt Nam**:
       - Game thủ Việt Nam nên chuẩn bị phôi, đổi sơ đồ hay chuẩn bị đón đầu meta này như thế nào?

    Yêu cầu: Viết súc tích, đi thẳng vào số liệu và thuật ngữ in-game chuẩn xác.
    """

    candidates = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
    for c in candidates:
        try:
            res = client.models.generate_content(model=c, contents=prompt)
            return res.text
        except Exception:
            continue
    raise Exception("Không gọi được Gemini API")

def send_discord(channel_name, video_title, video_url, summary):
    embed = {
        "title": f"🚨 [TÌNH BÁO META HÀN] {channel_name}",
        "url": video_url,
        "description": summary[:4000],
        "color": 3447003,
        "footer": {
            "text": "FC Online KR Intelligence Radar • Tự động bóc tách từ tiếng Hàn"
        }
    }
    requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]})

def main():
    history = load_history()
    new_history = list(history)

    for ch in CHANNELS:
        print(f"Kiểm tra kênh: {ch['name']}...")
        feed = feedparser.parse(ch["url"])
        if not feed.entries:
            continue

        latest_entry = feed.entries[0]
        video_id = latest_entry.yt_videoid
        video_url = latest_entry.link
        video_title = latest_entry.title
        video_desc = getattr(latest_entry, "summary", "")

        if video_id not in history:
            print(f"Phát hiện video mới từ {ch['name']}: {video_title}")
            try:
                print("-> Đang kéo phụ đề tiếng Hàn...")
                transcript = extract_korean_subtitles(video_url, video_id)
                if transcript:
                    print(f"-> Đã lấy thành công lời thoại.")
                else:
                    print("-> Video không có phụ đề, phân tích theo mô tả.")

                summary = analyze_meta_with_gemini(ch["name"], video_title, video_desc, transcript)
                send_discord(ch["name"], video_title, video_url, summary)
                new_history.append(video_id)
            except Exception as e:
                print(f"Lỗi xử lý video {video_id}: {e}")

    save_history(new_history)

if __name__ == "__main__":
    main()
