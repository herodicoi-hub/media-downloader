import os
import subprocess
import sys

from PIL import Image

TARGET_LONG_SIDE = {"2K": 2560, "4K": 3840}


def resource_path(relative):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def _suffixed_path(path, suffix, ext=None):
    root, orig_ext = os.path.splitext(path)
    return f"{root}{suffix}{ext or orig_ext}"


def fast_resize(src_path, target_label):
    """Lanczos resize up to the target long-side, in place quality. Returns new file path."""
    long_side = TARGET_LONG_SIDE[target_label]
    with Image.open(src_path) as img:
        w, h = img.size
        scale = long_side / max(w, h)
        if scale <= 1:
            return src_path
        new_size = (round(w * scale), round(h * scale))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.mode else "RGB")
        resized = img.resize(new_size, Image.LANCZOS)
        out_path = _suffixed_path(src_path, f"_{target_label}", ext=".png")
        resized.save(out_path)
    return out_path


def ai_upscale(src_path, target_label, log=print):
    """Runs the bundled Real-ESRGAN (ncnn-vulkan) binary for a 4x AI upscale,
    then resizes the result down to the requested target resolution.
    Falls back to a plain resize if the binary isn't available or fails."""
    exe = resource_path(os.path.join("bin", "realesrgan-ncnn-vulkan.exe"))
    if not os.path.exists(exe):
        log("AI upscaler not found in this build, using fast resize instead.")
        return fast_resize(src_path, target_label)

    tmp_out = _suffixed_path(src_path, "_ai4x_tmp", ext=".png")
    # realesrgan-ncnn-vulkan looks for its model files relative to its own folder,
    # so we run it with cwd=that folder - which means -i/-o must be absolute paths.
    cmd = [exe, "-i", os.path.abspath(src_path), "-o", os.path.abspath(tmp_out), "-n", "realesrgan-x4plus"]
    try:
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(exe),
            capture_output=True,
            text=True,
            timeout=600,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        log(f"AI upscale could not run ({e}), using fast resize instead.")
        return fast_resize(src_path, target_label)

    if result.returncode != 0 or not os.path.exists(tmp_out):
        err = (result.stderr or result.stdout or "unknown error").strip()
        log(f"AI upscale failed ({err}), using fast resize instead.")
        return fast_resize(src_path, target_label)

    final_path = _suffixed_path(src_path, f"_{target_label}", ext=".png")
    resized = fast_resize(tmp_out, target_label)
    if resized != tmp_out:
        os.replace(resized, final_path)
        os.remove(tmp_out)
    else:
        os.replace(tmp_out, final_path)
    return final_path
