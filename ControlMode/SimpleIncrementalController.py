# SimpleIncrementalController.py
# 简单增量控制器：复刻 Root/Controller.py 的控制逻辑
# 算法：Bang-Bang 控制 —— 偏差超出死区时，向固定步长方向移动

import sys
import os
import time

# 将 Root 目录加入搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Root'))
from AppConfig import Config

from ControlMode.BaseController import BaseControlThread


class SimpleIncrementalController(BaseControlThread):
    """
    简单增量控制器（Bang-Bang / 开关控制）

    控制逻辑：
        1. 如果偏差 <= DEADZONE_PX（25px），不动（死区保护）
        2. 如果偏差 > 25px，向下移动固定步长 INCREMENTAL_STEP_DISTANCE
        3. 如果偏差 < -25px，向上移动固定步长 INCREMENTAL_STEP_DISTANCE

    特点：
        - 实现简单，无需标定，适合初期调试
        - 不依赖偏差大小调整速度（非比例控制）
        - 每次移动完整步长后等待 GRBL 确认，再进入下一帧
    """

    def control_logic(self, vision_data: dict):
        """
        简单增量控制算法实现

        Args:
            vision_data: Vision 线程传入的数据字典（已保证 detected=True）
        """
        deviation_y = vision_data.get('deviation_y')

        # 情况一：检测到滑块但未检测到目标直线（无法计算偏差）
        if deviation_y is None:
            print(f"[{self.name}] 检测到滑块，但未找到目标直线，跳过")
            return

        # 情况二：偏差在死区内，不动作（防止电机在零点附近反复抖动）
        if abs(deviation_y) <= Config.INCREMENTAL_DEADZONE_PX:
            # print(f"[{self.name}] 偏差={deviation_y:+.0f}px，在死区内，不移动")
            return

        # 情况三：偏差超出死区，计算移动方向
        # deviation_y = line_center_y - slider_center_y（像素坐标，向下为正）
        # deviation_y > 0: 直线在滑块下方 → 滑块需向下移动 → 电机负方向
        # deviation_y < 0: 直线在滑块上方 → 滑块需向上移动 → 电机正方向
        if deviation_y > Config.INCREMENTAL_DEADZONE_PX:
            move_distance = -Config.INCREMENTAL_STEP_DISTANCE   # 负数 = 向下
            direction = "下"
        else:
            move_distance = Config.INCREMENTAL_STEP_DISTANCE    # 正数 = 向上
            direction = "上"

        # 发送移动指令，阻塞等待 GRBL 的 ok 响应
        # （BaseController 的 move_motor 已保证同步，不会堆积指令）
        success = self.move_motor(move_distance, feed_rate=Config.INCREMENTAL_FEED_RATE)

        if success:
            print(
                f"[{self.name}] "
                f"偏差={deviation_y:+.0f}px → "
                f"向{direction}移动 {abs(move_distance):.1f}mm ✓"
            )
        else:
            print(f"[{self.name}] 移动指令失败，跳过本帧")
            return

        # 控制频率限速：在 GRBL 已接受指令后再等待，避免视觉帧率过快时刷爆队列
        # 注意：此 sleep 是在 move_motor 阻塞返回之后，属于"节流"而非"等待执行完成"
        time.sleep(Config.CONTROL_FREQ)
