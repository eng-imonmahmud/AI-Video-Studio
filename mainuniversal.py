import os
import sys
import shutil
import customtkinter as ctk
from tkinter import filedialog, messagebox, END
import threading
import json
import time
import requests
import warnings
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
import gc
import multiprocessing
import subprocess
import re
import hashlib
import traceback
import textwrap
import random
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import datetime

# --- MONKEY PATCH SUBPROCESS FOR WINDOWS ---
# This prevents CMD windows from popping up whenever FFmpeg or other tools are called internally by libraries (like Whisper)
if os.name == 'nt':
    _original_popen = subprocess.Popen
    class NoWindowPopen(_original_popen):
        def __init__(self, *args, **kwargs):
            if 'creationflags' not in kwargs:
                kwargs['creationflags'] = 0x08000000 # CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)
    subprocess.Popen = NoWindowPopen

# Conditional import for missing Whisper/OpenAI/GenAI packages gracefully
HAS_WHISPER = False
try:
    import whisper
    from whisper.utils import get_writer
    HAS_WHISPER = True
except ImportError:
    print("WARNING: 'openai-whisper' not found. Transcription will fail.")

HAS_GENAI = False
try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    pass

HAS_OPENAI = False
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    pass

# --- 1. CRITICAL: PATH & ENV SETUP ---
def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    # add MEIPASS to PATH explicitly for ffmpeg subprocess calls to find binaries
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")
else:
    BASE_DIR = os.path.abspath(".")

DIR_FONT = get_resource_path("Font") 
imagemagick_folder = get_resource_path("ImageMagick")
if os.name == 'nt':
    magick_exe = os.path.join(imagemagick_folder, "magick.exe")
    ffmpeg_path = get_resource_path("ffmpeg.exe") 
else:
    local_magick = os.path.join(imagemagick_folder, "magick")
    magick_exe = local_magick if os.path.exists(local_magick) else (shutil.which("magick") or shutil.which("convert") or "magick")
    local_ffmpeg = get_resource_path("ffmpeg")
    ffmpeg_path = local_ffmpeg if os.path.exists(local_ffmpeg) else (shutil.which("ffmpeg") or "ffmpeg")

os.environ["IMAGEMAGICK_BINARY"] = magick_exe
os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path

if os.path.exists(ffmpeg_path):
    if os.name != 'nt':
        try:
            os.chmod(ffmpeg_path, 0o755)
        except Exception:
            pass
    ffmpeg_dir = os.path.dirname(os.path.abspath(ffmpeg_path))
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

# Track active subprocesses to forcefully kill
active_processes = []
active_pool = None

# --- CONSTANTS & PROVIDERS ---
try:
    TOTAL_SYS_THREADS = multiprocessing.cpu_count()
    MAX_CONCURRENT_FFMPEG = max(4, int(TOTAL_SYS_THREADS * 0.75)) 
except:
    MAX_CONCURRENT_FFMPEG = 8

DIR_INPUT = os.path.join(BASE_DIR, "Input")
DIR_OUTPUT = os.path.join(BASE_DIR, "Output")
DIR_TEMP = os.path.join(BASE_DIR, "Tempdata")
DIR_API = os.path.join(BASE_DIR, "PexelsAPI")
DIR_LOGO = os.path.join(BASE_DIR, "Logo")
DIR_MUSIC = os.path.join(BASE_DIR, "BackgroundMusic")
DIR_DISCLAIMER = os.path.join(BASE_DIR, "DisclaimerBackground")
DIR_INTRO = os.path.join(BASE_DIR, "Intro")
DIR_OUTRO = os.path.join(BASE_DIR, "Outro")

CONFIG_FILE = os.path.join(DIR_API, "settings.json")

RESOLUTIONS = {
    "1080p (1920x1080)": (1920, 1080),
    "4K (3840x2160)": (3840, 2160),
    "720p (1280x720)": (1280, 720),
    "Square (1080x1080)": (1080, 1080),
    "Portrait (1080x1920)": (1080, 1920)
}

ENCODERS = {
    "libx264 (CPU)": ["libx264", ["-preset", "ultrafast"]],
    "NVENC (Nvidia)": ["h264_nvenc", ["-preset", "p4"]],
    "AMF (AMD)": ["h264_amf", ["-usage", "transcoding"]],
    "QSV h264 (Intel)": ["h264_qsv", ["-preset", "fast"]],
    "QSV hevc (Intel)": ["hevc_qsv", ["-preset", "fast"]],
    "QSV av1 (Intel)": ["av1_qsv", ["-preset", "fast"]],
    "QSV mpeg2 (Intel)": ["mpeg2_qsv", ["-preset", "fast"]],
    "QSV vp9 (Intel)": ["vp9_qsv", ["-preset", "fast"]],
    "VideoToolbox (Mac)": ["h264_videotoolbox", []]
}

MODELS = {
    "Local AI (Ollama)": {"llama3.2": "llama3.2"},
    "Gemini": {
        "Gemini 3.1 Pro Preview": "gemini-3.1-pro-preview",
        "Gemini 3.1 Flash Lite": "gemini-3.1-flash-lite",
        "Gemini 3.1 Flash Lite Preview": "gemini-3.1-flash-lite-preview",
        "Gemini 3 Pro Preview": "gemini-3-pro-preview",
        "Gemini 3 Flash Preview": "gemini-3-flash-preview",
        "Gemini 2.5 Pro": "gemini-2.5-pro",
        "Gemini 2.5 Flash": "gemini-2.5-flash",
        "Gemini 2.5 Flash Preview": "gemini-2.5-flash-preview",
        "Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite",
        "Gemini 2.5 Flash Lite Preview": "gemini-2.5-flash-lite-preview",
        "Gemini 2.0 Flash": "gemini-2.0-flash",
        "Gemini 2.0 Flash Lite": "gemini-2.0-flash-lite"
    },
    "Vertex AI": {
        "Gemini 3.1 Pro Preview": "gemini-3.1-pro-preview",
        "Gemini 3.1 Flash Lite": "gemini-3.1-flash-lite",
        "Gemini 3.1 Flash Lite Preview": "gemini-3.1-flash-lite-preview",
        "Gemini 3 Pro Preview": "gemini-3-pro-preview",
        "Gemini 3 Flash Preview": "gemini-3-flash-preview",
        "Gemini 2.5 Pro": "gemini-2.5-pro",
        "Gemini 2.5 Flash": "gemini-2.5-flash",
        "Gemini 2.5 Flash Preview": "gemini-2.5-flash-preview",
        "Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite",
        "Gemini 2.5 Flash Lite Preview": "gemini-2.5-flash-lite-preview",
        "Gemini 2.0 Flash": "gemini-2.0-flash",
        "Gemini 2.0 Flash Lite": "gemini-2.0-flash-lite"
    },
    "OpenAI": {
        "GPT 5.5": "gpt-5.5",
        "GPT 5.5 Pro": "gpt-5.5-pro",
        "GPT 5.4": "gpt-5.4",
        "GPT 5.4 Pro": "gpt-5.4-pro",
        "GPT 5.4 Mini": "gpt-5.4-mini",
        "GPT 5.4 Nano": "gpt-5.4-nano",
        "GPT 5 Mini": "gpt-5-mini",
        "GPT 5 Nano": "gpt-5-nano",
        "GPT 5": "gpt-5",
        "GPT 4.1": "gpt-4.1"
    },
    "OpenRouter": {
        "Trinity Large Thinking": "arcee-ai/trinity-large-thinking:free",
        "DeepSeek V4 Flash": "deepseek/deepseek-v4-flash:free",
        "Gemma 4 26B A4B": "google/gemma-4-26b-a4b-it:free",
        "Gemma 4 31B": "google/gemma-4-31b-it:free",
        "Llama 3.2 3B Instruct": "meta-llama/llama-3.2-3b-instruct:free",
        "Llama 3.3 70B Instruct": "meta-llama/llama-3.3-70b-instruct:free",
        "MiniMax M2.5": "minimax/minimax-m2.5:free",
        "Hermes 3 405B Instruct": "nousresearch/hermes-3-llama-3.1-405b:free",
        "Nemotron 3 Nano 30B": "nvidia/nemotron-3-nano-30b-a3b:free",
        "Nemotron 3 Super": "nvidia/nemotron-3-super-120b-a12b:free",
        "Nemotron Nano 9B V2": "nvidia/nemotron-nano-9b-v2:free",
        "GPT OSS 120B": "openai/gpt-oss-120b:free",
        "GPT OSS 20B": "openai/gpt-oss-20b:free",
        "Qwen3 Coder": "qwen/qwen3-coder:free",
        "Qwen3 Next 80B Instruct": "qwen/qwen3-next-80b-a3b-instruct:free",
        "GLM 4.5 Air": "z-ai/glm-4.5-air:free"
    }
}

DEFAULT_MODELS = {
    "Local AI (Ollama)": "llama3.2",
    "Gemini": "Gemini 2.5 Flash",
    "Vertex AI": "Gemini 2.5 Flash",
    "OpenAI": "GPT 5.4 Mini",
    "OpenRouter": "Gemma 4 31B"
}

class GUILogger:
    def __init__(self, log_func):
        self.log_func = log_func

    def write(self, message):
        # tqdm uses \r to return to the start of the line
        if '\r' in message:
            msg = message.replace('\r', '').strip()
            if msg:
                self.log_func(msg, replace=True)
        else:
            if message.strip():
                self.log_func(message.strip(), replace=False)

    def flush(self): pass
    def isatty(self): return False

class VideoBatchEditor(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.init_folders()
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        
        self.title("AI Video Studio (V21.0 Advanced)")
        self.geometry("1400x950") 
        ctk.set_appearance_mode("Dark")
        
        self.audio_files = []
        self.bg_music_files = []
        self.logo_path = ""
        self.disclaimer_bg_path = ""
        self.intro_path = ""
        self.outro_path = ""
        self.vertex_credits = ""
        self.pexels_api_keys = []
        
        self.loaded_whisper_model = None
        self.is_processing = False
        self.stop_event = threading.Event()
        self.completed_projects = 0
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Load Defaults
        self.settings = self.load_settings()
        self.create_gui()
        self.preload_assets()
        
        sys.stdout = GUILogger(self.safe_log)
        sys.stderr = GUILogger(self.safe_log)

    def on_closing(self):
        self.save_settings()
        self.destroy()

    def init_folders(self):
        folders = [DIR_INPUT, DIR_OUTPUT, DIR_TEMP, DIR_API, DIR_LOGO, DIR_MUSIC, DIR_DISCLAIMER, DIR_FONT, DIR_INTRO, DIR_OUTRO]
        for folder in folders:
            if not os.path.exists(folder): os.makedirs(folder)

    def load_settings(self):
        default = {
            "api_keys": "", "resolution": "1080p (1920x1080)", "bg_volume": 0.1,
            "disclaimer_mode": "Online (AI)", "ai_provider": "Local AI (Ollama)", "encoder": "libx264 (CPU)",
            "ai_api_key": "http://127.0.0.1:11434/api/chat", "ai_model": "llama3.2",
            
            # Toggles defaults to False
            "tg_ai_trans": False,
            "tg_adv_sub": False, "tg_global_io": False, "tg_srt": False,
            "tg_ken_burns": False, "watermark_opacity": 0.8,
            "sub_y_pos": "Bottom", "sub_font": "Arial"
        }
        
        loaded = default.copy()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded.update(json.load(f))
            except: pass
            
        return loaded

    def save_settings(self):
        self.settings.update({
            "api_keys": self.entry_pexels_api.get("1.0", END).strip(),
            "resolution": self.var_resolution.get(),
            "bg_volume": self.slider_vol.get(),
            "ai_provider": self.var_ai_provider.get(),
            "ai_api_key": self.entry_ai_key.get().strip(),
            "ai_model": self.var_ai_model.get(),
            "encoder": self.var_encoder.get(),
            
            "disclaimer_mode": self.var_disc_mode.get(),
            "tg_ai_trans": self.var_tg_ai_trans.get(),
            "tg_adv_sub": self.var_tg_adv_sub.get(),
            "tg_global_io": self.var_tg_global_io.get(),
            "tg_srt": self.var_tg_srt.get(),
            "tg_ken_burns": self.var_tg_ken_burns.get(),
            "tg_watermark_opacity": self.var_tg_watermark_opacity.get(),
            "watermark_opacity": self.slider_opacity.get(),
            "sub_y_pos": self.var_sub_y_pos.get(),
            "sub_font": self.var_sub_font.get()
        })
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.settings, f)

    def preload_assets(self):
        # Audio Input
        if os.path.exists(DIR_INPUT):
            for f in os.listdir(DIR_INPUT):
                if f.lower().endswith((".mp3", ".wav", ".m4a")):
                    p = os.path.join(DIR_INPUT, f)
                    self.audio_files.append(p)
                    self.list_audio.insert('end', f)
        
        # Background Music
        if os.path.exists(DIR_MUSIC):
            for f in os.listdir(DIR_MUSIC):
                if f.lower().endswith((".mp3", ".wav", ".m4a")):
                    p = os.path.join(DIR_MUSIC, f)
                    self.bg_music_files.append(p)
                    self.list_bg.insert('end', f)
                    
        # Logo
        if os.path.exists(DIR_LOGO):
            for f in os.listdir(DIR_LOGO):
                if f.lower().endswith((".png", ".jpg", ".jpeg")):
                    self.logo_path = os.path.join(DIR_LOGO, f)
                    if hasattr(self, 'lbl_logo'): self.lbl_logo.configure(text=f)
                    break
        
        # Disclaimer
        if os.path.exists(DIR_DISCLAIMER):
            for f in os.listdir(DIR_DISCLAIMER):
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".mp4")):
                    self.disclaimer_bg_path = os.path.join(DIR_DISCLAIMER, f)
                    if hasattr(self, 'lbl_disc'): self.lbl_disc.configure(text=f)
                    break
                    
        # Intro
        if os.path.exists(DIR_INTRO):
            for f in os.listdir(DIR_INTRO):
                if f.lower().endswith((".mp4", ".mov", ".mkv")):
                    self.intro_path = os.path.join(DIR_INTRO, f)
                    if hasattr(self, 'lbl_intro'): self.lbl_intro.configure(text=f)
                    break
                    
        # Outro
        if os.path.exists(DIR_OUTRO):
            for f in os.listdir(DIR_OUTRO):
                if f.lower().endswith((".mp4", ".mov", ".mkv")):
                    self.outro_path = os.path.join(DIR_OUTRO, f)
                    if hasattr(self, 'lbl_outro'): self.lbl_outro.configure(text=f)
                    break

    def create_gui(self):
        import tkinter as tk # For Listbox compatibility with styling
        
        self.tabview = ctk.CTkTabview(self, width=1350, height=850)
        self.tabview.pack(pady=10, padx=10, fill="both", expand=True)
        
        self.tab_inputs = self.tabview.add("1. Input Files")
        self.tab_settings = self.tabview.add("2. Providers & Settings")
        self.tab_fx = self.tabview.add("3. Video/Audio FX Toggles")
        self.tab_process = self.tabview.add("4. Render")

        # --- TAB 1: INPUTS ---
        col1 = ctk.CTkFrame(self.tab_inputs, fg_color="transparent")
        col1.pack(side="left", fill="both", expand=True, padx=10)
        ctk.CTkButton(col1, text="Import Voiceover", command=self.add_audio_files).pack(pady=5, anchor="w")
        self.list_audio = tk.Listbox(col1, height=7, bg="#1e1e1e", fg="white", selectbackground="#1f538d", highlightthickness=2, highlightcolor="#3b8ed0", highlightbackground="#3d3d3d", relief="flat", borderwidth=0, font=("Inter", 11))
        self.list_audio.pack(fill="x", pady=5)
        
        btn_f1 = ctk.CTkFrame(col1, fg_color="transparent")
        btn_f1.pack(fill="x")
        ctk.CTkButton(btn_f1, text="Remove Selected", command=lambda: self.remove_selected(self.list_audio, self.audio_files)).pack(side="left", padx=5)
        ctk.CTkButton(btn_f1, text="Clear All", command=lambda: self.clear_all(self.list_audio, self.audio_files)).pack(side="left", padx=5)

        ctk.CTkButton(col1, text="Import BG Music", command=self.add_bg_files).pack(pady=15, anchor="w")
        self.list_bg = tk.Listbox(col1, height=6, bg="#1e1e1e", fg="white", selectbackground="#1f538d", highlightthickness=2, highlightcolor="#3b8ed0", highlightbackground="#3d3d3d", relief="flat", borderwidth=0, font=("Inter", 11))
        self.list_bg.pack(fill="x", pady=5)
        
        btn_f2 = ctk.CTkFrame(col1, fg_color="transparent")
        btn_f2.pack(fill="x")
        ctk.CTkButton(btn_f2, text="Remove Selected", command=lambda: self.remove_selected(self.list_bg, self.bg_music_files)).pack(side="left", padx=5)
        ctk.CTkButton(btn_f2, text="Clear All", command=lambda: self.clear_all(self.list_bg, self.bg_music_files)).pack(side="left", padx=5)

        col2 = ctk.CTkFrame(self.tab_inputs, fg_color="transparent")
        col2.pack(side="right", fill="both", expand=True, padx=10)
        
        ctk.CTkButton(col2, text="Select Logo", command=self.select_logo).pack(pady=5)
        self.lbl_logo = ctk.CTkLabel(col2, text="None")
        self.lbl_logo.pack()

        ctk.CTkButton(col2, text="Disclaimer BG", command=self.select_disclaimer_bg).pack(pady=5)
        self.lbl_disc = ctk.CTkLabel(col2, text="None")
        self.lbl_disc.pack()

        ctk.CTkButton(self.tab_inputs, text="Next ->", command=lambda: self.tabview.set("2. Providers & Settings")).pack(side="bottom", pady=10)

        # --- TAB 2: PROVDERS & SETTINGS ---
        saved_mode = self.settings.get("disclaimer_mode", "Online (AI)")
        if saved_mode.lower() == "online": saved_mode = "Online (AI)"
        elif saved_mode.lower() == "offline": saved_mode = "Offline (Keyword)"
        self.var_disc_mode = ctk.StringVar(value=saved_mode)
        
        self.f_disc = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        self.f_disc.pack(fill="x", padx=10, pady=5, anchor="w")
        ctk.CTkLabel(self.f_disc, text="Disclaimer Detection Mode:").pack(side="left")
        ctk.CTkOptionMenu(self.f_disc, variable=self.var_disc_mode, values=["Offline (Keyword)", "Online (AI)", "Off"], command=self.toggle_ai_visibility).pack(side="left", padx=10)

        self.f_ai = ctk.CTkFrame(self.tab_settings)
        
        self.var_ai_provider = ctk.StringVar(value=self.settings.get("ai_provider"))
        self.var_ai_model = ctk.StringVar(value=self.settings.get("ai_model"))
        self.var_encoder = ctk.StringVar(value=self.settings.get("encoder", "libx264 (CPU)"))
        
        ctk.CTkLabel(self.f_ai, text="AI Provider:", width=100).grid(row=0, column=0, padx=5, pady=5)
        self.opt_prov = ctk.CTkOptionMenu(self.f_ai, variable=self.var_ai_provider, values=list(MODELS.keys()), command=self.update_models)
        self.opt_prov.grid(row=0, column=1, padx=5, pady=5)

        self.btn_vertex = ctk.CTkButton(self.f_ai, text="Load Vertex JSON", command=self.load_vertex_json)
        self.btn_vertex.grid(row=0, column=2, padx=5, pady=5)
        
        self.lbl_vertex_name = ctk.CTkLabel(self.f_ai, text="None", width=120)
        self.lbl_vertex_name.grid(row=0, column=3, padx=5, pady=5)
        
        self.lbl_key = ctk.CTkLabel(self.f_ai, text="API Key / URL:", width=100)
        self.lbl_key.grid(row=1, column=0, padx=5, pady=5)
        self.entry_ai_key = ctk.CTkEntry(self.f_ai, width=300)
        self.entry_ai_key.insert(0, self.settings.get("ai_api_key"))
        self.entry_ai_key.grid(row=1, column=1, columnspan=2, padx=5, pady=5)
        
        self.btn_test = ctk.CTkButton(self.f_ai, text="Test Connection", command=self.test_api)
        self.btn_test.grid(row=1, column=3, padx=5, pady=5)

        ctk.CTkLabel(self.f_ai, text="Model:", width=100).grid(row=2, column=0, padx=5, pady=5)
        self.opt_mod = ctk.CTkComboBox(self.f_ai, variable=self.var_ai_model, values=MODELS["Local AI (Ollama)"], width=250)
        self.opt_mod.grid(row=2, column=1, padx=5, pady=5)

        ctk.CTkLabel(self.tab_settings, text="Pexels API Keys (Comma sep):").pack(anchor="w", padx=10)
        self.entry_pexels_api = ctk.CTkTextbox(self.tab_settings, height=60)
        self.entry_pexels_api.insert("1.0", self.settings.get("api_keys"))
        self.entry_pexels_api.pack(fill="x", padx=10, pady=5)

        self.var_resolution = ctk.StringVar(value=self.settings.get("resolution"))
        ctk.CTkLabel(self.tab_settings, text="Resolution:").pack(anchor="w", padx=10)
        ctk.CTkOptionMenu(self.tab_settings, variable=self.var_resolution, values=list(RESOLUTIONS.keys())).pack(anchor="w", padx=10, pady=5)
        
        ctk.CTkLabel(self.tab_settings, text="Encoder Hardware:").pack(anchor="w", padx=10)
        ctk.CTkOptionMenu(self.tab_settings, variable=self.var_encoder, values=list(ENCODERS.keys())).pack(anchor="w", padx=10, pady=5)

        nav_f2 = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        nav_f2.pack(side="bottom", fill="x", pady=10)
        ctk.CTkButton(nav_f2, text="<- Back", command=lambda: self.tabview.set("1. Input Files")).pack(side="left", padx=20)
        ctk.CTkButton(nav_f2, text="Next ->", command=lambda: self.tabview.set("3. Video/Audio FX Toggles")).pack(side="right", padx=20)

        # --- TAB 3: FX & TOGGLES ---
        scroll_fx = ctk.CTkFrame(self.tab_fx, fg_color="transparent")
        scroll_fx.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.var_tg_ai_trans = ctk.BooleanVar(value=self.settings.get("tg_ai_trans"))
        self.var_tg_adv_sub = ctk.BooleanVar(value=self.settings.get("tg_adv_sub"))
        self.var_tg_global_io = ctk.BooleanVar(value=self.settings.get("tg_global_io"))
        self.var_tg_srt = ctk.BooleanVar(value=self.settings.get("tg_srt"))
        self.var_tg_ken_burns = ctk.BooleanVar(value=self.settings.get("tg_ken_burns"))
        
        f_vol = ctk.CTkFrame(scroll_fx, fg_color="transparent")
        f_vol.pack(fill="x", pady=5)
        ctk.CTkLabel(f_vol, text="Background Music Vol:").pack(side="left")
        bg_vol = self.settings.get("bg_volume")
        if bg_vol is None: bg_vol = 0.1
        self.lbl_vol = ctk.CTkLabel(f_vol, text=f"{int(bg_vol*100)}%")
        self.lbl_vol.pack(side="left", padx=10)
        self.slider_vol = ctk.CTkSlider(scroll_fx, from_=0, to=1, command=lambda v: self.lbl_vol.configure(text=f"{int(v*100)}%"))
        self.slider_vol.set(bg_vol)
        self.slider_vol.pack(fill="x", pady=5)
        
        ctk.CTkSwitch(scroll_fx, text="Keyword Translation (Non-En voice -> En search)", variable=self.var_tg_ai_trans).pack(anchor="w", pady=5)
        ctk.CTkSwitch(scroll_fx, text="Ken Burns FX (Dynamic Zoom on Stock)", variable=self.var_tg_ken_burns).pack(anchor="w", pady=5)
        
        self.var_srt_lang = ctk.StringVar(value=self.settings.get("srt_lang", "English"))
        f_srt = ctk.CTkFrame(scroll_fx, fg_color="transparent")
        f_srt.pack(fill="x", pady=5)
        ctk.CTkSwitch(f_srt, text="Export Translated SRT File", variable=self.var_tg_srt).pack(side="left", padx=5)
        ctk.CTkLabel(f_srt, text="Target Language:").pack(side="left", padx=10)
        ctk.CTkEntry(f_srt, textvariable=self.var_srt_lang, width=100).pack(side="left")

        self.f_io_toggle = ctk.CTkFrame(scroll_fx, fg_color="transparent")
        self.f_io_toggle.pack(fill="x", pady=5)
        ctk.CTkSwitch(self.f_io_toggle, text="Concat Global Intro/Outro", variable=self.var_tg_global_io, command=self.toggle_io_visibility).pack(side="left", padx=5)

        self.f_io = ctk.CTkFrame(scroll_fx, fg_color="transparent")
        ctk.CTkButton(self.f_io, text="Select Intro MP4", command=self.select_intro).pack(side="left", padx=5)
        self.lbl_intro = ctk.CTkLabel(self.f_io, text="None")
        self.lbl_intro.pack(side="left", padx=5)
        ctk.CTkButton(self.f_io, text="Select Outro MP4", command=self.select_outro).pack(side="left", padx=5)
        self.lbl_outro = ctk.CTkLabel(self.f_io, text="None")
        self.lbl_outro.pack(side="left", padx=5)

        self.var_tg_watermark_opacity = ctk.BooleanVar(value=self.settings.get("tg_watermark_opacity", False))
        self.f_watermark_toggle = ctk.CTkFrame(scroll_fx, fg_color="transparent")
        self.f_watermark_toggle.pack(fill="x", pady=5)
        ctk.CTkSwitch(self.f_watermark_toggle, text="Enable Logo Opacity", variable=self.var_tg_watermark_opacity, command=self.toggle_watermark_visibility).pack(side="left", padx=5)

        self.f_op = ctk.CTkFrame(scroll_fx, fg_color="transparent")
        self.f_op.pack(fill="x", pady=5)
        ctk.CTkLabel(self.f_op, text="Logo Opacity:").pack(side="left")
        wm_op = self.settings.get("watermark_opacity")
        if wm_op is None: wm_op = 0.8
        self.lbl_op = ctk.CTkLabel(self.f_op, text=f"{int(wm_op*100)}%")
        self.lbl_op.pack(side="left", padx=10)
        self.slider_opacity = ctk.CTkSlider(self.f_op, from_=0, to=1, command=lambda v: self.lbl_op.configure(text=f"{int(v*100)}%"))
        self.slider_opacity.set(wm_op)
        self.slider_opacity.pack(fill="x", pady=5)

        self.f_subs_toggle = ctk.CTkFrame(scroll_fx)
        self.f_subs_toggle.pack(fill="x", pady=10)
        ctk.CTkSwitch(self.f_subs_toggle, text="Burn-in Advanced Subtitles", variable=self.var_tg_adv_sub, command=self.toggle_adv_sub_visibility).pack(anchor="w", padx=5, pady=5)
        
        self.var_sub_y_pos = ctk.StringVar(value=self.settings.get("sub_y_pos"))
        self.var_sub_font = ctk.StringVar(value=self.settings.get("sub_font"))
        
        self.f_subs_opt = ctk.CTkFrame(scroll_fx, fg_color="transparent")
        self.f_subs_opt.pack(fill="x", pady=5)
        ctk.CTkOptionMenu(self.f_subs_opt, variable=self.var_sub_y_pos, values=["Top", "Center", "Bottom"]).pack(side="left", padx=5, pady=5)
        fonts = ["ARIAL", "ARIALBD 1", "ARIALBD", "ARIALBI 1", "ARIALBI", "ARIALBLACKITALIC", "ArialCE", "arialceb", "ArialCEBoldItalic", "ArialCEItalic", "ArialCEMTBlack", "ARIALI 1", "ARIALI", "ARIALLGT", "ARIALLGTITL", "ArialMdm", "ArialMdmItl", "ARIALN", "ARIALNB", "ARIALNBI", "ARIALNI", "ARIBLK", "Nirmala"]
        ctk.CTkOptionMenu(self.f_subs_opt, variable=self.var_sub_font, values=fonts).pack(side="left", padx=5, pady=5)

        nav_f3 = ctk.CTkFrame(self.tab_fx, fg_color="transparent")
        nav_f3.pack(side="bottom", fill="x", pady=10)
        ctk.CTkButton(nav_f3, text="<- Back", command=lambda: self.tabview.set("2. Providers & Settings")).pack(side="left", padx=20)
        ctk.CTkButton(nav_f3, text="Next ->", command=self.nav_to_render).pack(side="right", padx=20)

        # --- TAB 4: RENDER ---
        self.btn_start = ctk.CTkButton(self.tab_process, text="START PRODUCTION", command=self.toggle_production, height=50, width=250, font=("Arial", 16, "bold"))
        self.btn_start.pack(pady=10)
        
        self.log_box = ctk.CTkTextbox(self.tab_process, width=1200, height=450, font=("Consolas", 12))
        self.log_box.pack(pady=10)
        
        self.progress_bar = ctk.CTkProgressBar(self.tab_process, width=800)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10)
        
        self.lbl_progress_text = ctk.CTkLabel(self.tab_process, text="0/0", font=("Consolas", 14))
        self.lbl_progress_text.pack(pady=5)

        nav_f4 = ctk.CTkFrame(self.tab_process, fg_color="transparent")
        nav_f4.pack(side="bottom", fill="x", pady=10)
        ctk.CTkButton(nav_f4, text="<- Back", command=lambda: self.tabview.set("3. Video/Audio FX Toggles")).pack(side="left", padx=20)

        # Developer Label
        self.lbl_branding = ctk.CTkLabel(nav_f4, text="Developer: Imon Mahmud | Phone: +8801739319407 | Version: 21.0 (Advanced)", font=("Arial", 11), text_color="gray")
        self.lbl_branding.pack(side="right", padx=20)

        self.update_models(self.var_ai_provider.get())
        self.toggle_ai_visibility()
        self.toggle_io_visibility()
        self.toggle_watermark_visibility()
        self.toggle_adv_sub_visibility()

    def nav_to_render(self):
        if self.var_tg_global_io.get() and not self.intro_path and not self.outro_path:
            messagebox.showwarning("Warning", "Intro/Outro feature is enabled but no video was selected. Auto-disabling feature.")
            self.var_tg_global_io.set(False)
            self.toggle_io_visibility()
        self.tabview.set("4. Render")

    def remove_selected(self, listbox, file_list):
        opts = listbox.curselection()
        if opts:
            for i in reversed(opts):
                file_path = file_list.pop(i)
                listbox.delete(i)
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    self.safe_log(f"Error removing file: {e}")

    def clear_all(self, listbox, file_list):
        for file_path in file_list:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                self.safe_log(f"Error removing file: {e}")
        file_list.clear()
        listbox.delete(0, 'end')

    def toggle_ai_visibility(self, *args):
        if self.var_disc_mode.get() == "Online (AI)":
            self.f_ai.pack(fill="x", padx=10, pady=5, after=self.f_disc)
        else:
            self.f_ai.pack_forget()

    def toggle_watermark_visibility(self):
        if hasattr(self, 'f_op'):
            if self.var_tg_watermark_opacity.get():
                self.f_op.pack(fill="x", pady=5, after=self.f_watermark_toggle)
            else:
                self.f_op.pack_forget()

    def toggle_adv_sub_visibility(self):
        if hasattr(self, 'f_subs_opt'):
            if self.var_tg_adv_sub.get():
                self.f_subs_opt.pack(fill="x", pady=5, after=self.f_subs_toggle)
            else:
                self.f_subs_opt.pack_forget()

    def toggle_io_visibility(self):
        if hasattr(self, 'f_io'):
            if self.var_tg_global_io.get():
                self.f_io.pack(fill="x", pady=5, after=self.f_io_toggle)
            else:
                self.f_io.pack_forget()

    def test_api(self):
        self.safe_log("Testing AI Connection...")
        try:
            res = self.call_ai("Hello. Answer with only the word 'OK'.")
            if res and "ok" in res.lower():
                messagebox.showinfo("Success", f"Connection Successful!\nProvider {self.var_ai_provider.get()} responded.")
                self.safe_log("AI Connection Successful.")
            else:
                messagebox.showerror("Failed", f"Connection Failed!\nPlease verify your Key, JSON, or Local URL.\nDetails: {res}")
                self.safe_log("AI Connection Failed.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect:\n{e}")
            self.safe_log(f"AI Connection Exception: {e}")

    def safe_log(self, msg, replace=False): self.after(0, lambda: self._log_internal(msg, replace))
    def _log_internal(self, msg, replace=False):
        at_bottom = self.log_box.yview()[1] >= 0.95
        if replace:
            try:
                # Delete the last inserted line
                self.log_box.delete("end-2l", "end-1c")
            except: pass
        else:
            self.log_box.insert('end', f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            if at_bottom:
                self.log_box.see('end')
            return
            
        self.log_box.insert('end', f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        if at_bottom:
            self.log_box.see('end')

    def update_models(self, provider):
        models_dict = MODELS.get(provider, {})
        if isinstance(models_dict, dict):
            values = list(models_dict.keys())
        else:
            values = models_dict
        self.opt_mod.configure(values=values)
        self.var_ai_model.set(DEFAULT_MODELS.get(provider, ""))
        
        if provider == "Vertex AI":
            self.btn_vertex.grid(row=0, column=2, padx=5, pady=5)
            self.lbl_key.grid_forget()
            self.entry_ai_key.grid_forget()
        elif provider == "Local AI (Ollama)":
            self.btn_vertex.grid_forget()
            self.lbl_key.grid_forget()
            self.entry_ai_key.grid_forget()
            self.entry_ai_key.delete(0, 'end')
            self.entry_ai_key.insert(0, "http://127.0.0.1:11434/api/chat")
        else:
            self.btn_vertex.grid_forget()
            self.lbl_key.grid(row=1, column=0, padx=5, pady=5)
            self.entry_ai_key.grid(row=1, column=1, columnspan=2, padx=5, pady=5)
            # Clear if previous was Ollama default
            if "http" in self.entry_ai_key.get():
                self.entry_ai_key.delete(0, 'end')

    def load_vertex_json(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if f:
            self.vertex_credits = f
            self.safe_log(f"Vertex Credentials Loaded: {f}")
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f
            if hasattr(self, 'lbl_vertex_name'):
                self.lbl_vertex_name.configure(text=os.path.basename(f))
            messagebox.showinfo("Success", f"Vertex credentials loaded successfully!\nFile: {os.path.basename(f)}")

    def add_audio_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Audio", "*.mp3 *.wav *.m4a")])
        for f in files:
            d = os.path.join(DIR_INPUT, os.path.basename(f))
            shutil.copy2(f, d)
            if d not in self.audio_files:
                self.audio_files.append(d)
                self.list_audio.insert('end', os.path.basename(d))

    def add_bg_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Audio", "*.mp3 *.wav *.m4a")])
        for f in files:
            d = os.path.join(DIR_MUSIC, os.path.basename(f))
            shutil.copy2(f, d)
            if d not in self.bg_music_files:
                self.bg_music_files.append(d)
                self.list_bg.insert('end', os.path.basename(d))
                
    def select_logo(self):
        f = filedialog.askopenfilename()
        if f:
            d = os.path.join(DIR_LOGO, os.path.basename(f))
            shutil.copy2(f, d)
            self.logo_path = d
            self.lbl_logo.configure(text=os.path.basename(f))
        
    def select_disclaimer_bg(self):
        f = filedialog.askopenfilename()
        if f:
            d = os.path.join(DIR_DISCLAIMER, os.path.basename(f))
            shutil.copy2(f, d)
            self.disclaimer_bg_path = d
            self.lbl_disc.configure(text=os.path.basename(f))
        
    def select_intro(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.mkv")])
        if f:
            d = os.path.join(DIR_INTRO, os.path.basename(f))
            shutil.copy2(f, d)
            self.intro_path = d
            self.lbl_intro.configure(text=os.path.basename(f))
        
    def select_outro(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.mkv")])
        if f:
            d = os.path.join(DIR_OUTRO, os.path.basename(f))
            shutil.copy2(f, d)
            self.outro_path = d
            self.lbl_outro.configure(text=os.path.basename(f))

    # --- INSTANT FORCE STOP ---
    def toggle_production(self):
        if not self.is_processing: self.start_processing()
        else: self.force_stop()

    def force_stop(self, silent=False):
        self.stop_event.set()
        self.is_processing = False
        if not silent:
            self.safe_log("FORCE STOP INITIATED. Killing all processes...")
        
        for p in active_processes:
            try:
                p.kill()
            except:
                pass
        active_processes.clear()
        
        global active_pool
        if active_pool:
            try:
                active_pool.shutdown(wait=False, cancel_futures=True)
            except:
                pass
                
        self.btn_start.configure(text="START PRODUCTION", fg_color="#1f6aa5")

    def translate_text(self, text, target_lang='en'):
        try:
            from deep_translator import GoogleTranslator
            return GoogleTranslator(source='auto', target=target_lang).translate(text)
        except Exception as e:
            try:
                # Fallback to Ollama
                prompt = f"Translate the following text to {target_lang}. Return ONLY the translated text without quotes:\n{text}"
                
                if self.var_ai_provider.get() == "Local AI (Ollama)":
                    res = self.call_ai(prompt)
                    if res: return res.strip()
                else:
                    key = "http://127.0.0.1:11434/api/chat"
                    if "11434" in self.entry_ai_key.get():
                        key = self.entry_ai_key.get().strip()
                    model = self.var_ai_model.get() or "llama3.2"
                    r = requests.post(key, json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "keep_alive": 0})
                    if r.status_code == 200:
                        return r.json()['message']['content'].strip()
                return text
            except Exception as e2:
                self.safe_log(f"Translation failed: {e2}")
                return text

    def call_ai(self, prompt):
        provider = self.var_ai_provider.get()
        model_raw = self.var_ai_model.get()
        
        # Get actual model id from dictionary
        model = model_raw
        if isinstance(MODELS.get(provider), dict):
            model = MODELS[provider].get(model_raw, model_raw)
        elif "(" in model_raw and ")" in model_raw:
            model = model_raw.split("(")[-1].split(")")[0].strip()
            
        key = self.entry_ai_key.get().strip()
        
        try:
            if provider == "Local AI (Ollama)":
                r = requests.post(key, json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "keep_alive": 0})
                r.raise_for_status()
                data = r.json()
                return data['message']['content']
                
            elif provider in ["Gemini", "Vertex AI"]:
                if not HAS_GENAI: 
                    raise RuntimeError("Google GenAI SDK is not installed.")
                if provider == "Vertex AI":
                    client = genai.Client(vertexai=True)
                else:
                    if not key: raise ValueError("API Key is required for Gemini.")
                    client = genai.Client(api_key=key)
                r = client.models.generate_content(model=model, contents=prompt)
                return r.text
                
            elif provider == "OpenAI":
                if not HAS_OPENAI: 
                    raise RuntimeError("OpenAI SDK is not installed.")
                if not key: raise ValueError("API Key is required for OpenAI.")
                client = OpenAI(api_key=key)
                r = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
                return r.choices[0].message.content
                
            elif provider == "OpenRouter":
                if not key: raise ValueError("API Key is required for OpenRouter.")
                r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://github.com/AI-Video-Studio", "X-Title": "AI Video Studio"}, json={"model": model, "messages": [{"role": "user", "content": prompt}]})
                if not r.ok:
                    try:
                        err_msg = r.json().get('error', {}).get('message', r.text)
                    except:
                        err_msg = r.text
                    raise RuntimeError(f"OpenRouter API Error: {err_msg}")
                data = r.json()
                return data['choices'][0]['message']['content']
        except Exception as e:
            if isinstance(e, (ValueError, RuntimeError)):
                self.safe_log(f"CRITICAL: {e}")
                raise e
            self.safe_log(f"AI Call failed for provider '{provider}'. Error: {e}")
            raise e

    def start_processing(self):
        self.save_settings()
        self.pexels_api_keys = [k.strip() for k in self.entry_pexels_api.get("1.0", END).split(',') if k.strip()]
        
        if not self.audio_files:
            messagebox.showerror("Error", "No Input Voiceovers.")
            return

        self.is_processing = True
        self.stop_event.clear()
        
        self.btn_start.configure(text="STOP PRODUCTION", fg_color="red")
        threading.Thread(target=self.batch_runner, daemon=True).start()

    def detect_disclaimer_offline(self, segments):
        indices = []
        lock = 0
        for i, s in enumerate(segments):
            if s['start'] < lock:
                indices.append(i)
                continue
            txt = s['text'].lower()
            if "disclaimer" in txt or "warning" in txt or "attention" in txt:
                indices.append(i)
                lock = s['end'] + 15.0
        return indices

    def extract_keywords(self, text):
        import string
        stopwords = {"this", "is", "about", "potential", "outcomes", "where", "you", "are", "in", "total", "control", "of", "the", "a", "an", "and", "or", "to", "for", "with", "on", "it", "that", "they", "we", "have", "been", "was", "how", "what", "when", "why", "who", "will", "going", "your", "out", "did", "not", "even", "know", "needed", "then", "there", "has", "can", "could", "would", "should"}
        # Remove punctuation
        text = text.translate(str.maketrans('', '', string.punctuation))
        words = text.split()
        keywords = [w for w in words if w.lower() not in stopwords and len(w) > 3]
        if not keywords:
            # Fallback to just the first long-ish word or the text itself
            candidates = [w for w in words if len(w) > 2]
            if candidates: return candidates[0]
            return text.strip()[:10]
        # Return first 2 keywords max for broader search
        return " ".join(keywords[:2])

    def detect_disclaimer_online(self, segments):
        lines = []
        for i, seg in enumerate(segments):
            if seg['start'] > 120: break  # Only check the first 2 minutes
            lines.append(f"ID:{i} Text:{seg['text']}")
        full_text = "\n".join(lines)
        
        prompt = f"Analyze transcripts. Return ONLY a raw JSON list of IDs for disclaimer/warning/legal content. No code blocks, no explanations. Ex: [0, 1]. If none, return [].\n\n{full_text}"
        
        try:
            res = self.call_ai(prompt)
            import json
            import re
            if not res:
                raise ValueError("AI returned empty response for disclaimer detection.")
                
            m = re.search(r"\[.*?\]", res, re.DOTALL)
            if not m:
                raise ValueError(f"Could not find JSON array in AI response: {res}")
                
            ids = json.loads(m.group(0))
            return [int(x) for x in ids]
        except Exception as e:
            self.safe_log(f"Online disclaimer detection failed: {e}. Falling back to offline mode.")
            return self.detect_disclaimer_offline(segments)

    def batch_runner(self):
        try:
            self._batch_runner_internal()
        except Exception as e:
            self.safe_log(f"CRITICAL THREAD ERROR: {e}")
            import traceback
            self.safe_log(traceback.format_exc())
            self.force_stop()

    def _batch_runner_internal(self):
        global active_pool
        global HAS_WHISPER
        if not HAS_WHISPER:
            self.safe_log("openai-whisper package is not installed. Installing it automatically...")
            try:
                import subprocess
                subprocess.check_call([sys.executable, "-m", "pip", "install", "openai-whisper"])
                global whisper, get_writer
                import whisper
                from whisper.utils import get_writer
                HAS_WHISPER = True
                self.safe_log("openai-whisper installed successfully.")
            except Exception as e:
                self.safe_log(f"Auto-install failed: {e}")
                self.safe_log("ERROR: openai-whisper package is not installed. Please install it manually.")
                self.force_stop()
                return

        if self.loaded_whisper_model is None:
            self.safe_log("Loading Whisper...")
            try:
                self.loaded_whisper_model = whisper.load_model("base")
            except:
                self.safe_log("Whisper Load Failed.")
                self.force_stop()
                return

        for idx, aud in enumerate(self.audio_files):
            if self.stop_event.is_set(): break
            name = os.path.splitext(os.path.basename(aud))[0]
            
            temp_dir = os.path.join(DIR_TEMP, name)
            out_dir = os.path.join(DIR_OUTPUT, name)
            os.makedirs(temp_dir, exist_ok=True)
            os.makedirs(out_dir, exist_ok=True)
            
            self.safe_log(f"--- Processing {idx+1}/{len(self.audio_files)}: {name} ---")
            if hasattr(self, 'progress_bar'):
                self.progress_bar.set(idx / max(1, len(self.audio_files)))
            if hasattr(self, 'lbl_progress_text'):
                self.after(0, lambda text=f"{idx}/{len(self.audio_files)} Completed": self.lbl_progress_text.configure(text=text))
            
            self.safe_log(f"Transcribing {name}...")
            res = self.loaded_whisper_model.transcribe(aud, verbose=False, fp16=False)
            segments = res['segments']
            
            if self.var_tg_srt.get():
                target_lang = getattr(self, 'var_srt_lang', ctk.StringVar(value="English")).get().strip().lower()
                if target_lang and target_lang != "english":
                    for s in res['segments']:
                        s['text'] = self.translate_text(s['text'], target_lang)
                writer = get_writer("srt", out_dir)
                writer(res, aud, {"max_line_width": 47, "max_line_count": 2, "highlight_words": False})
                self.safe_log(f"SRT saved.")

            # Clip logic
            disc_indices = []
            mode = self.var_disc_mode.get()
            self.safe_log(f"Detecting Disclaimers using {mode}...")
            if mode == "Offline (Keyword)":
                disc_indices = self.detect_disclaimer_offline(segments)
            elif mode == "Online (AI)":
                disc_indices = self.detect_disclaimer_online(segments)
            
            self.safe_log(f"Detected {len(disc_indices)} Disclaimer segments.")

            if self.var_tg_adv_sub.get():
                import copy
                burnin_res = copy.deepcopy(res)
                # clear text for disclaimer segments
                for i in disc_indices:
                    if i < len(burnin_res['segments']):
                        # We use a space string so the SRT entry exists but shows nothing
                        burnin_res['segments'][i]['text'] = " "
                
                writer = get_writer("srt", temp_dir)
                try:
                    writer(burnin_res, "burnin_subs.mp3", {"max_line_width": 47, "max_line_count": 2, "highlight_words": False})
                except Exception as e:
                    self.safe_log(f"Burn-in SRT Error: {e}")

            download_q = []
            for i, s in enumerate(segments):
                if i in disc_indices and self.disclaimer_bg_path and os.path.exists(self.disclaimer_bg_path):
                    download_q.append("DISCLAIMER_TAG")
                    continue

                text = s['text'].strip()
                if self.var_tg_ai_trans.get():
                    text = self.translate_text(text, "en")
                
                download_q.append(text)
                
            self.safe_log("Fetching Assets...")
            vmap = self.download_stock([q for q in download_q if q != "DISCLAIMER_TAG"], temp_dir)
            if self.disclaimer_bg_path and os.path.exists(self.disclaimer_bg_path):
                vmap["DISCLAIMER_TAG"] = self.disclaimer_bg_path
            
            audio_dur = self.get_media_duration(aud)
            if not audio_dur:
                audio_dur = segments[-1]['end'] if segments else 60

            self.safe_log("Rendering Base Video...")
            merged = self.render_base_ff(segments, download_q, vmap, temp_dir, audio_dur)
            if not merged: continue
            
            self.safe_log("Applying Final FX & Concat...")
            
            final_file = os.path.join(out_dir, f"Final_{name}.mp4")
            self.apply_final_fx(merged, aud, final_file, temp_dir, out_dir, audio_dur)
            
            if self.var_tg_global_io.get() and (self.intro_path or self.outro_path):
                concat_list_path = os.path.join(temp_dir, "io_clips.txt")
                
                hw_enc, hw_params = ENCODERS[self.var_encoder.get()]
                res_x, res_y = RESOLUTIONS[self.var_resolution.get()]
                
                def conform_io(io_path, prefix):
                    conformed = os.path.join(temp_dir, f"{prefix}_conformed.mp4")
                    vf = f"scale={res_x}:{res_y}:force_original_aspect_ratio=decrease,pad={res_x}:{res_y}:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1"
                    
                    has_aud = self.has_audio_stream(io_path)
                    if has_aud:
                        cmd = [ffmpeg_path, "-y", "-i", io_path, "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", 
                               "-filter_complex", f"[0:v]{vf}[vout];[1:a][0:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]",
                               "-map", "[vout]", "-map", "[aout]", "-shortest", "-c:v", hw_enc] + hw_params + ["-c:a", "aac", "-ar", "44100", "-ac", "2", "-video_track_timescale", "30000", conformed]
                    else:
                        cmd = [ffmpeg_path, "-y", "-i", io_path, "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", 
                               "-filter_complex", f"[0:v]{vf}[vout]",
                               "-map", "[vout]", "-map", "1:a", "-shortest", "-c:v", hw_enc] + hw_params + ["-c:a", "aac", "-ar", "44100", "-ac", "2", "-video_track_timescale", "30000", conformed]
                    self.exec_ffmpeg(cmd, cwd=temp_dir)
                    return conformed if os.path.exists(conformed) else io_path
                
                io_inputs = []
                if self.intro_path and os.path.exists(self.intro_path):
                    io_inputs.append(conform_io(self.intro_path, "intro"))
                io_inputs.append(final_file)
                if self.outro_path and os.path.exists(self.outro_path):
                    io_inputs.append(conform_io(self.outro_path, "outro"))
                
                final_io_file = os.path.join(out_dir, f"Final_IO_{name}.mp4")
                
                with open(concat_list_path, 'w') as f:
                    for inp in io_inputs:
                        if os.path.exists(inp):
                            f.write(f"file '{inp}'\n")
                            
                cmd = [ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", final_io_file]
                self.exec_ffmpeg(cmd, cwd=temp_dir)
                
                if os.path.exists(final_io_file):
                    try:
                        os.replace(final_io_file, final_file)
                    except:
                        pass
                        
            # Clean up temporary directory after successful processing
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                self.safe_log(f"Temp cleanup warning: {e}")

        self.force_stop(silent=True)
        if hasattr(self, 'progress_bar') and self.audio_files:
            self.progress_bar.set(1.0)
        if hasattr(self, 'lbl_progress_text') and self.audio_files:
            self.after(0, lambda text=f"{len(self.audio_files)}/{len(self.audio_files)} Completed": self.lbl_progress_text.configure(text=text))
        self.safe_log("BATCH COMPLETE.")

    def download_stock(self, keywords, save_dir):
        global active_pool
        vmap = {}
        active_keys = self.pexels_api_keys.copy()
        uniq = list(set(keywords))

        # ১. Stats Tracking Dictionary
        stats = {"success": 0, "cached": 0, "failed": 0, "retries": 0}

        def task(q):
            if self.stop_event.is_set() or not active_keys: 
                return {"status": "failed", "q": q, "file": None, "retries": 0}
            
            h = hashlib.md5(q.encode()).hexdigest()
            final_fname = os.path.join(save_dir, f"{h}.mp4")
            temp_fname = final_fname + ".part"

            # ১. Skip Logic: সম্পূর্ণ ভিডিও থাকলে স্কিপ করবে (৩০০ KB সাইজ ভ্যালিডেশন)
            if os.path.exists(final_fname) and os.path.getsize(final_fname) > 300000:
                # ২. Return Dictionary (Cached)
                return {"status": "cached", "q": q, "file": final_fname, "retries": 0}

            def get_video_url(search_q):
                attempts = 0
                while attempts < 8 and active_keys:
                    if self.stop_event.is_set(): return None
                    current_key = random.choice(active_keys)
                    try:
                        url = f"https://api.pexels.com/videos/search?query={quote(search_q)}&per_page=5&orientation=landscape"
                        r = self.session.get(url, headers={"Authorization": current_key}, timeout=30)

                        # Error Handling: 401/429 Quota Exceeded/Invalid Key -> Thread-safe Remove Key (No Sleep)
                        if r.status_code in [401, 429]:
                            try:
                                active_keys.remove(current_key)
                            except ValueError:
                                pass
                            continue

                        # Error Handling: 403 WAF Block -> Exponential Backoff (Do Not Remove Key)
                        if r.status_code == 403:
                            time.sleep(2 ** (attempts + 1))
                            attempts += 1
                            continue
                            
                        if r.status_code == 200:
                            vids = r.json().get('videos', [])
                            if vids:
                                v_files = vids[0].get('video_files', [])
                                if v_files:
                                    v_files.sort(key=lambda x: x.get('width', 0), reverse=True)
                                    return v_files[0].get('link')
                            break 
                        
                        attempts += 1
                    except Exception:
                        attempts += 1
                return None

            video_url = get_video_url(q)
            
            # ফলব্যাক কিওয়ার্ড সার্চ
            if not video_url:
                kw = self.extract_keywords(q)
                if kw != q:
                    video_url = get_video_url(kw)

            download_attempts = 0

            # ২. Temp File Download with Retry Mechanism (Maximum 8 Retries)
            if video_url:
                while download_attempts < 8:
                    if self.stop_event.is_set(): 
                        return {"status": "failed", "q": q, "file": None, "retries": download_attempts}
                    
                    try:
                        # যদি আগের ফেইল্ড ডাউনলোড থেকে যায়, তাহলে ডিলিট করে নতুন শুরু করবে
                        if os.path.exists(temp_fname):
                            try:
                                os.remove(temp_fname)
                            except:
                                pass

                        with self.session.get(video_url, stream=True, timeout=60) as vr:
                            vr.raise_for_status()
                            with open(temp_fname, 'wb') as f:
                                for ch in vr.iter_content(8192): 
                                    if self.stop_event.is_set(): break
                                    f.write(ch)
                                    
                        # ৫. Success Rename: ডাউনলোড ১০০% সম্পূর্ণ হলে এবং ৩০০ KB পার হলে রিনেম
                        if os.path.exists(temp_fname) and os.path.getsize(temp_fname) > 300000:
                            os.replace(temp_fname, final_fname)
                            # ২. Return Dictionary (Success)
                            return {"status": "success", "q": q, "file": final_fname, "retries": download_attempts}
                    except Exception:
                        pass # Network connection drop বা অন্য error-এর ক্ষেত্রে পাস করে রি-ট্রাই করবে
                    
                    download_attempts += 1
                    if download_attempts < 8:
                        time.sleep(2)

            # ৩ ও ৪. Zero Corruption & Fresh Start: ৮ বার ফেইল করার পরও যদি টেম্প ফাইল থাকে, মুছে ফেলবে
            if os.path.exists(temp_fname):
                try:
                    os.remove(temp_fname)
                except:
                    pass

            # ২. Return Dictionary (Failed)
            return {"status": "failed", "q": q, "file": None, "retries": download_attempts}

        total_vids = len(uniq)
        completed_vids = 0
        if total_vids > 0:
            self.safe_log(f"Downloading Pexels Assets: 0/{total_vids}")

        # ThreadPoolExecutor Context Manager ব্যবহার করা হয়েছে (Memory Leak প্রতিরোধে)
        with ThreadPoolExecutor(max_workers=3) as executor:
            active_pool = executor # Assigned globally so force_stop can access it if needed
            futures = [executor.submit(task, q) for q in uniq]
            for f in as_completed(futures):
                res = f.result()
                
                # Update Stats
                if res:
                    status = res.get("status")
                    if status == "success":
                        stats["success"] += 1
                        vmap[res["q"]] = res["file"]
                    elif status == "cached":
                        stats["cached"] += 1
                        vmap[res["q"]] = res["file"]
                    elif status == "failed":
                        stats["failed"] += 1
                    
                    stats["retries"] += res.get("retries", 0)

                completed_vids += 1
                
                # ৩. Live Console Update
                msg = f"Downloading Assets: {completed_vids}/{total_vids} (New: {stats['success']} | Cached: {stats['cached']} | Retries: {stats['retries']} | Failed: {stats['failed']})"
                self.safe_log(msg, replace=True)
                
        active_pool = None
        
        # ৪. Final Summary
        summary_msg = f"Download Summary => Total Unique: {total_vids} | New DLs: {stats['success']} | Cached: {stats['cached']} | Retries Triggered: {stats['retries']} | Failed: {stats['failed']}"
        self.safe_log(summary_msg)
        
        return vmap

    def exec_ffmpeg(self, cmd, cwd=None):
        if self.stop_event.is_set(): return False
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = 0x08000000
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, **kwargs)
            active_processes.append(p)
            stdout, stderr = p.communicate()
            if p in active_processes:
                active_processes.remove(p)
            if p.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='ignore').strip() if isinstance(stderr, bytes) else str(stderr).strip()
                self.safe_log(f"FFmpeg Error:\n{err_msg}")
                return False
            return True
        except Exception as e:
            self.safe_log(f"FFmpeg Execution Error: {e}")
            return False

    def get_media_duration(self, file_path):
        cmd = [ffmpeg_path, "-hide_banner", "-i", file_path]
        try:
            # Note: ffmpeg -i outputs to stderr
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = 0x08000000
            p = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
            import re
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr)
            if m:
                return float(m.group(1)) * 3600 + float(m.group(2)) * 60 + float(m.group(3))
        except:
            pass
        return None

    def has_audio_stream(self, file_path):
        cmd = [ffmpeg_path, "-hide_banner", "-i", file_path]
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = 0x08000000
            p = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
            return "Audio:" in p.stderr
        except:
            return False

    def render_base_ff(self, segs, download_q, vmap, temp_dir, audio_dur):
        global active_pool
        res_x, res_y = RESOLUTIONS[self.var_resolution.get()]
        hw_enc, hw_params = ENCODERS[self.var_encoder.get()]
        
        clip_list = os.path.join(temp_dir, "clips.txt")
        tasks = []
        fps = 30.0
        for i, s in enumerate(segs):
            start_t = s['start'] if i > 0 else 0.0
            end_t = segs[i+1]['start'] if i < len(segs) - 1 else audio_dur
            if end_t <= start_t and i == len(segs) - 1:
                end_t = start_t + max(0.1, s['end'] - s['start'])
            
            start_f = int(round(start_t * fps))
            end_f = int(round(end_t * fps))
            dur = (end_f - start_f) / fps
            if dur <= 0: dur = 0.1
                
            out = os.path.join(temp_dir, f"r_{i}.mp4")
            query_txt = download_q[i]
            tasks.append((out, query_txt, dur, s['text']))

        def create_disclaimer_image(bg_path, text, out_path, w, h):
            try:
                if bg_path and os.path.exists(bg_path):
                    if bg_path.lower().endswith('.mp4'):
                        pass
                    else:
                        img = PIL.Image.open(bg_path).convert("RGBA")
                        img = img.resize((w, h))
                        draw = PIL.ImageDraw.Draw(img)
                        try:
                            if os.name == 'nt':
                                font = PIL.ImageFont.truetype("arial.ttf", int(h*0.06))
                            else:
                                try:
                                    font = PIL.ImageFont.truetype("DejaVuSans.ttf", int(h*0.06))
                                except:
                                    font = PIL.ImageFont.load_default()
                        except:
                            font = PIL.ImageFont.load_default()
                            
                        words = text.split()
                        lines = []
                        line = ""
                        for word in words:
                            test_line = line + " " + word if line else word
                            bbox = draw.textbbox((0,0), test_line, font=font)
                            if bbox[2] - bbox[0] <= w * 0.8:
                                line = test_line
                            else:
                                lines.append(line)
                                line = word
                        if line: lines.append(line)
                        
                        y_text = h * 0.5 - (len(lines) * int(h*0.07)) / 2
                        for line in lines:
                            bbox = draw.textbbox((0,0), line, font=font)
                            line_w = bbox[2] - bbox[0]
                            draw.text(((w - line_w) / 2, y_text), line, font=font, fill=(255,255,255), stroke_width=2, stroke_fill=(0,0,0))
                            y_text += int(h*0.07)
                        
                        img.convert("RGB").save(out_path)
                        return out_path
            except Exception as e:
                self.safe_log(f"Error creating disclaimer PIL image: {e}")
            return bg_path

        def render_clip(t):
            out, query_txt, dur, text = t
            vid = vmap.get(query_txt)
            
            if not vid: 
                vid = random.choice(list(vmap.values())) if vmap else None
            
            if query_txt == "DISCLAIMER_TAG" and vid:
                disc_img = os.path.join(temp_dir, f"disc_bg_{os.path.basename(out)}.jpg")
                vid = create_disclaimer_image(vid, text, disc_img, res_x, res_y)
            
            cmd = [ffmpeg_path, "-y"]
            if vid:
                if vid.lower().endswith(('.jpg', '.jpeg', '.png')):
                    cmd.extend(["-loop", "1"])
                else:
                    cmd.extend(["-stream_loop", "-1"])
                cmd.extend(["-i", vid])
            else: 
                cmd.extend(["-f", "lavfi", "-i", f"color=black:s={res_x}x{res_y}"])
            
            is_disclaimer = (query_txt == "DISCLAIMER_TAG")
            is_image = vid and vid.lower().endswith(('.jpg', '.jpeg', '.png'))
            
            if is_disclaimer:
                v_filter = f"scale={res_x}:{res_y}:force_original_aspect_ratio=decrease,pad={res_x}:{res_y}:(ow-iw)/2:(oh-ih)/2,setsar=1"
            else:
                v_filter = f"scale={res_x}:{res_y}:force_original_aspect_ratio=increase,crop={res_x}:{res_y},setsar=1"
                if self.var_tg_ken_burns.get():
                    if is_image:
                        frames = int(dur * 30) + 30
                        v_filter += f",zoompan=z='min(zoom+0.0015,1.5)':d={frames}:x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':s={res_x}x{res_y}:fps=30,setsar=1"
            
            v_filter += ",fps=30,format=yuv420p"
            # Explicitly select only the video stream to avoid loop issues
            cmd.extend(["-map", "0:v:0"])
            cmd.extend(["-vf", v_filter, "-t", str(dur), "-c:v", hw_enc] + hw_params + ["-video_track_timescale", "30000", "-an", out])
            self.exec_ffmpeg(cmd)
            return out

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FFMPEG) as pool:
            active_pool = pool
            results = list(pool.map(render_clip, tasks))
        
        valids = [c for c in results if os.path.exists(c)]
        if not valids: return None
        
        with open(clip_list, 'w') as f:
            for v in valids: f.write(f"file '{os.path.basename(v)}'\n")
            
        merged = os.path.join(temp_dir, "merged.mp4")
        success = self.exec_ffmpeg([ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", clip_list, "-c", "copy", merged], cwd=temp_dir)
        return merged if success else None

    def apply_final_fx(self, v_in, a_in, f_out, temp_dir, out_dir, audio_dur=60):
        hw_enc, hw_params = ENCODERS[self.var_encoder.get()]
        res_x, res_y = RESOLUTIONS[self.var_resolution.get()]
        
        cmd = [ffmpeg_path, "-y", "-i", v_in, "-i", a_in]
        filters = []
        next_i = 2
        
        a_map = "1:a"
        v_map = "0:v"
        
        # Audio
        if self.bg_music_files:
            bg = random.choice(self.bg_music_files)
            cmd.extend(["-stream_loop", "-1", "-i", bg])
            bg_i = next_i
            next_i += 1
            
            vol = self.slider_vol.get()
            
            filters.append(f"[{bg_i}:a]volume={vol}[bgv];[1:a][bgv]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a_mix]")
                
            a_map = "[a_mix]"
            
        # Video
        if self.logo_path and os.path.exists(self.logo_path):
            cmd.extend(["-loop", "1", "-i", self.logo_path])
            logo_i = next_i
            next_i += 1
            logo_w = int(res_x * 0.06)
            logo_pad = int(res_x * 0.015)
            if self.var_tg_watermark_opacity.get():
                op = self.slider_opacity.get()
                filters.append(f"[{logo_i}:v]format=rgba,colorchannelmixer=aa={op},scale={logo_w}:-1[logo]")
            else:
                filters.append(f"[{logo_i}:v]format=rgba,scale={logo_w}:-1[logo]")
            v_in_pad = f"[{v_map}]" if not v_map.startswith('[') else v_map
            filters.append(f"{v_in_pad}[logo]overlay=main_w-overlay_w-{logo_pad}:{logo_pad}:shortest=1[v1]")
            v_map = "[v1]"
            
        if self.var_tg_adv_sub.get():
            safe_srt_path = os.path.join(temp_dir, "burnin_subs.srt")
            if os.path.exists(safe_srt_path):
                safe_srt = "burnin_subs.srt"
                
                y_pos = self.var_sub_y_pos.get()
                align = 2
                margin = 15
                if y_pos == "Top":
                    align = 8
                    margin = 20
                elif y_pos == "Center":
                    align = 5
                    margin = 0
                font_size = 20
                fnt = getattr(self, 'var_sub_font', ctk.StringVar(value="Arial")).get()
                # Subtitles filter
                v_in_pad = f"[{v_map}]" if not v_map.startswith('[') else v_map
                filters.append(f"{v_in_pad}subtitles=filename='{safe_srt}':force_style='Fontname={fnt},FontSize={font_size},Alignment={align},MarginV={margin}'[vsub]")
                v_map = "[vsub]"

        if filters:
            cmd.extend(["-filter_complex", ";".join(filters)])
            
        cmd.extend(["-map", v_map, "-map", a_map, "-c:v", hw_enc] + hw_params + ["-c:a", "aac", "-ar", "44100", "-ac", "2", "-video_track_timescale", "30000", "-shortest", f_out])
        
        self.exec_ffmpeg(cmd, cwd=temp_dir)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = VideoBatchEditor()
    app.mainloop()