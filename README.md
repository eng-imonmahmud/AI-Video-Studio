# 🎬 AI Video Studio (V21.0 Advanced)

![Version](https://img.shields.io/badge/Version-v21.0--Advanced-blue?style=for-the-badge&logo=appveyor)
![Python](https://img.shields.io/badge/Python-3.12+-green?style=for-the-badge&logo=python)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Hardware_Accelerated-red?style=for-the-badge&logo=ffmpeg)
![License](https://img.shields.io/badge/License-MIT-orange?style=for-the-badge)

**AI Video Studio (V21.0 Advanced)** হলো একটি অল-ইন-ওয়ান অটোমেটেড ভিডিও প্রসেসিং এবং এডিটিং সফটওয়্যার। এটি কৃত্রিম বুদ্ধিমত্তা (AI), OpenAI Whisper টান্সক্রিপশন, Pexels API মিডিয়া সার্চ এবং FFmpeg হার্ডওয়্যার অ্যাক্সিলারেশন ব্যবহার করে মাত্র কয়েক ক্লিকে ভয়েসওভার থেকে চমৎকার ভিডিও তৈরি করতে পারে।

---

## ✨ প্রধান বৈশিষ্ট্যসমূহ (Key Features)

### 🤖 Multi-LLM AI Integration
- **Local AI (Ollama)**: Llama 3.2 সম্পূর্ণ অফলাইনে চালনা করার সুবিধা।
- **Google Gemini**: Gemini 3.1 Pro/Flash, Gemini 2.5 Pro/Flash, Gemini 2.0 Flash প্রোভাইডার সাপোর্ট।
- **OpenAI**: GPT-5.5, GPT-5.4, GPT-5 Mini ও অন্যান্য ফ্ল্যাগশিপ মডেল।
- **OpenRouter**: DeepSeek V4, Trinity, Gemma 4, Qwen3 Coder, Nemotron এবং অন্যান্য ফ্রি/পেইড মডেল।
- **Vertex AI**: এন্টারপ্রাইজ গ্রেড Google Cloud AI সাপোর্ট।

### 🎥 ভিডিও প্রসেসিং ও এফেক্টস (Video Processing & FX)
- **Automatic Stock Media**: ভয়েসওভার বা স্ক্রিপ্টের সাথে সামঞ্জস্য রেখে Pexels API থেকে স্বয়ংক্রিয় এইচডি ভিডিও ও ছবি ডাউনলোড।
- **Whisper Subtitles**: OpenAI Whisper ব্যবহার করে শতভাগ নিখুঁত সাবটাইটেল জেনারেশন।
- **Ken Burns Effect**: স্থির ছবিতে ডাইনামিক প্যান এবং জুম অ্যাকশন।
- **Intro & Outro Handling**: ভিডিওর শুরুতে ইনট্রো এবং শেষে আউট্রো অটো-যুক্ত করার ব্যবস্থা।
- **Logo / Watermark Overlay**: লোগো ওয়াটারমার্ক পজিশনিং ও অপাসিটি (Opacity) কন্ট্রোল।
- **Background Music Mixing**: ভয়েসওভারের সাথে ব্যাকগ্রাউন্ড মিউজিক অ্যাডজাস্টেবল ভলিউমে ব্লেন্ডিং।
- **Disclaimer Overlay**: AI-জেনারেটেড বা কাস্টম ডিসক্লেইমার ব্যাকগ্রাউন্ড ভিডিও/ইমেজ সাপোর্ট।

### ⚡ হার্ডওয়্যার অ্যাক্সিলারেশন (Hardware Acceleration)
- **Nvidia NVENC** (`h264_nvenc`)
- **Intel QSV** (`h264_qsv`, `hevc_qsv`, `av1_qsv`, `vp9_qsv`, `mpeg2_qsv`)
- **AMD AMF** (`h264_amf`)
- **Apple VideoToolbox** (`h264_videotoolbox`)
- **CPU Multithreading** (`libx264`)

### 📐 রেজোলিউশন ও ফরম্যাট সাপোর্ট
- **1080p Full HD** (1920x1080)
- **4K Ultra HD** (3840x2160)
- **720p HD** (1280x720)
- **Square** (1080x1080 - Instagram/Facebook)
- **Portrait** (1080x1920 - YouTube Shorts / TikTok / Reels)

---

## 📁 ডিরেকটরি স্ট্রাকচার (Directory Structure)

```text
AI_Video_Studio/
├── mainuniversal.py              # সফটওয়্যারের মূল সোর্স কোড (CustomTkinter GUI)
├── AI_Video_Studio_(V21.0).exe   # Standalone Windows Executable (Releases-এ প্রাপ্ত)
├── Font/                         # কাস্টম ফন্ট ফাইলসমূহ (Arial, DejaVu, Nirmala ইত্যাদি)
├── ImageMagick/                  # ইমেজ প্রসেসিং হেল্পার
├── Input/                        # ইনপুট ভয়েসওভার ও অডিও ফাইলসমূহ (.mp3, .wav, .m4a)
├── Output/                       # রেন্ডার হওয়া চূড়ান্ত ভিডিও ফাইলসমূহ
├── Tempdata/                     # প্রসেসিং সাময়িক ডাটা ও ডাউনলোড ক্যাশ
├── BackgroundMusic/              # ব্যাকগ্রাউন্ড মিউজিক ট্র্যাক
├── DisclaimerBackground/         # ডিসক্লেইমার ব্যাকগ্রাউন্ড ভিডিও/ছবি
├── Logo/                         # ওয়াটারমার্ক বা লোগো ফাইল
├── Intro/                        # ইনট্রো ভিডিও
├── Outro/                        # আউট্রো ভিডিও
├── PexelsAPI/                    # API কী ও সেটিংস কনফিগারেশন
└── README.md                     # প্রজেক্ট ডকুমেন্টেশন
```

---

## 🚀 ইনস্টলেশন ও ব্যবহার বিধি (Setup & Usage)

### অপশন ১: সরাসরি এক্সিকিউটেবল (.exe) রান করা (সুপারিশকৃত)
1. GitHub-এর [Releases Tab](https://github.com/eng-imonmahmud/AI-Video-Studio/releases) থেকে `AI_Video_Studio_(V21.0).exe` টি ডাউনলোড করুন।
2. `.exe` ফাইলটি রান করুন (কোনো Python ইনস্টলেশনের প্রয়োজন নেই)।

### অপশন ২: সোর্স কোড থেকে রান করা
1. এই রিপ্রজেটরি ক্লোন করুন:
   ```bash
   git clone https://github.com/eng-imonmahmud/AI-Video-Studio.git
   cd AI-Video-Studio
   ```
2. প্রয়োজনীয় ডিপেন্ডেন্সি ইনস্টল করুন:
   ```bash
   pip install customtkinter pillow requests openai-whisper google-genai openai urllib3
   ```
3. অ্যাপ্লিকেশনটি চালু করুন:
   ```bash
   python mainuniversal.py
   ```

---

## 👨‍💻 ডেভলপার তথ্য (Developer Information)

- **ডেভলপার**: Imon Mahmud
- **ইমেল**: [imon.mahmud.official@hotmail.com](mailto:imon.mahmud.official@hotmail.com)
- **ভার্সন**: V21.0 Advanced

---

## 📄 লাইসেন্স (License)

এই প্রজেক্টটি MIT লাইসেন্সের অধীনে প্রকাশিত। বিস্তারিত জানতে `LICENSE` ফাইল দেখুন।
