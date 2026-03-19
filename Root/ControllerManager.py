# Root/ControllerManager.py
# 控制器注册器 / 工厂
#
# 使用方法：
#   在 main.py 中：
#       from ControllerManager import create_controller
#       controller_t = create_controller(shared_queue)
#
#   在 AppConfig.py 中修改 CONTROL_MODE 即可切换算法：
#       CONTROL_MODE = 'simple_incremental'

import sys
import os

# 将 ControlMode 目录的父目录（Code/）加入搜索路径
# 这使得 "from ControlMode.XxxController import ..." 的写法可以正常工作
_code_dir = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.abspath(_code_dir))

# 同时将 Root 目录自身加入路径（给 ControlMode 里的模块 import AppConfig 用）
sys.path.insert(0, os.path.dirname(__file__))

from AppConfig import Config

# ══════════════════════════════════════════════════════════════════
#  控制器注册表
#  格式：{ 'AppConfig.CONTROL_MODE 中填写的字符串': 对应的控制器类 }
#
#  ✅ 添加新控制模式时，只需要：
#     1. 在 ControlMode/ 目录下新建控制器文件并继承 BaseControlThread
#     2. 在下方 import 并注册到 CONTROLLER_REGISTRY
#     3. 在 AppConfig.CONTROL_MODE 中填写对应的 key
# ══════════════════════════════════════════════════════════════════

from ControlMode.SimpleIncrementalController import SimpleIncrementalController
from ControlMode.CalibrationController import CalibrationController
from ControlMode.PIDController import PIDController
# from ControlMode.AdaptiveController import AdaptiveController  # 未来扩展：自适应控制

CONTROLLER_REGISTRY: dict = {
    'simple_incremental':       SimpleIncrementalController,
    'Motor_Motion_Calibration': CalibrationController,
    'pid':                      PIDController,
    # 'adaptive':               AdaptiveController,
}


# ══════════════════════════════════════════════════════════════════
#  工厂函数
# ══════════════════════════════════════════════════════════════════

def create_controller(data_queue):
    """
    根据 AppConfig.CONTROL_MODE 创建对应的控制器实例。

    Args:
        data_queue: 与 VisionThread 共享的数据队列

    Returns:
        BaseControlThread 子类的实例（未调用 start()，由调用方负责启动）

    Raises:
        ValueError: 当 CONTROL_MODE 未在注册表中时抛出，并列出所有合法值
    """
    mode = Config.CONTROL_MODE

    if mode not in CONTROLLER_REGISTRY:
        available = list(CONTROLLER_REGISTRY.keys())
        raise ValueError(
            f"\n[ControllerManager] 未知的控制模式: '{mode}'\n"
            f"请在 AppConfig.py 的 CONTROL_MODE 中填写以下之一:\n"
            + "\n".join(f"  - '{k}'" for k in available)
        )

    controller_cls = CONTROLLER_REGISTRY[mode]
    print(f"[ControllerManager] 控制模式: '{mode}' → {controller_cls.__name__}")
    return controller_cls(data_queue)


def list_available_modes() -> list:
    """返回所有已注册的控制模式名称列表（用于调试/显示）"""
    return list(CONTROLLER_REGISTRY.keys())
