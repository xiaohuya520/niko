"""用 NiKo 本人高清照片生成主屏图标 + 站内头像。

流程：
  1. 从 Liquipedia 下载原图（assets/_src/NiKo_orig.jpg，2048x1366）
  2. Haar 级联做人脸检测，算出脸部中心
  3. 以脸为中心裁正方形（头顶留白少一点、下巴下方留到胸口）
  4. LANCZOS 降采样 + 轻度 USM 锐化，输出全档位图标

用法：
  python make_avatar_icon.py              # 正常生成
  python make_avatar_icon.py --debug      # 额外输出裁切框可视化，人工核对用
"""
import pathlib
import sys

import cv2
import numpy as np
from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).parent
SRC = ROOT / "assets" / "_src" / "NiKo_orig.jpg"
CASCADE = ROOT / "assets" / "_src" / "haarcascade_frontalface_default.xml"
OUT = ROOT / "assets" / "pixel"
PLAYERS = ROOT / "assets" / "players"
OUT.mkdir(parents=True, exist_ok=True)
PLAYERS.mkdir(parents=True, exist_ok=True)

MASTER = 1024          # 图标母版尺寸
FRAME = 3.4            # 取景系数：方形边长 ≈ 脸高 * FRAME（越大留白越多）
EYE_BIAS = 0.38        # 方框中心相对脸心下移的比例（保留发际线以上空间）


def detect_face(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.equalizeHist(g)
    clf = cv2.CascadeClassifier(str(CASCADE))
    faces = clf.detectMultiScale(g, scaleFactor=1.08, minNeighbors=6,
                                 minSize=(60, 60))
    if len(faces) == 0:
        # 放宽再试一次
        faces = clf.detectMultiScale(g, scaleFactor=1.05, minNeighbors=3,
                                     minSize=(40, 40))
    if len(faces) == 0:
        return None
    # 取面积最大的一张脸
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return (int(x), int(y), int(w), int(h))


def pad_top_mirror(img, need, blur=9):
    """在图像顶部拼一条镜像翻转 + 模糊的延展带。

    NiKo 这张原图的头顶几乎贴着照片上边缘，直接裁方形会切掉头发。
    用镜像延展补出头部上方的空间，观感自然，不像硬填色。
    """
    if need <= 0:
        return img, 0
    strip = img.crop((0, 0, img.width, min(need, img.height))).transpose(
        Image.FLIP_TOP_BOTTOM)
    if strip.height < need:                       # 不够就先拉伸补齐
        strip = strip.resize((img.width, need), Image.LANCZOS)
    strip = strip.filter(ImageFilter.GaussianBlur(blur))
    canvas = Image.new("RGB", (img.width, img.height + need))
    canvas.paste(strip, (0, 0))
    canvas.paste(img, (0, need))
    return canvas, need


def square_box(img_w, img_h, face, frame=FRAME, bias=EYE_BIAS):
    """按脸的位置与大小算一个正方形裁切框，并夹在图像内。"""
    fx, fy, fw, fh = face
    cx = fx + fw / 2
    cy = fy + fh / 2 + fh * bias          # 中心下移，给头顶留空间
    side = fh * frame
    # 若超出边界，先缩边长再平移，保证框完整落在图内
    side = min(side, img_w, img_h)
    x0 = cx - side / 2
    y0 = cy - side / 2
    x0 = min(max(0.0, x0), img_w - side)
    y0 = min(max(0.0, y0), img_h - side)
    return (int(round(x0)), int(round(y0)),
            int(round(x0 + side)), int(round(y0 + side)))


def main():
    if not SRC.exists():
        print("缺原图：", SRC)
        return 1

    bgr = cv2.imdecode(np.fromfile(str(SRC), dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        bgr = cv2.imread(str(SRC))
    h, w = bgr.shape[:2]
    print("原图:", w, "x", h)

    face = detect_face(bgr)
    if face:
        fx, fy, fw, fh = face
        print(f"检测到人脸: x={fx} y={fy} {fw}x{fh} "
              f"(占图高 {fh/h*100:.1f}%)")

        rgb_full = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        # 头顶至少留 0.5 个脸高，不够就镜像延展补
        rgb_full, pad = pad_top_mirror(rgb_full, int(fh * 0.5) - fy)
        if pad:
            print(f"顶部镜像延展 {pad}px，避免切到头发")
            face = (fx, fy + pad, fw, fh)
        box = square_box(rgb_full.width, rgb_full.height, face)
        im = rgb_full
    else:
        print("未检测到人脸，退化为居中裁切")
        im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        side = min(w, h)
        box = ((w - side) // 2, (h - side) // 2,
               (w - side) // 2 + side, (h - side) // 2 + side)
    print("裁切框:", box)

    if face:
        side = box[2] - box[0]
        top_gap = face[1] - box[1]                 # 脸框上方留白
        print(f"构图：方形边长 {side}px，"
              f"头顶留白 {top_gap}px（{top_gap/side*100:.1f}%），"
              f"脸高占 {face[3]/side*100:.1f}%")

    if "--debug" in sys.argv:
        dbg = im.copy()
        from PIL import ImageDraw
        d = ImageDraw.Draw(dbg)
        d.rectangle(box, outline=(255, 0, 0), width=6)
        if face:
            fx, fy, fw, fh = face
            d.rectangle((fx, fy, fx + fw, fy + fh), outline=(0, 255, 0), width=6)
        dbg.resize((dbg.width // 3, dbg.height // 3),
                   Image.LANCZOS).save(ROOT / "assets" / "_src" / "crop_debug.png")
        print("裁切预览已保存 assets/_src/crop_debug.png")

    crop = im.crop(box)
    master = crop.resize((MASTER, MASTER), Image.LANCZOS)
    # 轻度锐化：小尺寸下更"精神"，又不至于出白边
    master = master.filter(ImageFilter.UnsharpMask(radius=1.2, percent=85, threshold=2))

    out_sizes = {
        "icon-1024.png": 1024,          # iOS 主屏首选高清源
        "icon-512.png": 512,            # PWA / Android
        "icon-192.png": 192,            # PWA / Android
        "apple-touch-icon.png": 180,    # iOS 主屏标准档
        "apple-touch-icon-152.png": 152,
        "favicon_256.png": 256,
        "favicon-48.png": 48,
        "favicon.png": 32,
    }
    for name, size in out_sizes.items():
        master.resize((size, size), Image.LANCZOS).save(
            OUT / name, optimize=True)
        print(f"{name:26s} {size}x{size}")

    # 站内头像：512 足够高清，体积可控
    master.resize((512, 512), Image.LANCZOS).save(
        PLAYERS / "NiKo.jpg", quality=90, optimize=True)
    print("assets/players/NiKo.jpg      512x512 (站内头像同步高清化)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
