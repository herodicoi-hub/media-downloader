# Media Downloader

A Windows desktop app that downloads media from (almost) any link:

- **Video** — choose highest frame rate, 1080p, or 720p
- **Audio** — extract as MP3 or WAV
- **Image / File** — save directly, with an optional upscale to 2K or 4K (real AI upscaling via Real-ESRGAN, or a fast plain resize)

Video/audio sites are handled by [yt-dlp](https://github.com/yt-dlp/yt-dlp) (supports thousands of sites). Anything else is saved with a plain direct download.

## Getting the app

You don't need Python or anything else installed. Every push to `main` builds a Windows `.exe` automatically:

1. Go to the **Actions** tab of this repo on GitHub.
2. Click the latest (green-checked) **Build Windows App** run.
3. Scroll down to **Artifacts** and download `MediaDownloader-windows`.
4. Unzip it anywhere and run `MediaDownloader.exe`.

## Notes

- Windows may show a "protect your PC" SmartScreen warning the first time you run it, because the exe isn't code-signed. Click **More info → Run anyway**.
- Everything runs locally on your PC — no accounts, no uploads.
