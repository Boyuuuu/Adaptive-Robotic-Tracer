# test_yolo_model.py
# ============================================================
#  YOLO 实时摄像头检测测试脚本
#  功能：
#    1. 打开指定摄像头进行实时画面采集
#    2. 使用指定 YOLO 模型逐帧推理
#    3. 在画面上绘制检测框、类别标签、置信度
#    4. 实时显示 FPS 和检测统计信息
#  用法：
#    cd E:\1111AdaptiveSlidingTable\Code
#    python test_code/test_yolo_model.py
#  按键：
#    Q / ESC  —— 退出程序
#    S        —— 保存当前帧到 save/ 目录
#    P        —— 暂停 / 继续
# ============================================================

from pathlib import Path

# ══════════════════════════════════════════════════════════════
#  ★ 全局配置参数（按需修改这里即可）★
# ══════════════════════════════════════════════════════════════

# ── 模型路径（最重要的配置项）────────────────────────────────
# 支持：.pt 文件（PyTorch）或 ONNX 等其他格式
# 可选路径示例：
#   最新自训练模型（推荐）：
MODEL_PATH = r"E:\1111AdaptiveSlidingTable\Code\model\yolo_20260304_112156\best.pt"
#   官方预训练权重（用于测试）：
# MODEL_PATH = r"E:\1111AdaptiveSlidingTable\Code\yolo11s.pt"

# ── 摄像头配置 ────────────────────────────────────────────────
CAMERA_INDEX    = 1        # 摄像头索引，0 = 默认摄像头，1 = 第二个摄像头...
CAMERA_WIDTH    = 640     # 采集分辨率宽度（像素），若摄像头不支持则自动降级
CAMERA_HEIGHT   = 480      # 采集分辨率高度（像素）
CAMERA_FPS      = 60       # 期望帧率（实际受摄像头硬件限制）

# ── 推理参数 ──────────────────────────────────────────────────
CONF_THRESHOLD  = 0.50     # 置信度阈值，低于此值的检测框将被过滤（0.0 ~ 1.0）
IOU_THRESHOLD   = 0.45     # NMS IoU 阈值，控制重叠框的去除程度（0.0 ~ 1.0）
IMG_SIZE        = 512      # 推理输入尺寸（像素），应与训练时一致（本项目训练用 512）
DEVICE          = ""       # 推理设备："" = 自动选择, "cpu" = CPU, "cuda:0" = GPU

# ── 显示配置 ──────────────────────────────────────────────────
SHOW_CONF       = True     # 是否在标签上显示置信度数值
SHOW_FPS        = True     # 是否在画面左上角显示 FPS
SHOW_COUNT      = True     # 是否显示每帧检测到的目标数量
BOX_THICKNESS   = 2        # 检测框线条粗细（像素）
FONT_SCALE      = 0.65     # 标签字体大小

# ── 保存设置 ──────────────────────────────────────────────────
SAVE_DIR        = Path(__file__).resolve().parent / "save"   # 保存目录
SAVE_WITH_BOXES = True     # True=保存带检测框的画面，False=保存原始帧

# ── 颜色调色板（BGR 格式，每个类别自动循环使用）──────────────
COLOR_PALETTE = [
    (  0, 200, 255),   # 亮橙黄
    ( 50, 220,  50),   # 绿色
    (255,  80,  80),   # 蓝色
    (200,  50, 200),   # 紫色
    ( 50, 200, 200),   # 青色
    (255, 180,  30),   # 蓝紫
    ( 80, 255, 180),   # 青绿
    (180,  80, 255),   # 粉紫
]

# ══════════════════════════════════════════════════════════════
#  以下为程序逻辑，一般不需要修改
# ══════════════════════════════════════════════════════════════

import sys
import time
import cv2
import numpy as np
from datetime import datetime


def check_model_path(model_path: str) -> Path:
    """检查模型文件是否存在，不存在则给出提示并退出"""
    p = Path(model_path)
    if not p.exists():
        print(f"\n[错误] 模型文件不存在: {p}")
        print("  请修改脚本顶部的 MODEL_PATH 变量，指向正确的 .pt 文件路径。")
        print("  示例：")
        print(r'  MODEL_PATH = r"E:\1111AdaptiveSlidingTable\Code\model\best.pt"')
        sys.exit(1)
    return p


def open_camera(index: int, width: int, height: int, fps: int) -> cv2.VideoCapture:
    """打开摄像头并配置分辨率/帧率"""
    print(f"\n[摄像头] 正在打开摄像头 {index} ...")
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)   # CAP_DSHOW 在 Windows 下延迟更低
    if not cap.isOpened():
        # 如果 CAP_DSHOW 失败，回退到默认后端
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"[错误] 无法打开摄像头 {index}，请检查 CAMERA_INDEX 配置。")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS,          fps)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_f = cap.get(cv2.CAP_PROP_FPS)
    print(f"[摄像头] 实际分辨率: {actual_w} x {actual_h}  |  帧率: {actual_f:.1f} FPS")
    return cap


def get_color(class_id: int) -> tuple:
    """根据类别 ID 从调色板获取颜色（BGR）"""
    return COLOR_PALETTE[class_id % len(COLOR_PALETTE)]


def draw_detections(frame: np.ndarray, results, class_names: list) -> np.ndarray:
    """
    在帧上绘制检测框和标签。
    results: ultralytics 推理结果对象
    """
    if results is None or len(results) == 0:
        return frame

    result = results[0]   # 只取第一帧结果

    if result.boxes is None or len(result.boxes) == 0:
        return frame

    boxes  = result.boxes.xyxy.cpu().numpy().astype(int)    # [N, 4] xyxy
    confs  = result.boxes.conf.cpu().numpy()                 # [N]
    cls_ids = result.boxes.cls.cpu().numpy().astype(int)    # [N]

    for (x1, y1, x2, y2), conf, cls_id in zip(boxes, confs, cls_ids):
        color = get_color(cls_id)
        name  = class_names[cls_id] if cls_id < len(class_names) else str(cls_id)

        # 绘制检测框
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, BOX_THICKNESS)

        # 构造标签文字
        label = f"{name}  {conf:.2f}" if SHOW_CONF else name

        # 计算标签背景大小
        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX,
                                              FONT_SCALE, 1)
        pad = 4
        bg_y1 = max(y1 - th - pad * 2, 0)
        bg_y2 = y1
        bg_x2 = min(x1 + tw + pad * 2, frame.shape[1])

        # 绘制半透明标签背景
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, bg_y1), (bg_x2, bg_y2), color, -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        # 绘制标签文字
        cv2.putText(frame, label,
                    (x1 + pad, bg_y2 - pad),
                    cv2.FONT_HERSHEY_SIMPLEX, FONT_SCALE,
                    (20, 20, 20), 1, cv2.LINE_AA)

    return frame


def draw_hud(frame: np.ndarray, fps: float, det_count: int) -> np.ndarray:
    """在画面左上角绘制 HUD 信息（FPS + 检测数量）"""
    h, w = frame.shape[:2]
    hud_lines = []
    if SHOW_FPS:
        hud_lines.append(f"FPS: {fps:5.1f}")
    if SHOW_COUNT:
        hud_lines.append(f"Det: {det_count}")

    for i, text in enumerate(hud_lines):
        y = 30 + i * 28
        # 描边（黑色阴影）
        cv2.putText(frame, text, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 0, 0), 3, cv2.LINE_AA)
        # 主字（白色）
        cv2.putText(frame, text, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (255, 255, 255), 2, cv2.LINE_AA)

    # 右上角显示暂停提示
    hint = "[S]保存  [P]暂停  [Q/ESC]退出"
    (tw, th), _ = cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    cv2.putText(frame, hint, (w - tw - 10, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, hint, (w - tw - 10, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (220, 220, 220), 1, cv2.LINE_AA)
    return frame


def save_frame(frame: np.ndarray):
    """保存当前帧到 SAVE_DIR"""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename  = SAVE_DIR / f"frame_{timestamp}.jpg"
    cv2.imwrite(str(filename), frame)
    print(f"[保存] 已保存: {filename}")


def main():
    # ── 检查模型 ──────────────────────────────────────────────
    model_path = check_model_path(MODEL_PATH)

    # ── 加载 YOLO 模型 ─────────────────────────────────────────
    print(f"\n[模型] 正在加载: {model_path}")
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[错误] 未安装 ultralytics，请执行：pip install ultralytics")
        sys.exit(1)

    model = YOLO(str(model_path))
    class_names = list(model.names.values())
    print(f"[模型] 加载成功！类别数: {len(class_names)}  →  {class_names}")

    # 确定推理设备
    device = DEVICE
    if device == "":
        try:
            import torch
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    print(f"[模型] 推理设备: {device}")

    # ── 打开摄像头 ─────────────────────────────────────────────
    cap = open_camera(CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS)

    # ── 主循环 ─────────────────────────────────────────────────
    print("\n[运行] 开始实时检测... 按 Q 或 ESC 退出\n")
    window_name = f"YOLO 实时检测  |  模型: {model_path.name}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, min(CAMERA_WIDTH, 1280), min(CAMERA_HEIGHT, 720))

    paused      = False
    fps_counter = 0
    fps_sum     = 0.0
    fps_display = 0.0
    fps_update_interval = 10    # 每 10 帧更新一次 FPS 显示
    last_frame  = None          # 暂停时保存最后一帧

    try:
        while True:
            t_start = time.perf_counter()

            # ── 读取帧 ────────────────────────────────────────
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    print("[警告] 摄像头读取失败，尝试重新连接...")
                    time.sleep(0.1)
                    continue
                last_frame = frame.copy()
            else:
                frame = last_frame.copy() if last_frame is not None else np.zeros(
                    (CAMERA_HEIGHT, CAMERA_WIDTH, 3), dtype=np.uint8)

            # ── YOLO 推理 ─────────────────────────────────────
            if not paused:
                results = model.predict(
                    source    = frame,
                    imgsz     = IMG_SIZE,
                    conf      = CONF_THRESHOLD,
                    iou       = IOU_THRESHOLD,
                    device    = device,
                    verbose   = False,     # 关闭控制台每帧打印
                )
                det_count = len(results[0].boxes) if results[0].boxes is not None else 0
            else:
                results   = None
                det_count = 0

            # ── 绘制结果 ──────────────────────────────────────
            display_frame = frame.copy()
            if not paused and results is not None:
                display_frame = draw_detections(display_frame, results, class_names)

            # FPS 计算
            elapsed = time.perf_counter() - t_start
            if not paused:
                fps_sum     += 1.0 / max(elapsed, 1e-6)
                fps_counter += 1
                if fps_counter >= fps_update_interval:
                    fps_display = fps_sum / fps_counter
                    fps_sum     = 0.0
                    fps_counter = 0

            # 暂停遮罩
            if paused:
                overlay = display_frame.copy()
                cv2.rectangle(overlay, (0, 0),
                              (display_frame.shape[1], display_frame.shape[0]),
                              (0, 0, 0), -1)
                cv2.addWeighted(overlay, 0.35, display_frame, 0.65, 0, display_frame)
                cv2.putText(display_frame, "PAUSED",
                            (display_frame.shape[1] // 2 - 80,
                             display_frame.shape[0] // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 2.0,
                            (0, 200, 255), 4, cv2.LINE_AA)

            # HUD 覆盖
            display_frame = draw_hud(display_frame, fps_display, det_count)

            cv2.imshow(window_name, display_frame)

            # ── 按键处理 ──────────────────────────────────────
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):         # Q / ESC 退出
                print("\n[退出] 用户按键退出。")
                break
            elif key in (ord('s'), ord('S')):            # S 保存
                save_img = display_frame if SAVE_WITH_BOXES else (last_frame if last_frame is not None else display_frame)
                save_frame(save_img)
            elif key in (ord('p'), ord('P')):            # P 暂停/继续
                paused = not paused
                print(f"[暂停] {'已暂停' if paused else '已继续'}")

    except KeyboardInterrupt:
        print("\n[退出] Ctrl+C 中断。")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("[完成] 摄像头已释放，窗口已关闭。")


if __name__ == "__main__":
    main()
