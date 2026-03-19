# Code/Vision/VisionProcessor/YoloProcessor.py
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

class YoloProcessor(BaseProcessor):
    """
    YOLO 深度学习图像算法类（策略）
    主要步骤：
      1. 裁剪感兴趣区域（ROI）这能提速和避免环境乱七八糟物体的干扰
      2. 将 ROI 图像输入给 YOLO 模型进行推理。
      3. 从 YOLO 检测结果中提取 'q' (黑色滑块) 和 'a' (绿色横线标靶)。
      4. 计算滑块中心和绿线中心！
      5. 在最后一步输出标准 VisionResult 给上面的“VisionManager”老板
    """
    def __init__(self):
        super().__init__()
        # 记录内部处理的一些过程数据（字典和格式），好提供给之后绘画调试框框
        self._roi_coords = (0, 0, 0, 0)
        self._black_rect = None       # 对于 YOLO 这是 'q' 的框
        self._rightmost_rect = None   # 对于 YOLO 这是 'a' 的框
        self.model = None
        self.class_names = []
        
        self.init_model()

    def init_model(self):
        print(f"\n[YoloProcessor] 正在加载模型: {Config.YOLO_MODEL_PATH}")
        try:
            from ultralytics import YOLO
        except ImportError:
            print("[错误] 未安装 ultralytics，请执行：pip install ultralytics")
            sys.exit(1)
            
        if not os.path.exists(Config.YOLO_MODEL_PATH):
            print(f"[错误] 模型文件不存在: {Config.YOLO_MODEL_PATH}")
            sys.exit(1)

        self.model = YOLO(Config.YOLO_MODEL_PATH)
        self.class_names = list(self.model.names.values())
        print(f"[YoloProcessor] 模型加载成功！类别: {self.class_names}")

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
        
        # 3. 使用 YOLO 进行推理 (在 ROI 上)
        # 确定推理设备
        device = getattr(Config, 'YOLO_DEVICE', "")
        if device == "":
            try:
                import torch
                device = "cuda:0" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        if self.model is None:
             return result

        results = self.model.predict(
            source    = roi_frame,
            imgsz     = getattr(Config, 'YOLO_IMG_SIZE', 512),
            conf      = getattr(Config, 'YOLO_CONF_THRESHOLD', 0.50),
            iou       = getattr(Config, 'YOLO_IOU_THRESHOLD', 0.45),
            device    = device,
            verbose   = False,
        )

        black_rect = None
        # 对于绿块 'a'，如果有多个，我们仍然找最右边的
        rightmost_rect = None
        max_x = -1
        
        if len(results) > 0 and results[0].boxes is not None and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            xyxy_boxes = boxes.xyxy.cpu().numpy().astype(int)
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            
            for (bx1, by1, bx2, by2), cls_id in zip(xyxy_boxes, cls_ids):
                class_name = self.class_names[cls_id] if cls_id < len(self.class_names) else str(cls_id)
                
                w = bx2 - bx1
                h = by2 - by1
                
                if class_name == 'q':
                    # 滑块 (相当于传统算法里的黑色块)
                    # 如果检测到多个 'q'，尽量选一个靠左侧或者直接记录这里我们简化处理如果只有一个
                    # 也可以加入面积过滤等
                    if black_rect is None:
                        black_rect = {'x': bx1, 'y': by1, 'w': w, 'h': h}
                    else:
                        # 如有多个取更偏左的（参考传统算法）
                        if bx1 < black_rect['x']:
                            black_rect = {'x': bx1, 'y': by1, 'w': w, 'h': h}
                            
                elif class_name == 'a':
                    # 绿靶块
                    # 同样取最靠右侧的
                    if bx1 > max_x:
                        max_x = bx1
                        rightmost_rect = {'x': bx1, 'y': by1, 'w': w, 'h': h}
                        
        self._black_rect = black_rect 
        self._rightmost_rect = rightmost_rect

        # =======================================================
        # 4. 计算处理结果并打包
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
