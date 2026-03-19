# Code/Root/VisionManager.py
import threading
import time
import queue
import cv2
import os
import sys
from datetime import datetime

# 自动处理包引用路径
_code_dir = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.abspath(_code_dir))

from AppConfig import Config
from DebugServer import DebugServer
# 从刚建立的新模块导入工具与组件！
from Vision.Camera import ThreadedCamera
from Vision.Utils.Filters import EMAFilter
from Vision.VisionProcessor.TraditionalProcessor import TraditionalProcessor
from Vision.VisionProcessor.YoloProcessor import YoloProcessor

# ══════════════════════════════════════════════════════════════════
#  视觉处理器工厂 / 注册表
#  这就和 ControllerManager 一样：方便后续无痛加入如 YOLO 处理类
# ══════════════════════════════════════════════════════════════════
VISION_REGISTRY = {
    'traditional': TraditionalProcessor,
    'yolo': YoloProcessor, # AI YOLO 算子！
}

class VisionManager(threading.Thread):
    """
    负责整套视觉系统“流水线”运转的老大！
    他从不管下属摄像头是如何防线掉帧，也从不去理会算法是HSV还是YOLO，他只管大局：
      1. 开线程启动摄像头
      2. 去读取图像传递给所选中的下属（处理器/Strategy）进行打螺丝
      3. 把处理结果拿去滤掉毛刺防止手抖
      4. 然后安全把东西丢给上级“控制器”(放入消息队列提供数据)。
    """
    def __init__(self, data_queue, enable_debug=True, enable_debug_web=False):
        super().__init__()
        self.data_queue = data_queue
        self.running = True
        self.enable_debug = enable_debug
        
        # 0. 【Web可视化看板开机】
        self.debug_server = DebugServer(port=5000) if enable_debug_web else None
        if self.debug_server:
            self.debug_server.start()

        # 1. 【摄像模块】调用独立的线程相机，不掉帧卡死
        self.camera = ThreadedCamera(
            cam_index=Config.CAM_INDEX,
            width=Config.FRAME_WIDTH,
            height=Config.FRAME_HEIGHT,
            fps=60 # 摄像头试图跑的最高帧数
        )

        # 2. 【核心大脑】 根据配置（或默认）加载注册表里的底层视觉计算器！
        mode = getattr(Config, 'VISION_MODE', 'traditional') # 假如用户暂时还没配置VISION_MODE，默认传统色块识别
        if mode not in VISION_REGISTRY:
            print(f"[VisionManager] Warning: 未知的视觉模式 {mode}，将降级使用 traditional")
            mode = 'traditional'
            
        print(f"[VisionManager] === 核心视觉引擎挂载完毕 === 模式:【{mode}】")
        self.processor = VISION_REGISTRY[mode]()

        # 3. 【工具手】数据滤波平滑清理工具：EMA
        self.ema_filter = EMAFilter(alpha=Config.VISION_EMA_ALPHA, max_jump=Config.VISION_MAX_JUMP_PX)

        # 4. 【系统计数】
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.current_fps = 0.0

        # 照片留底路径
        self._save_dir = os.path.join(os.path.dirname(__file__), '..', 'save')
        os.makedirs(self._save_dir, exist_ok=True)
        self._save_count = 0

    def run(self):
        print("[VisionManager] ---> 视觉主循环后台服务启动中...")
        
        # 为了稳定，等待相机完全准备并预热好再进行正式工作
        while self.running and not self.camera.is_ready():
            time.sleep(0.1)
            
        while self.running:
            loop_start = time.time()
            
            # --- 【流水线环节 1】 : 相机捕获最新一帧图像 ---
            ret, frame = self.camera.get_frame()
            if not ret or frame is None:
                continue

            # --- 【流水线环节 2】 : 给黑盒打工仔干活(核心推理) ---
            # 它有可能是 HSV 算子，也可能是 Yolo v11 处理。不论那种，他们遵守规定产出的格式都是统一的 Result 结构。
            result = self.processor.process(frame)

            # --- 【流水线环节 3】 : 进行数据统一修饰处理（滤波等） ---
            final_dev_y = None
            if result.detected and result.raw_deviation_y is not None:
                # 给原始数据上一层滤镜：截断防跳跃以及平通滤波，防止电机乱轴！
                final_dev_y = self.ema_filter.update(result.raw_deviation_y)
                result.deviation_y = final_dev_y 
            else:
                self.ema_filter.reset() # 丢失了目标，所以清空它的滑动记忆！

            # --- 【流水线环节 4】 : 与机器人电机总管(ControllerManager)交接班 ---
            # 格式依然保持从前，不破坏业务层任何一处结构代码：
            vision_data = {
                'detected': result.detected,
                'slider_center_y': getattr(result, 'slider_center_y', None),
                'slider_top_y': getattr(result, 'slider_top_y', None),
                'slider_bottom_y': getattr(result, 'slider_bottom_y', None),
                'line_center_y': getattr(result, 'line_center_y', None),
                'deviation_y': result.deviation_y,
                'raw_deviation_y': result.raw_deviation_y,
                'timestamp': result.timestamp
            }
            
            # 推入共享传送带消息队列！采取挤掉旧帧留新帧的原则！
            try:
                self.data_queue.put_nowait(vision_data)
            except queue.Full:
                try:
                    self.data_queue.get_nowait()
                    self.data_queue.put_nowait(vision_data)
                except:
                    pass

            # --- 【流水线环节 5】 : 统计当前计算算力耗时！ ---
            loop_time = (time.time() - loop_start) * 1000
            self.fps_counter += 1
            if time.time() - self.fps_start_time >= 1.0:
                self.current_fps = self.fps_counter / (time.time() - self.fps_start_time)
                self.fps_counter = 0
                self.fps_start_time = time.time()

            # --- 【流水线环节 6】 : 根据需要渲染调试大屏监控UI ---
            if self.enable_debug:
                # 调取基底自己独有的绘画风格，比如画它的红色绿色标注或者YOLO的矩形分类框标枪！
                debug_frame = self.processor.draw_debug(frame, result)
                # 然后在这基础上加盖统一的UI，诸如实时帧率水印或者公用辅助死区线
                self._draw_overlay(debug_frame, loop_time, final_dev_y, result.raw_deviation_y)

                # 将组装好的图显示至屏幕上！
                cv2.imshow("Vision Dashboard - Modular Engine", debug_frame)
                
                # 读取我们键盘操作
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self.running = False
                elif key == ord('s'):
                    self._save_raw_image(frame)

            # --- 【流水线环节 7】 : 服务端上传 (监控) ---
            if self.debug_server:
                self.debug_server.push_image("1-摄像头裸源图", frame)
                if self.enable_debug:
                    self.debug_server.push_image("2-视觉复合数据解析视图", debug_frame)
                self.debug_server.push_metric("System_FPS", self.current_fps)

        # 打烊关机清理释放资源
        self.camera.stop()
        cv2.destroyAllWindows()
        print("[VisionManager] 👋视觉引擎已正常离线挂起。")

    def _draw_overlay(self, image, loop_time, dev_y, raw_dev_y):
        """通用层数据刻画展示与UI绘制服务函数"""
        # 左上方的结果信息：原始结果 vs 被过滤好的数据
        if raw_dev_y is not None and dev_y is not None:
            cv2.putText(image, f"Offset raw:{raw_dev_y} filt:{dev_y}px", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                        
        # 右上方的硬件负载统计面板：大字体、高可见
        bg_x1, bg_y1 = image.shape[1] - 260, 5
        cv2.putText(image, f"Current FPS: {self.current_fps:.1f}", (bg_x1 + 5, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(image, f"Process Loop: {loop_time:.1f} ms", (bg_x1 + 5, 55), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # 因为运动可能涉及标定死区阈界，画两横参考辅助标量线协助人眼调控！
        img_width = image.shape[1]
        calib_color = (0, 165, 255)
        cv2.line(image, (0, Config.CALIBRATION_Y1), (img_width, Config.CALIBRATION_Y1), calib_color, 2)
        cv2.line(image, (0, Config.CALIBRATION_Y2), (img_width, Config.CALIBRATION_Y2), calib_color, 2)

    def _save_raw_image(self, frame):
        """一键给当下源头帧截图快门（原始图片用以收集用以训练自己的 YOLO 数据集材料！）"""
        self._save_count += 1
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        filename = f"dataset_img_{ts}_{self._save_count:04d}.png"
        full_path = os.path.join(self._save_dir, filename)
        cv2.imwrite(full_path, frame)
        print(f"📸 快门！一张没有任何加工的高清摄像头原素材入库至: {filename}")
