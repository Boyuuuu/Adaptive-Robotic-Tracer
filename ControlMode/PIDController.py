# PIDController.py
# PID 控制器：基于物理-像素标定和电机运动标定，实现闭环位置控制
#
# 数据流：
#   deviation_y (px)
#       × PIXEL_TO_MM_RATIO → error_mm
#       → PID 计算 → output_mm（限幅）
#       → move_motor(output_mm)

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Root'))
from AppConfig import Config

from ControlMode.BaseController import BaseControlThread


class PIDController(BaseControlThread):
    """
    PID 位置控制器

    算法说明：
        error(t)    = deviation_y × PIXEL_TO_MM_RATIO          [mm]
        P           = Kp × error(t)
        I           = I_prev + Ki × error(t) × dt              [Anti-windup 限幅]
        D           = Kd × (error(t) - error(t-1)) / dt
        output      = clamp(P + I + D, -OUTPUT_LIMIT, +OUTPUT_LIMIT)

        output > 0 → 滑块向上移动（正方向）
        output < 0 → 滑块向下移动（负方向）

    死区（DEADZONE_MM）：
        |error_mm| ≤ DEADZONE_MM 时不发送任何指令，防止电机在零点附近抖动。

    调参顺序建议：
        1. 先设 Kp=0.5, Ki=0, Kd=0，观察系统响应（是否能收敛）
        2. 逐步增大 Kp 直到轻微震荡，然后加 Kd 抑制震荡
        3. 最后少量加 Ki 消除长期静差
    """

    def __init__(self, data_queue):
        super().__init__(data_queue)

        # PID 状态变量（每次运行初始化）
        self._integral   = 0.0    # 积分累积量 (mm)
        self._prev_error = None   # 上一帧误差，None 表示首帧（跳过微分计算）
        self._prev_ts    = None   # 上一帧时间戳

    # ══════════════════════════════════════════════════════════
    # 控制逻辑（由 BaseController.run() 每帧调用）
    # ══════════════════════════════════════════════════════════

    def control_logic(self, vision_data: dict):
        """
        PID 控制算法主体。

        Args:
            vision_data: Vision 线程数据字典（已保证 detected=True）
        """
        deviation_y = vision_data.get('deviation_y')
        timestamp   = vision_data.get('timestamp', time.time())

        # ── 情况一：无法计算偏差 ──────────────────────────────
        if deviation_y is None:
            print(f"[{self.name}] 未找到目标直线，跳过（积分保持）")
            self._prev_ts = timestamp   # 时间戳推进，避免下帧 dt 虚大
            return

        # ── 像素偏差 → 物理偏差（mm）──────────────────────────
        # deviation_y > 0：线在滑块下方，需向下 → 负方向
        # deviation_y < 0：线在滑块上方，需向上 → 正方向
        error_mm = deviation_y * Config.PIXEL_TO_MM_RATIO

        # ── 情况二：偏差在死区内，不动作 ─────────────────────
        if abs(error_mm) <= Config.PID_DEADZONE_MM:
            # 死区内清零积分，防止停止时积分继续累积
            self._integral   = 0.0
            self._prev_error = 0.0
            self._prev_ts    = timestamp
            return

        # ── 计算 dt ───────────────────────────────────────────
        if self._prev_ts is None:
            dt = Config.CONTROL_FREQ        # 首帧使用名义周期
        else:
            dt = timestamp - self._prev_ts
            dt = max(dt, 1e-3)             # 防止 dt=0 导致除零

        # ── P 项 ──────────────────────────────────────────────
        p_term = Config.PID_KP * error_mm

        # ── I 项（Anti-windup：限幅后再累积）────────────────
        self._integral += Config.PID_KI * error_mm * dt
        self._integral  = max(-Config.PID_INTEGRAL_LIMIT,
                              min(Config.PID_INTEGRAL_LIMIT, self._integral))
        i_term = self._integral

        # ── D 项（首帧跳过，避免虚假大导数）─────────────────
        if self._prev_error is None:
            d_term = 0.0
        else:
            d_term = Config.PID_KD * (error_mm - self._prev_error) / dt

        # ── 合并输出并限幅 ────────────────────────────────────
        output_mm = p_term + i_term + d_term
        output_mm = max(-Config.PID_OUTPUT_LIMIT,
                        min(Config.PID_OUTPUT_LIMIT, output_mm))

        # ── 方向修正 ──────────────────────────────────────────
        # error_mm > 0 表示线在下方 → 滑块需向下 → 电机负方向
        # output_mm 的符号已与 error_mm 一致，但电机方向需取反
        move_mm = -output_mm

        # ── 更新状态 ──────────────────────────────────────────
        self._prev_error = error_mm
        self._prev_ts    = timestamp

        # ── 发送运动指令 ──────────────────────────────────────
        success = self.move_motor(move_mm)

        if success:
            direction = "上" if move_mm > 0 else "下"
            print(
                f"[{self.name}] "
                f"偏差={deviation_y:+.0f}px ({error_mm:+.2f}mm) | "
                f"P={p_term:+.3f} I={i_term:+.3f} D={d_term:+.3f} | "
                f"输出={output_mm:+.3f}mm → 向{direction}移 {abs(move_mm):.3f}mm ✓"
            )
        else:
            print(f"[{self.name}] 移动指令失败，跳过本帧（积分保持）")
