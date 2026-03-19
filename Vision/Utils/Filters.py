# Code/Vision/Utils/Filters.py
import math

class EMAFilter:
    """
    数据滤波器工具类
    负责做平滑（如指数移动平均 EMA）和去除异常跳跃毛刺（限幅）。
    这能将视觉中杂乱跳跃的识别点变成顺滑的数值曲线，从而防范电机抖震！
    """
    def __init__(self, alpha: float, max_jump: float = float('inf')):
        """
        Args:
            alpha (float): EMA 平滑系数（0到1之间）。
                           0=完全不跟踪新值(卡死)，1=无滤波全盘接收。
                           一般推荐 0.2~0.4，越小越平滑但有滞后。
            max_jump (float): 限幅阈值（比如允许一次最大跳动 10 个像素），
                              单帧数据变化假如超过这里，就会被狠狠截断抛弃，
                              这对遮挡、抖动抗干扰很有用。
        """
        self.alpha = alpha
        self.max_jump = max_jump
        self.filtered_value = None

    def update(self, raw_value: float) -> float:
        """
        每次喂给这一个函数一个最新的原始数值（比如摄像头一帧算完的 deviation_y），
        内部就会做处理然后发回更顺畅的处理结果。
        """
        if raw_value is None:
            return None
            
        # 层一：跳跃限幅 —— 单帧变化假如真超过阈值则直接截断到边缘
        if self.filtered_value is not None:
            delta = raw_value - self.filtered_value
            if abs(delta) > self.max_jump:
                raw_value = self.filtered_value + self.max_jump * (1 if delta > 0 else -1)

        # 层二：EMA 低通滤波 (Exponential Moving Average)
        if self.filtered_value is None:
            self.filtered_value = float(raw_value)  # 没记录就说明是开头第一帧，直接接受
        else:
            self.filtered_value = self.alpha * raw_value + (1 - self.alpha) * self.filtered_value

        return round(self.filtered_value)

    def reset(self):
        """假如发现目标丢了或者目标消失，需要调它清空内部旧记忆，以免粘滞"""
        self.filtered_value = None
