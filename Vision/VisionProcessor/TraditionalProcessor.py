# Code/Vision/VisionProcessor/TraditionalProcessor.py
import cv2
import numpy as np
import time
import sys
import os

# 将上级父文件夹的模块暴露出方便引用（找寻 BaseProcessor 这种同级）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from BaseProcessor import BaseProcessor, VisionResult

# 将 Root 路径加入进来以读取 AppConfig
_root_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'Root')
sys.path.insert(0, os.path.abspath(_root_dir))
from AppConfig import Config

class TraditionalProcessor(BaseProcessor):
    """
    传统 OpenCV 图像算法类（策略）
    主要步骤：
      1. 裁剪感兴趣区域（ROI）这能提速和避免环境乱七八糟物体的干扰
      2. 图像降噪和色彩空间转换由于设备在厂房中光源不稳定，通过转 HSV 色系识别能更好抗强光和暗光。
      3. 色彩提取和形态学闭开运算（黑白修补），将杂音颗粒消除。
      4. 找矩形框！算出最旁边的框，再算出黑色长条矩形的滑块中心！
      5. 在最后一步输出标准 VisionResult 给上面的“VisionManager”老板
    """
    def __init__(self):
        super().__init__()
        # 记录内部处理的一些过程数据（字典和格式），好提供给之后绘画调试框框
        self._roi_coords = (0, 0, 0, 0)
        self._black_rect = None
        self._rightmost_rect = None

    def process(self, frame: np.ndarray) -> VisionResult:
        # 1. 工厂初始化产品返回包装盒
        result = VisionResult(timestamp=time.time())
        
        # 2. 剪视频帧上的指定 ROI（提取有意义区域）
        x1, y1, x2, y2 = Config.ROI_COORDS
        height, width = frame.shape[:2]
        
        # 为了不崩溃，需要防御性规范长宽（防超出界限）
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)
        roi_frame = frame[y1:y2, x1:x2]
        
        # 记录给画画用的
        self._roi_coords = (x1, y1, x2, y2)
        
        # 3. 图像滤波，去除高斯底噪；之后换格式（转色域至更具特征强度的HSV）
        blurred = cv2.GaussianBlur(roi_frame, (3, 3), 0)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        
        # 4. 做颜色分离提取。一绿线标靶掩码（mask_green），二黑色滑块掩码（mask_black）
        mask_green = cv2.inRange(hsv, Config.HSV_LOWER, Config.HSV_UPPER)
        
        # 深色，甚至纯黑（不限定色相，只有暗就可以了即明度 V极低）
        black_lower = np.array([0, 0, 0])
        black_upper = np.array([180, 255, 50])
        mask_black = cv2.inRange(hsv, black_lower, black_upper)
        
        # 5. 上“整形大工程”（形态学运算）
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        # （把不连贯的破散黑色点和白点先处理补大窟窿、断线，再去除外围小杂点）
        mask_black = cv2.morphologyEx(mask_black, cv2.MORPH_OPEN, kernel, iterations=2)
        mask_black = cv2.morphologyEx(mask_black, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        mask_green = cv2.morphologyEx(mask_green, cv2.MORPH_OPEN, kernel, iterations=2)
        mask_green = cv2.morphologyEx(mask_green, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        # 6. 计算最黑的一个目标滑块位置
        # (寻找轮廓信息，用一个很简便和快捷的外廓多边形查找)
        contours_black, _ = cv2.findContours(mask_black, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        black_rect = None
        min_x = float('inf')
        
        for contour in contours_black:
            area = cv2.contourArea(contour)
            if area < Config.SLIDER_AREA_MIN or area > Config.SLIDER_AREA_MAX:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            # 我们只需要知道找“最贴近画面左侧”也就是在滑道上面的那个长片
            if x < min_x:
                min_x = x
                black_rect = {'x': x, 'y': y, 'w': w, 'h': h, 'area': area}
                
        self._black_rect = black_rect 
                
        # 7. 计算标靶上的右侧绿色块来作为横线追踪定位基础点
        contours_green, _ = cv2.findContours(mask_green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rightmost_rect = None
        max_x = -1
        
        for contour in contours_green:
            area = cv2.contourArea(contour)
            # 过滤绿噪点面积
            if area < 100:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            # 根据逻辑要提取到最右边的那一个（绿方格组的末端格！）
            if x > max_x:
                max_x = x
                rightmost_rect = {'x': x, 'y': y, 'w': w, 'h': h}
                
        self._rightmost_rect = rightmost_rect

        # =======================================================
        # 8. 最后得出这几项我们 PID 核心所需计算的绝对位置与偏差数值。并打包进 Result 返回即可
        # =======================================================
        slider_center_y = None
        line_center_y = None
        
        if black_rect is not None:
            # 这里的 Y 全部都是以所切出 ROI 小框内的局部相对坐标！
            result.slider_top_y = black_rect['y']
            result.slider_bottom_y = black_rect['y'] + black_rect['h']
            slider_center_y = (result.slider_top_y + result.slider_bottom_y) // 2
            result.slider_center_y = slider_center_y
            
        if rightmost_rect is not None:
            line_center_y = rightmost_rect['y'] + rightmost_rect['h'] // 2
            result.line_center_y = line_center_y
            
        if slider_center_y is not None and line_center_y is not None:
            result.detected = True
            # 直线（绿靶子） 的位置 减去 我们跟随物体的中心。这正是将送至控制器的“误差变量 e(t)”！
            result.raw_deviation_y = line_center_y - slider_center_y
            # 注意：实际平滑交给调用这接口层的人去办，或者说在这也不必滤波了，原样把数据丢走给经理处理。
            result.deviation_y = result.raw_deviation_y 

        return result

    def draw_debug(self, frame: np.ndarray, result: VisionResult) -> np.ndarray:
        """
        在这里利用你保留的中间坐标和检测数据等状态来涂绘出直观视觉界面框框，极便于定位开发和诊断调整效果
        """
        debug_frame = frame.copy()
        x1, y1, x2, y2 = getattr(self, '_roi_coords', (0,0,0,0))
        
        # --- 重点一：ROI 定位框（绿色） ---
        cv2.rectangle(debug_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(debug_frame, "ROI Area", (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # --- 重点二：跟随滑块轮廓（红色粗框、上下中心辅助线（蓝色））---
        black_rect = getattr(self, '_black_rect', None)
        if black_rect is not None:
            x_g = black_rect['x'] + x1
            y_g = black_rect['y'] + y1
            w = black_rect['w']
            h = black_rect['h']
            cv2.rectangle(debug_frame, (x_g, y_g), (x_g + w, y_g + h), (0, 0, 255), 3)
            
            top = y1 + result.slider_top_y
            bottom = y1 + result.slider_bottom_y
            cv2.line(debug_frame, (x1, top), (x2, top), (255, 0, 0), 2)
            cv2.circle(debug_frame, (x1 + w//2, top), 3, (255, 0, 0), -1)
            cv2.line(debug_frame, (x1, bottom), (x2, bottom), (255, 0, 0), 2)
            cv2.circle(debug_frame, (x1 + w//2, bottom), 3, (255, 0, 0), -1)

        # --- 重点三：标靶（黄色线）与目标锚点（青偏黄粗框） ---
        rightmost = getattr(self, '_rightmost_rect', None)
        if rightmost is not None:
            x_g = rightmost['x'] + x1
            y_g = rightmost['y'] + y1
            w = rightmost['w']
            h = rightmost['h']
            cv2.rectangle(debug_frame, (x_g, y_g), (x_g + w, y_g + h), (255, 255, 0), 3)
            
        if result.line_center_y is not None:
            ly = y1 + result.line_center_y
            cv2.line(debug_frame, (x1, ly), (x2, ly), (0, 255, 255), 2)
            cv2.putText(debug_frame, f"Line Offset (Y): {result.line_center_y}", (x1 + 5, ly - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

        return debug_frame
