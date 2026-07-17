import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from downloader import AUDIO_FORMAT_CODECS, VIDEO_QUALITY_OPTIONS, DownloadCancelled, Downloader
from upscaler import TARGET_LONG_SIDE, ai_upscale, fast_resize

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Media Downloader")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Media Downloader")
        self.geometry("640x560")
        self.minsize(560, 480)

        self.downloader = None
        self.busy = False
        self.last_saved_dir = DEFAULT_DOWNLOAD_DIR
        self.ui_queue = queue.Queue()

        self._build_ui()
        self.after(100, self._poll_queue)

    # ---------------------------------------------------------------- UI ---

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        url_frame = ttk.Frame(self)
        url_frame.pack(fill="x", **pad)
        ttk.Label(url_frame, text="Link:").pack(side="left")
        self.url_var = tk.StringVar()
        ttk.Entry(url_frame, textvariable=self.url_var).pack(side="left", fill="x", expand=True, padx=(6, 0))

        type_frame = ttk.LabelFrame(self, text="What are you downloading?")
        type_frame.pack(fill="x", **pad)
        self.type_var = tk.StringVar(value="Video")
        for value in ("Video", "Audio", "Image / File"):
            ttk.Radiobutton(
                type_frame, text=value, variable=self.type_var, value=value, command=self._refresh_option_visibility
            ).pack(side="left", padx=10, pady=6)

        # Container that always holds exactly one of the three option frames below,
        # so it stays in a fixed position in the layout regardless of which is shown.
        self.options_container = ttk.Frame(self)
        self.options_container.pack(fill="x", **pad)

        # Video options
        self.video_frame = ttk.LabelFrame(self.options_container, text="Video quality")
        self.quality_var = tk.StringVar(value="1080p")
        for label in VIDEO_QUALITY_OPTIONS:
            ttk.Radiobutton(self.video_frame, text=label, variable=self.quality_var, value=label).pack(
                side="left", padx=10, pady=6
            )

        # Audio options
        self.audio_frame = ttk.LabelFrame(self.options_container, text="Audio format")
        self.audio_fmt_var = tk.StringVar(value="MP3")
        for label in AUDIO_FORMAT_CODECS:
            ttk.Radiobutton(self.audio_frame, text=label, variable=self.audio_fmt_var, value=label).pack(
                side="left", padx=10, pady=6
            )

        # Image options
        self.image_frame = ttk.LabelFrame(self.options_container, text="Image options")
        self.upscale_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.image_frame, text="Upscale after downloading", variable=self.upscale_var,
            command=self._refresh_option_visibility,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(6, 0))

        self.upscale_method_var = tk.StringVar(value="AI upscale")
        self.upscale_target_var = tk.StringVar(value="4K")
        self.upscale_controls = []
        r1 = ttk.Radiobutton(self.image_frame, text="AI upscale (best quality, slower)", variable=self.upscale_method_var, value="AI upscale")
        r2 = ttk.Radiobutton(self.image_frame, text="Fast resize (instant, lower quality)", variable=self.upscale_method_var, value="Fast resize")
        r1.grid(row=1, column=0, columnspan=4, sticky="w", padx=25)
        r2.grid(row=2, column=0, columnspan=4, sticky="w", padx=25)
        self.upscale_controls += [r1, r2]
        for i, label in enumerate(TARGET_LONG_SIDE):
            rb = ttk.Radiobutton(self.image_frame, text=label, variable=self.upscale_target_var, value=label)
            rb.grid(row=3, column=i, sticky="w", padx=25, pady=(0, 6))
            self.upscale_controls.append(rb)

        # Save location
        loc_frame = ttk.Frame(self)
        loc_frame.pack(fill="x", **pad)
        ttk.Label(loc_frame, text="Save to:").pack(side="left")
        self.folder_var = tk.StringVar(value=DEFAULT_DOWNLOAD_DIR)
        ttk.Entry(loc_frame, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, padx=(6, 6))
        ttk.Button(loc_frame, text="Browse...", command=self._browse_folder).pack(side="left")

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", **pad)
        self.download_btn = ttk.Button(btn_frame, text="Download", command=self._start_download)
        self.download_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self._stop_download, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.open_folder_btn = ttk.Button(btn_frame, text="Open folder", command=self._open_last_folder)
        self.open_folder_btn.pack(side="right")

        # Progress
        prog_frame = ttk.Frame(self)
        prog_frame.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(prog_frame, textvariable=self.status_var).pack(anchor="w", pady=(4, 0))

        # Log
        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(log_frame, height=10, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, side="left")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

        self._refresh_option_visibility()

    def _refresh_option_visibility(self):
        self.video_frame.pack_forget()
        self.audio_frame.pack_forget()
        self.image_frame.pack_forget()

        media_type = self.type_var.get()
        for frame in (self.video_frame, self.audio_frame, self.image_frame):
            frame.pack_forget()
        if media_type == "Video":
            self.video_frame.pack(fill="x")
        elif media_type == "Audio":
            self.audio_frame.pack(fill="x")
        else:
            self.image_frame.pack(fill="x")

        state = "normal" if self.upscale_var.get() else "disabled"
        for widget in self.upscale_controls:
            widget.configure(state=state)

    # ------------------------------------------------------------ actions ---

    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder_var.get() or os.path.expanduser("~"))
        if chosen:
            self.folder_var.set(chosen)

    def _open_last_folder(self):
        target = self.last_saved_dir if os.path.isdir(self.last_saved_dir) else self.folder_var.get()
        if os.path.isdir(target):
            os.startfile(target)
        else:
            messagebox.showinfo("Open folder", "That folder doesn't exist yet.")

    def _set_busy(self, busy):
        self.busy = busy
        self.download_btn.configure(state="disabled" if busy else "normal")
        self.stop_btn.configure(state="normal" if busy else "disabled")

    def _log(self, message):
        self.ui_queue.put(("log", message))

    def _set_progress(self, pct, status):
        self.ui_queue.put(("progress", (pct, status)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "log":
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", payload + "\n")
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                elif kind == "progress":
                    pct, status = payload
                    if pct is not None:
                        self.progress["mode"] = "determinate"
                        self.progress["value"] = pct
                    else:
                        self.progress["mode"] = "indeterminate"
                    self.status_var.set(status)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing link", "Paste a link first.")
            return
        out_dir = self.folder_var.get().strip() or DEFAULT_DOWNLOAD_DIR
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Can't create folder", str(e))
            return

        self.last_saved_dir = out_dir
        self._set_busy(True)
        self.progress["value"] = 0
        self.status_var.set("Starting...")
        threading.Thread(target=self._run_download, args=(url, out_dir), daemon=True).start()

    def _stop_download(self):
        if self.downloader:
            self.downloader.cancel()
            self._log("Stopping...")

    def _run_download(self, url, out_dir):
        self.downloader = Downloader(self._log, self._set_progress)
        media_type = self.type_var.get()
        try:
            if media_type == "Video":
                quality = self.quality_var.get()
                self._log(f"Downloading video ({quality})...")
                self.downloader.download_video(url, out_dir, quality)
                self._log("Video download complete.")
            elif media_type == "Audio":
                fmt = self.audio_fmt_var.get()
                self._log(f"Downloading audio as {fmt}...")
                self.downloader.download_audio(url, out_dir, fmt)
                self._log("Audio download complete.")
            else:
                self._log("Downloading file...")
                path, content_type = self.downloader.download_direct(url, out_dir)
                self._log(f"Saved: {os.path.basename(path)}")
                if self.upscale_var.get():
                    if content_type.startswith("image/") or path.lower().endswith(
                        (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
                    ):
                        target = self.upscale_target_var.get()
                        self._set_progress(None, "Upscaling...")
                        if self.upscale_method_var.get() == "AI upscale":
                            self._log("Upscaling with AI (this can take a little while)...")
                            result = ai_upscale(path, target, log=self._log)
                        else:
                            self._log("Resizing...")
                            result = fast_resize(path, target)
                        self._log(f"Upscaled image saved: {os.path.basename(result)}")
                    else:
                        self._log("Upscale skipped: the downloaded file isn't an image.")
            self._set_progress(100, "Done.")
        except DownloadCancelled:
            self._log("Cancelled.")
            self._set_progress(0, "Cancelled.")
        except Exception as e:
            self._log(f"Error: {e}")
            self._set_progress(0, "Failed.")
        finally:
            self._set_busy(False)


if __name__ == "__main__":
    app = App()
    app.mainloop()
