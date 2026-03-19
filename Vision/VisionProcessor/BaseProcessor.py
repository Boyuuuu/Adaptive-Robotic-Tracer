# Code/Vision/VisionProcessor/BaseProcessor.py
from abc import ABC, abstractmethod
import numpy as np
from dataclasses import dataclass
from typing import Optional

@dataclass
class VisionResult:
    """
    视觉识别结果标准数据类 (Data Class)
    统一了所有视觉算法的输出接口格式。
    不管用什么算法，输出都得是这些字段，这样控制逻辑才不会报错。
    """
    detected: bool = False                # 是否检测到目标
    slider_center_y: Optional[int] = None # 滑块中心Y坐标
    slider_top_y: Optional[int] = None    # 滑块顶部Y坐标
    slider_bottom_y: Optional[int] = None # 滑块底部Y坐标
    line_center_y: Optional[int] = None   # 直线中心Y坐标
    deviation_y: Optional[int] = None     # Y轴偏差 (直线 - 滑块) (滤波后)
    raw_deviation_y: Optional[int] = None # 未滤波的原始偏差 (用于调试和后处理滤波)
    timestamp: float = 0.0                # 图像处理完成的时间戳

class BaseProcessor(ABC):
    """
    视觉处理器基类 (Abstract Interface)
    所有具体的识别算法都需要继承此类，并实现相应的方法。
    """
    
    @abstractmethod
    def process(self, frame: np.ndarray) -> VisionResult:
        """
        核心处理方法：接受一帧图像，返回识别结果。
        【所有子类必须实现此方法】
        
        Args:
            frame: 从摄像头获取的一帧 numpy array 图像数据。
            
        Returns:
            VisionResult: 识别结果数据结构。
        """
        pass

    def draw_debug(self, frame: np.ndarray, result: VisionResult) -> np.ndarray:
        """
        调试绘图规范：负责在原图上画框、画中心点等。
        【可选覆盖】：可以在这里定义默认的绘制逻辑，或者子类覆写定制化绘制。
        
        Args:
            frame: 原始图像
            result: process() 产生的结果
            
        Returns:
            np.ndarray: 绘制上标注信息后的图像
        """
        return frame
