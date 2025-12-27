import json
from pathlib import Path
import os

DEBUG_MODE = False

PROJECT_ROOT = Path(__file__).parent.parent.parent
CORE_FOLDER = PROJECT_ROOT / "core"
CONFIG_FOLDER = CORE_FOLDER / "config"
DATABASE_FOLDER = CORE_FOLDER / "dataBase"
LOGS_FOLDER = PROJECT_ROOT / "logs"
AUXILIARIES_FOLDER = PROJECT_ROOT / "auxiliaries"

CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)
DATABASE_FOLDER.mkdir(parents=True, exist_ok=True)
LOGS_FOLDER.mkdir(parents=True, exist_ok=True)
AUXILIARIES_FOLDER.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = CONFIG_FOLDER / "config.json"
DATABASE_FILE = DATABASE_FOLDER / "dados.json"

ARIA2C_PATH = AUXILIARIES_FOLDER / "aria2c" / "aria2c.exe"
YTDOWN_URL = "https://ytdown.to/pt2/"

QUALITIES = {
    "1080p": {"label": "MP4 - 1920x1080", "pattern": "/1080p"},
    "720p": {"label": "MP4 - 1280x720", "pattern": "/720p"},
    "480p": {"label": "MP4 - 854x480", "pattern": "/480p"},
    "360p": {"label": "MP4 - 640x360", "pattern": "/360p"},
    "240p": {"label": "MP4 - 426x240", "pattern": "/240p"},
    "144p": {"label": "MP4 - 256x144", "pattern": "/144p"},
    "128k": {"label": "M4A - 128K", "pattern": "/128k"},
    "48k": {"label": "M4A - 48K", "pattern": "/48k"},
}

DEFAULT_SETTINGS = {
    "max_simultaneous_links": 2,
    "max_simultaneous_downloads": 4,
    "aria2_connections": 8,
    "quality": "720p",
    "download_folder": str(Path.home() / "Downloads" / "YT Downloads"),
    "retry_attempts": 3,
}

POLLING_INTERVAL = 3
POLLING_TIMEOUT = 90
POLLING_RETRY = 5
POLLING_TIMEOUT_INCREASE = 30

def load_settings():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erro ao salvar configurações: {e}")
        return False

def get_download_folder():
    settings = load_settings()
    folder = settings.get("download_folder", str(Path.home() / "Downloads" / "YT Downloads"))
    Path(folder).mkdir(parents=True, exist_ok=True)
    return Path(folder)

def get_quality():
    settings = load_settings()
    quality = settings.get("quality", "480p")
    return quality if quality in QUALITIES else "480p"

def get_max_links():
    settings = load_settings()
    return settings.get("max_simultaneous_links", 2)

def get_max_downloads():
    settings = load_settings()
    return settings.get("max_simultaneous_downloads", 2)

def get_retry_attempts():
    settings = load_settings()
    return settings.get("retry_attempts", 3)