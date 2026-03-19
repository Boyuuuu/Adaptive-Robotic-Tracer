# Adaptive Sliding Table Control System (自适应滑台控制系统)

本项目是一个结合了 **OpenCV 传统图像处理** 与 **YOLO 深度学习目标检测** 的实时反馈控制系统。通过视觉传感器捕捉滑块位置与目标偏移，实时调节电机运动实现自适应跟踪。

---

## 🏗️ 项目架构

- **Root/**: 核心控制逻辑 (`main.py`, `VisionManager.py`, `ControllerManager.py`)
- **Vision/**: 模块化视觉引擎
  - `VisionProcessor/`: 包含传统 (Traditional) 与 AI (YOLO) 识别策略
  - `Camera/`: 多线程高帧率采集模块
- **ControlMode/**: PID 控制器与标定算法
- **AppConfig.py**: 全局统一配置文件（端口、模式、阈值、比例因子等）

---

## 🚀 快速启动

### 1. 环境准备
确保拥有 `Python 3.8+` 环境（推荐使用 Conda）：
```bash
pip install -r requirements.txt
```

### 2. 参数配置
在 `Root/AppConfig.py` 中根据实际硬件调整：
- `SERIAL_PORT`: 电机控制板的 COM 口
- `VISION_MODE`: 选择 `'traditional'` 或 `'yolo'`
- `CONTROL_MODE`: 选择控制器（`'pid'`, `'simple_incremental'`, 或 `'false'` 纯视觉测试）

### 3. 运行程序
在项目根目录下直接运行：
```bash
python run.py
```

---

## ⌨️ 快捷键说明
- **[Q]**: 退出程序并安全关闭串口/相机
- **[S]**: 保存当前摄像头原始帧（用于数据集采集）
- **[P]**: 暂停/恢复 (仅部分测试脚本支持)

---

## 🛠️ 核心开发
- **PID 控制**: 支持实时调参并具有死区保护。
- **模块化设计**: 可以在不改动核心逻辑的情况下，通过配置文件一键切换视觉算法或控制算法。
