#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""app-icon.png -> app-icon.ico（多尺寸），供 Windows 快捷方式 / 任务栏使用。

用法： python build/make_icon.py
"""
import os
import sys
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(ROOT, "app-icon.png")
out = os.path.join(ROOT, "app-icon.ico")
im = Image.open(src).convert("RGBA")
bbox = im.getbbox()
print("bbox", bbox, "size", im.size)

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
frames = []
for s in SIZES:
    f = im.resize((s, s), Image.LANCZOS)
    if s <= 48:
        # 小尺寸补一点点锐度，避免细线糊成一团
        f = f.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=1))
    frames.append(f)

big = frames[-1]
big.save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
print("written", out)
with Image.open(out) as chk:
    print("ico sizes:", sorted(chk.ico.sizes()))
