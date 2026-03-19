# train_yolo.py
# ============================================================
#  YOLO11 训练脚本 —— 自适应滑台视觉检测
#  功能：
#    1. 从 datasets/v1/train 自动按 70/15/15 分割数据集
#    2. 生成临时 data.yaml 供 YOLO 使用
#    3. 调用 ultralytics 训练 YOLOv8
#    4. 训练结束后生成详细评估指标图并保存到 model/yolo_YYYYMMDD_HHMMSS/
#  用法：
#    cd E:\1111AdaptiveSlidingTable\Code
#    python Vision/train_yolo.py
# ============================================================

import os
import sys
import shutil
import random
import yaml
from pathlib import Path
from datetime import datetime
import numpy as np
import matplotlib
matplotlib.use('Agg')          # 无 GUI 环境安全
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ─── 路径常量（相对于本脚本位置的 Code 根目录）───────────────
SCRIPT_DIR   = Path(__file__).resolve().parent          # Code/Vision/
CODE_ROOT    = SCRIPT_DIR.parent                         # Code/
SRC_IMAGES   = CODE_ROOT / 'datasets' / 'v1' / 'train' / 'images'
SRC_LABELS   = CODE_ROOT / 'datasets' / 'v1' / 'train' / 'labels'
SPLIT_ROOT   = CODE_ROOT / 'datasets' / 'v1_split'      # 临时分割数据集
MODEL_ROOT   = CODE_ROOT / 'model'

# ─── 数据集分割比例 ────────────────────────────────────────────
TRAIN_RATIO = 0.70
VAL_RATIO   = 0.15
TEST_RATIO  = 0.15

# ─── YOLO 训练参数 ─────────────────────────────────────────────
IMG_SIZE    = 512       # 数据集图片实际尺寸 512×512
EPOCHS      = 100
BATCH_SIZE  = 8         # 小数据集，小 batch 避免过拟合
PATIENCE    = 30        # early-stopping 耐心轮数
MODEL_BASE  = 'yolo11s.pt'   # YOLO11 small：RTX 4060 下 512×512 推理约 80~120 FPS，精度/速度最佳平衡

# ─── 类别信息（来自 data.yaml）────────────────────────────────
CLASS_NAMES = ['a', 'q']     # 与 datasets/v1/data.yaml 一致


# ══════════════════════════════════════════════════════════════
#  1. 数据集分割
# ══════════════════════════════════════════════════════════════
def split_dataset(seed: int = 42) -> Path:
    """
    将所有图片按 train/val/test 比例随机分割，
    复制（不移动）到 SPLIT_ROOT 下，返回 data.yaml 路径。
    """
    print("\n[Step 1] 数据集分割 ...")

    # 收集所有有对应标注文件的图片
    img_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    all_stems = []
    for f in SRC_IMAGES.iterdir():
        if f.suffix.lower() in img_exts:
            label_file = SRC_LABELS / (f.stem + '.txt')
            if label_file.exists():
                all_stems.append(f.stem)
            else:
                print(f"  [警告] 找不到标注文件，跳过: {f.name}")

    print(f"  有效样本数: {len(all_stems)}")

    # 随机打乱
    random.seed(seed)
    random.shuffle(all_stems)

    n_total = len(all_stems)
    n_train = int(n_total * TRAIN_RATIO)
    n_val   = int(n_total * VAL_RATIO)
    # n_test  = 剩余

    splits = {
        'train': all_stems[:n_train],
        'val'  : all_stems[n_train : n_train + n_val],
        'test' : all_stems[n_train + n_val:],
    }

    for split, stems in splits.items():
        print(f"  {split:5s}: {len(stems)} 张")

    # 清空并重建目录
    if SPLIT_ROOT.exists():
        shutil.rmtree(SPLIT_ROOT)

    for split in ['train', 'val', 'test']:
        (SPLIT_ROOT / split / 'images').mkdir(parents=True, exist_ok=True)
        (SPLIT_ROOT / split / 'labels').mkdir(parents=True, exist_ok=True)

    # 复制文件
    img_exts_list = list(img_exts)
    for split, stems in splits.items():
        for stem in stems:
            # 找到实际图片（可能是 jpg/png 等）
            src_img = None
            for ext in img_exts:
                candidate = SRC_IMAGES / (stem + ext)
                if candidate.exists():
                    src_img = candidate
                    break
            if src_img is None:
                print(f"  [警告] 找不到图片文件: {stem}，跳过")
                continue

            src_lbl = SRC_LABELS / (stem + '.txt')
            shutil.copy2(src_img, SPLIT_ROOT / split / 'images' / src_img.name)
            shutil.copy2(src_lbl, SPLIT_ROOT / split / 'labels' / (stem + '.txt'))

    # 生成 data.yaml
    yaml_path = SPLIT_ROOT / 'data.yaml'
    data_cfg = {
        'path'  : str(SPLIT_ROOT),
        'train' : 'train/images',
        'val'   : 'val/images',
        'test'  : 'test/images',
        'nc'    : len(CLASS_NAMES),
        'names' : CLASS_NAMES,
    }
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(data_cfg, f, allow_unicode=True, sort_keys=False)

    print(f"  data.yaml 已生成: {yaml_path}\n")
    return yaml_path, splits


# ══════════════════════════════════════════════════════════════
#  2. YOLO 训练
# ══════════════════════════════════════════════════════════════
def train_yolo(yaml_path: Path, output_dir: Path) -> object:
    """启动 YOLOv8 训练，返回 results 对象。"""
    from ultralytics import YOLO

    print(f"[Step 2] 开始训练 YOLOv8 ...")
    print(f"  基础模型  : {MODEL_BASE}")
    print(f"  图片尺寸  : {IMG_SIZE}")
    print(f"  Epochs    : {EPOCHS}")
    print(f"  Batch     : {BATCH_SIZE}")
    print(f"  输出目录  : {output_dir}\n")

    model = YOLO(MODEL_BASE)
    results = model.train(
        data        = str(yaml_path),
        epochs      = EPOCHS,
        imgsz       = IMG_SIZE,
        batch       = BATCH_SIZE,
        patience    = PATIENCE,
        project     = str(output_dir),
        name        = 'train',
        exist_ok    = True,
        # 数据增强（小数据集加强增强）
        hsv_h       = 0.015,
        hsv_s       = 0.7,
        hsv_v       = 0.4,
        degrees     = 5.0,
        translate   = 0.1,
        scale       = 0.5,
        fliplr      = 0.5,
        mosaic      = 1.0,
        mixup       = 0.1,
        # 优化器
        optimizer   = 'AdamW',
        lr0         = 1e-3,
        weight_decay= 5e-4,
        verbose     = True,
        workers     = 0,     
    )
    return model, results


# ══════════════════════════════════════════════════════════════
#  3. 评估指标图生成
# ══════════════════════════════════════════════════════════════
def load_results_csv(train_dir: Path) -> dict:
    """读取 ultralytics 自动生成的 results.csv"""
    import csv
    csv_path = train_dir / 'results.csv'
    if not csv_path.exists():
        print(f"  [警告] 未找到 results.csv: {csv_path}")
        return {}

    data = {}
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            for k, v in row.items():
                key = k.strip()
                if key not in data:
                    data[key] = []
                try:
                    data[key].append(float(v.strip()))
                except ValueError:
                    data[key].append(None)
    return data


def plot_training_metrics(train_dir: Path, output_dir: Path):
    """
    读取 results.csv，绘制 9 宫格专业训练曲线大图。
    """
    print("[Step 3] 生成训练指标图 ...")

    csv_data = load_results_csv(train_dir)
    if not csv_data:
        print("  [跳过] 无法读取训练数据，跳过自定义指标图")
        return

    epochs = csv_data.get('epoch', list(range(len(next(iter(csv_data.values()))))))

    # ── 定义要绘制的面板 ──────────────────────────────────────
    panels = [
        # (标题,          x轴,    [(csv_key, 图例标签, 颜色), ...],  y轴标签)
        ('Box Loss',      epochs, [
            ('train/box_loss', 'Train', '#EF5350'),
            ('val/box_loss',   'Val',   '#42A5F5'),
        ], 'Loss'),
        ('Class Loss',    epochs, [
            ('train/cls_loss', 'Train', '#EF5350'),
            ('val/cls_loss',   'Val',   '#42A5F5'),
        ], 'Loss'),
        ('DFL Loss',      epochs, [
            ('train/dfl_loss', 'Train', '#EF5350'),
            ('val/dfl_loss',   'Val',   '#42A5F5'),
        ], 'Loss'),
        ('Precision',     epochs, [
            ('metrics/precision(B)', 'Precision', '#66BB6A'),
        ], 'Precision'),
        ('Recall',        epochs, [
            ('metrics/recall(B)',    'Recall',    '#FFA726'),
        ], 'Recall'),
        ('mAP@0.5',       epochs, [
            ('metrics/mAP50(B)',     'mAP50',     '#AB47BC'),
        ], 'mAP'),
        ('mAP@0.5:0.95',  epochs, [
            ('metrics/mAP50-95(B)', 'mAP50-95',  '#26C6DA'),
        ], 'mAP'),
        ('Learning Rate', epochs, [
            ('lr/pg0', 'pg0', '#FFCA28'),
            ('lr/pg1', 'pg1', '#FF7043'),
            ('lr/pg2', 'pg2', '#8D6E63'),
        ], 'LR'),
        ('F1 Score (est.)', epochs, [], 'F1'),  # 由 P/R 计算
    ]

    # ── 绘图 ────────────────────────────────────────────────
    fig = plt.figure(figsize=(20, 15), facecolor='#1A1A2E')
    fig.suptitle('YOLOv8 Training Metrics Dashboard',
                 fontsize=20, color='white', fontweight='bold', y=0.98)

    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35)
    axes = [fig.add_subplot(gs[i // 3, i % 3]) for i in range(9)]

    def style_ax(ax, title, ylabel):
        ax.set_facecolor('#0D0D1A')
        ax.set_title(title, color='white', fontsize=11, fontweight='bold', pad=8)
        ax.set_xlabel('Epoch', color='#AAAAAA', fontsize=9)
        ax.set_ylabel(ylabel, color='#AAAAAA', fontsize=9)
        ax.tick_params(colors='#AAAAAA', labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor('#333355')
        ax.grid(True, color='#333355', linestyle='--', linewidth=0.5, alpha=0.7)

    for idx, (title, x, series, ylabel) in enumerate(panels):
        ax = axes[idx]
        style_ax(ax, title, ylabel)

        if title == 'F1 Score (est.)':
            # 估算 F1 = 2*P*R / (P+R)
            p = csv_data.get('metrics/precision(B)', [])
            r = csv_data.get('metrics/recall(B)', [])
            if p and r:
                f1 = []
                for pi, ri in zip(p, r):
                    if pi is not None and ri is not None and (pi + ri) > 0:
                        f1.append(2 * pi * ri / (pi + ri))
                    else:
                        f1.append(None)
                valid = [(e, v) for e, v in zip(x, f1) if v is not None]
                if valid:
                    ex, fy = zip(*valid)
                    ax.plot(ex, fy, color='#EC407A', linewidth=2, label='F1')
                    ax.fill_between(ex, fy, alpha=0.15, color='#EC407A')
                    # 标注最高点
                    best_f1 = max(fy)
                    best_ep = ex[fy.index(best_f1)]
                    ax.axvline(best_ep, color='#EC407A', linestyle=':', alpha=0.6)
                    ax.text(best_ep, best_f1, f' {best_f1:.3f}',
                            color='#EC407A', fontsize=8, va='bottom')
                    ax.legend(facecolor='#1A1A2E', labelcolor='white', fontsize=8)
            continue

        plotted = False
        for csv_key, label, color in series:
            vals = csv_data.get(csv_key, [])
            if not vals:
                continue
            valid = [(e, v) for e, v in zip(x, vals) if v is not None]
            if not valid:
                continue
            ex, vy = zip(*valid)
            ax.plot(ex, vy, color=color, linewidth=2, label=label)
            ax.fill_between(ex, vy, alpha=0.10, color=color)
            plotted = True

            # 标注最终值
            if vy:
                ax.text(ex[-1], vy[-1], f' {vy[-1]:.3f}',
                        color=color, fontsize=7.5, va='center')

        if plotted:
            ax.legend(facecolor='#1A1A2E', labelcolor='white', fontsize=8,
                      framealpha=0.7)

    out_path = output_dir / 'metrics_dashboard.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight',
                facecolor='#1A1A2E', edgecolor='none')
    plt.close(fig)
    print(f"  metrics_dashboard.png → {out_path}")


def plot_confusion_matrix_custom(train_dir: Path, output_dir: Path):
    """复制/增强 ultralytics 自动生成的混淆矩阵"""
    src = train_dir / 'confusion_matrix_normalized.png'
    if not src.exists():
        src = train_dir / 'confusion_matrix.png'
    if src.exists():
        dst = output_dir / 'confusion_matrix.png'
        shutil.copy2(src, dst)
        print(f"  confusion_matrix.png      → {dst}")


def plot_pr_curve_custom(train_dir: Path, output_dir: Path):
    """复制 PR 曲线"""
    for name in ['PR_curve.png', 'P_curve.png', 'R_curve.png', 'F1_curve.png']:
        src = train_dir / name
        if src.exists():
            shutil.copy2(src, output_dir / name)
            print(f"  {name:<26}→ {output_dir / name}")


def copy_best_model(train_dir: Path, output_dir: Path):
    """把 best.pt 复制到输出根目录，方便直接使用"""
    src = train_dir / 'weights' / 'best.pt'
    if src.exists():
        dst = output_dir / 'best.pt'
        shutil.copy2(src, dst)
        print(f"  best.pt                   → {dst}")
    src_last = train_dir / 'weights' / 'last.pt'
    if src_last.exists():
        shutil.copy2(src_last, output_dir / 'last.pt')
        print(f"  last.pt                   → {output_dir / 'last.pt'}")


def generate_summary_report(train_dir: Path, output_dir: Path,
                             splits: dict, elapsed_sec: float):
    """生成纯文本训练摘要报告"""
    csv_data = load_results_csv(train_dir)

    lines = []
    lines.append("=" * 60)
    lines.append("  YOLOv8 训练摘要报告")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    lines.append(f"  基础模型      : {MODEL_BASE}")
    lines.append(f"  图片尺寸      : {IMG_SIZE} x {IMG_SIZE}")
    lines.append(f"  训练轮数(上限): {EPOCHS}")
    lines.append(f"  Batch Size    : {BATCH_SIZE}")
    lines.append(f"  Early Stop    : {PATIENCE} 轮")
    lines.append(f"  总耗时        : {elapsed_sec/60:.1f} 分钟")
    lines.append("")
    lines.append("  数据集分布:")
    lines.append(f"    Train : {len(splits['train'])} 张")
    lines.append(f"    Val   : {len(splits['val'])} 张")
    lines.append(f"    Test  : {len(splits['test'])} 张")
    lines.append(f"    合计  : {sum(len(v) for v in splits.values())} 张")
    lines.append("")
    lines.append("  类别信息:")
    for i, name in enumerate(CLASS_NAMES):
        lines.append(f"    [{i}] {name}")
    lines.append("")

    if csv_data:
        def last_valid(key):
            vals = csv_data.get(key, [])
            valids = [v for v in vals if v is not None]
            return valids[-1] if valids else None

        lines.append("  最终指标 (最后一轮):")
        metrics = [
            ('metrics/precision(B)', 'Precision   '),
            ('metrics/recall(B)',    'Recall      '),
            ('metrics/mAP50(B)',     'mAP@0.5     '),
            ('metrics/mAP50-95(B)', 'mAP@0.5:0.95'),
            ('val/box_loss',         'Val Box Loss'),
            ('val/cls_loss',         'Val Cls Loss'),
        ]
        for key, label in metrics:
            val = last_valid(key)
            lines.append(f"    {label}: {val:.4f}" if val is not None else f"    {label}: N/A")

        # 最佳 mAP50
        map50_vals = [v for v in csv_data.get('metrics/mAP50(B)', []) if v is not None]
        if map50_vals:
            best_map50 = max(map50_vals)
            best_ep = map50_vals.index(best_map50) + 1
            lines.append(f"\n  最佳 mAP@0.5    : {best_map50:.4f}  (Epoch {best_ep})")

    lines.append("")
    lines.append(f"  输出目录: {output_dir}")
    lines.append("=" * 60)

    report_text = "\n".join(lines)
    with open(output_dir / 'summary.txt', 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(report_text)


# ══════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════
def main():
    import time

    # ── 创建本次训练专属输出目录（时间戳命名，绝不覆盖） ────
    run_tag = datetime.now().strftime('yolo_%Y%m%d_%H%M%S')
    output_dir = MODEL_ROOT / run_tag
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"  YOLO 训练脚本启动")
    print(f"  本次输出目录: {output_dir}")
    print(f"{'='*60}\n")

    # Step 1: 分割数据集
    yaml_path, splits = split_dataset()

    # Step 2: 训练
    t_start = time.time()
    model, results = train_yolo(yaml_path, output_dir)
    elapsed = time.time() - t_start

    # ultralytics 把结果放在 output_dir/train/
    train_dir = output_dir / 'train'

    # Step 3: 生成指标图
    print(f"\n[Step 3] 整理评估结果 ...")
    plot_training_metrics(train_dir, output_dir)
    plot_confusion_matrix_custom(train_dir, output_dir)
    plot_pr_curve_custom(train_dir, output_dir)
    copy_best_model(train_dir, output_dir)

    # Step 4: 生成文本摘要
    print(f"\n[Step 4] 生成训练摘要 ...")
    generate_summary_report(train_dir, output_dir, splits, elapsed)

    print(f"\n✅ 全部完成！结果保存在：{output_dir}\n")


if __name__ == '__main__':
    main()
