import os
import sys
import threading

import requests
import yt_dlp


def resource_path(relative):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


BIN_DIR = resource_path("bin")

VIDEO_QUALITY_OPTIONS = {
    "Highest frame rate": {
        "format": "bv*+ba/b",
        "format_sort": ["fps", "res"],
    },
    "1080p": {
        "format": "bv*[height<=1080]+ba/b[height<=1080]",
        "format_sort": ["res", "fps"],
    },
    "720p": {
        "format": "bv*[height<=720]+ba/b[height<=720]",
        "format_sort": ["res", "fps"],
    },
}

AUDIO_FORMAT_CODECS = {
    "MP3": "mp3",
    "WAV": "wav",
}

CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "application/pdf": ".pdf",
}


class DownloadCancelled(Exception):
    pass


class Downloader:
    """Wraps yt-dlp (for supported sites) and plain HTTP (for direct file links)."""

    def __init__(self, log_callback, progress_callback):
        self.log = log_callback
        self.progress = progress_callback
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def _check_cancel(self):
        if self._cancel.is_set():
            raise DownloadCancelled()

    def _ydl_progress_hook(self, d):
        self._check_cancel()
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed")
            if total:
                pct = downloaded / total * 100
                msg = f"Downloading... {pct:.1f}%"
            else:
                pct = None
                msg = f"Downloading... {downloaded / (1024 * 1024):.1f} MB"
            if speed:
                msg += f" ({speed / (1024 * 1024):.2f} MB/s)"
            self.progress(pct, msg)
        elif d["status"] == "finished":
            self.progress(100, "Processing / converting...")

    def _base_ydl_opts(self, out_dir):
        opts = {
            "outtmpl": os.path.join(out_dir, "%(title).150B [%(id)s].%(ext)s"),
            "progress_hooks": [self._ydl_progress_hook],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "restrictfilenames": False,
        }
        if os.path.isdir(BIN_DIR):
            opts["ffmpeg_location"] = BIN_DIR
        return opts

    def download_video(self, url, out_dir, quality_label):
        choice = VIDEO_QUALITY_OPTIONS[quality_label]
        ydl_opts = self._base_ydl_opts(out_dir)
        ydl_opts.update(
            {
                "format": choice["format"],
                "format_sort": choice["format_sort"],
                "merge_output_format": "mp4",
            }
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    def download_audio(self, url, out_dir, format_label):
        codec = AUDIO_FORMAT_CODECS[format_label]
        postprocessor = {"key": "FFmpegExtractAudio", "preferredcodec": codec}
        if codec == "mp3":
            postprocessor["preferredquality"] = "0"
        ydl_opts = self._base_ydl_opts(out_dir)
        ydl_opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [postprocessor],
            }
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    def download_direct(self, url, out_dir):
        """Plain HTTP download for direct file links (images, or any other file type)."""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        with requests.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "").split(";")[0].strip()
            total = int(r.headers.get("Content-Length", 0) or 0)
            filename = self._filename_for(url, content_type)
            path = os.path.join(out_dir, filename)
            path = self._unique_path(path)
            downloaded = 0
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    self._check_cancel()
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        self.progress(pct, f"Downloading... {pct:.1f}%")
                    else:
                        self.progress(None, f"Downloading... {downloaded / (1024 * 1024):.1f} MB")
            return path, content_type

    def _filename_for(self, url, content_type):
        base = os.path.basename(url.split("?")[0].split("#")[0]) or "download"
        if "." not in base:
            base += CONTENT_TYPE_EXT.get(content_type, "")
        return base or "download"

    @staticmethod
    def _unique_path(path):
        if not os.path.exists(path):
            return path
        root, ext = os.path.splitext(path)
        i = 1
        while os.path.exists(f"{root} ({i}){ext}"):
            i += 1
        return f"{root} ({i}){ext}"
