# Vision.py
import threading
import cv2
import numpy as np
import time
import queue
import os
from datetime import datetime
from AppConfig import Config
from DebugServer import DebugServer

class VisionThread(threading.Thread):
    def __init__(self, data_queue, enable_debug=True, enable_debug_web=False):
        super().__init__()
        self.data_queue = data_queue  # 接收共享的“传送带”
        self.running = True           # 线程开关
        
        # 调试服务器
        self.debug_server = DebugServer(port=5000) if enable_debug_web else None
        self.enable_debug = enable_debug
        if self.debug_server:
            self.debug_server.start()
        
        # 性能监控
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.current_fps = 0.0
        
        # 初始化摄像头
        self.cap = cv2.VideoCapture(Config.CAM_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, 60)  # 尝试设置摄像头为 60 FPS
        
        # 读取实际的摄像头 FPS（用于调试）
        actual_cam_fps = self.cap.get(cv2.CAP_PROP_FPS)
        print(f"[Vision] 摄像头实际 FPS: {actual_cam_fps}")

        # deviation_y 滤波状态
        self._filtered_deviation: float | None = None  # EMA 的上一帧输出

        # 图片保存路径（相对于 Code 目录的 save 文件夹）
        self._save_dir = os.path.join(os.path.dirname(__file__), '..', 'save')
        os.makedirs(self._save_dir, exist_ok=True)
        self._save_count = 0

    def run(self):
        print("[Vision] 视觉线程启动...")
        
        while self.running:
            loop_start = time.time()  # 记录循环开始时间
            
            # --- 步骤 1: 摄像头采集 ---
            ret, frame = self.cap.read()
            if not ret:
                print("[Vision] 无法读取摄像头画面")
                time.sleep(1)
                continue
            
            # --- 步骤 2: ROI裁剪 ---
            # 1. 从配置获取坐标 (x1, y1, x2, y2)
            x1, y1, x2, y2 = Config.ROI_COORDS
            
            # 确保坐标不越界 (防止程序崩溃)
            height, width = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(width, x2), min(height, y2)

            # 2. 在原图 frame 上画出这个区域 (绿色矩形框，线宽2)
            # 这一步是为了让你调试时能在屏幕上看到机器"关注"的区域
            frame_with_roi = frame.copy()
            cv2.rectangle(frame_with_roi, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # 3. 核心步骤：裁剪出感兴趣区域
            # 注意：NumPy 切片的顺序是 [y1:y2, x1:x2] (先高后宽)
            roi_frame = frame[y1:y2, x1:x2]


            # --- 步骤 2: 预处理 (降噪 & 转换) ---
            # 高斯模糊去除噪点
            blurred = cv2.GaussianBlur(roi_frame, (3, 3), 0)
            # 转换到 HSV 颜色空间 (为了适应光照)
            hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

            # --- 步骤 3: 特征提取 (颜色过滤) ---
            # 根据 AppConfig 里的范围提取掩码（原有颜色，如黄色）
            mask = cv2.inRange(hsv, Config.HSV_LOWER, Config.HSV_UPPER)
            
            # --- 步骤 3.5: 黑色框检测 ---
            # 黑色的 HSV 范围：H 任意，S 低，V 低
            black_lower = np.array([0, 0, 0])      # H, S, V 的最小值
            black_upper = np.array([180, 255, 50]) # H 任意，S 任意，V < 50（暗）
            mask_black = cv2.inRange(hsv, black_lower, black_upper)
            
            # 对黑色 mask 进行形态学运算
            kernel_black = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            mask_black_opened = cv2.morphologyEx(mask_black, cv2.MORPH_OPEN, kernel_black, iterations=2)
            mask_black_closed = cv2.morphologyEx(mask_black_opened, cv2.MORPH_CLOSE, kernel_black, iterations=2)
            
            # 检测黑色轮廓
            contours_black, _ = cv2.findContours(mask_black_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 找到面积在 [500, 1000] 之间且最靠近 ROI 左侧（x 最小）的黑色矩形
            black_rect = None
            min_x = float('inf')

            for contour in contours_black:
                area = cv2.contourArea(contour)
                if area < Config.SLIDER_AREA_MIN or area > Config.SLIDER_AREA_MAX:
                    continue

                x, y, w, h = cv2.boundingRect(contour)
                if x < min_x:                   # 取最靠近 ROI 左侧的
                    min_x = x
                    black_rect = {
                        'x': x, 'y': y, 'w': w, 'h': h,
                        'area': area,
                        'aspect_ratio': w / h if h > 0 else 0,
                        'contour': contour
                    }
            
            # --- 步骤 4: 形态学运算（开闭运算）---
            # 定义结构元素（卷积核）
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            
            # 开运算：先腐蚀后膨胀，去除小噪点
            # 作用：消除小的白色噪点，断开细小的连接
            mask_opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
            
            # 闭运算：先膨胀后腐蚀，填充小孔洞
            # 作用：填充物体内部的小黑洞，连接邻近的物体
            mask_closed = cv2.morphologyEx(mask_opened, cv2.MORPH_CLOSE, kernel, iterations=2)
            
            # --- 步骤 5: 轮廓检测 ---
            # 找到所有轮廓
            contours, hierarchy = cv2.findContours(mask_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 使用原图作为绘制结果（而不是 ROI）
            result_image = frame.copy()
            
            # 在原图上画出 ROI 区域框（绿色虚线）
            cv2.rectangle(result_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(result_image, "ROI", (x1 + 5, y1 + 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # 存储检测到的矩形框
            rectangles = []
            
            # 遍历所有轮廓
            for contour in contours:
                # 计算轮廓面积，过滤太小的轮廓（噪点）
                area = cv2.contourArea(contour)
                if area < 100:  # 面积阈值，可以根据实际情况调整
                    continue
                
                # 获取外接矩形（ROI 坐标系）
                x, y, w, h = cv2.boundingRect(contour)
                
                # 存储矩形信息（ROI 坐标系，用于后续计算）
                rectangles.append({
                    'x': x, 'y': y, 'w': w, 'h': h,
                    'area': area,
                    'aspect_ratio': w / h if h > 0 else 0,  # 宽高比
                    'contour': contour
                })

            # 打印检测到的矩形数量（调试用）
            if Config.VISION_VERBOSE and len(rectangles) > 0:
                print(f"[Vision] 检测到 {len(rectangles)} 个矩形框")
            
            # 绘制黑色框（用红色标记）
            if black_rect is not None:
                # ROI 坐标系
                x, y, w, h = black_rect['x'], black_rect['y'], black_rect['w'], black_rect['h']
                
                # 转换到原图坐标系
                x_global = x + x1
                y_global = y + y1
                
                # 在原图上绘制
                cv2.rectangle(result_image, (x_global, y_global), (x_global + w, y_global + h), (0, 0, 255), 3)
                cv2.putText(result_image, f"BLACK: {int(black_rect['area'])}", (x_global, y_global - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                if Config.VISION_VERBOSE:
                    print(f"[Vision] 检测到黑色框: 位置({x},{y}), 大小({w}x{h}), 面积={black_rect['area']:.0f}")
            
            # --- 步骤 6: 计算关键点数据 ---
            slider_top_y = None      # 滑块上位置（ROI 坐标系）
            slider_bottom_y = None   # 滑块下位置（ROI 坐标系）
            line_center_y = None     # 直线投影位置（ROI 坐标系）
            
            # 1. 计算黑色矩形的上下顶点 Y 坐标（ROI 坐标系）
            if black_rect is not None:
                slider_top_y = black_rect['y']                    # 上顶点 Y
                slider_bottom_y = black_rect['y'] + black_rect['h']  # 下顶点 Y
                
                # 转换到原图坐标系进行绘制
                slider_top_y_global = slider_top_y + y1
                slider_bottom_y_global = slider_bottom_y + y1
                
                # 在原图上标注滑块上下位置
                # 上顶点：画一条蓝色横线（只在 ROI 区域内）
                cv2.line(result_image, (x1, slider_top_y_global), (x2, slider_top_y_global), 
                        (255, 0, 0), 2)  # 蓝色
                cv2.putText(result_image, f"Slider Top: {slider_top_y}", (x1 + 5, slider_top_y_global - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                
                # 下顶点：画一条蓝色横线（只在 ROI 区域内）
                cv2.line(result_image, (x1, slider_bottom_y_global), (x2, slider_bottom_y_global), 
                        (255, 0, 0), 2)  # 蓝色
                cv2.putText(result_image, f"Slider Bottom: {slider_bottom_y}", (x1 + 5, slider_bottom_y_global + 15), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            
            # 2. 找到最右侧的绿色矩形框（ROI 坐标系）
            rightmost_rect = None
            max_x = -1
            
            for rect in rectangles:
                # 找到 x 坐标最大的矩形（最右侧）
                if rect['x'] > max_x:
                    max_x = rect['x']
                    rightmost_rect = rect
            
            # 3. 计算最右侧矩形的中心点 Y 坐标（ROI 坐标系）
            if rightmost_rect is not None:
                # ROI 坐标系
                center_x = rightmost_rect['x'] + rightmost_rect['w'] // 2
                center_y = rightmost_rect['y'] + rightmost_rect['h'] // 2
                line_center_y = center_y
                
                # 转换到原图坐标系
                center_x_global = center_x + x1
                center_y_global = center_y + y1
                line_center_y_global = center_y_global
                
                # 在原图上标注直线投影位置
                # 画一条黄色横线表示直线的模拟投影（只在 ROI 区域内）
                cv2.line(result_image, (x1, line_center_y_global), (x2, line_center_y_global), 
                        (0, 255, 255), 2)  # 黄色
                cv2.putText(result_image, f"Line Center: {line_center_y}", (x1 + 5, line_center_y_global - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                
                # 在最右侧矩形上画一个圆点标记中心（原图坐标）
                cv2.circle(result_image, (center_x_global, center_y_global), 5, (255, 255, 0), -1)  # 青色圆点
                
                # 在最右侧矩形框上加粗标记（区别于其他绿色框）
                x, y, w, h = rightmost_rect['x'], rightmost_rect['y'], rightmost_rect['w'], rightmost_rect['h']
                x_global = x + x1
                y_global = y + y1
                cv2.rectangle(result_image, (x_global, y_global), (x_global + w, y_global + h), (255, 255, 0), 3)  # 青色，粗线
            
            if Config.VISION_VERBOSE:
                if slider_top_y is not None and slider_bottom_y is not None:
                    print(f"[Vision] 滑块位置(ROI): 上={slider_top_y}, 下={slider_bottom_y}")

                if line_center_y is not None:
                    print(f"[Vision] 直线投影位置(ROI): Y={line_center_y}")
            
            # 5. 计算偏差（如果两者都存在，ROI 坐标系）
            deviation_y = None  # 初始化偏差变量
            slider_center_y = None  # 初始化滑块中心变量
            
            if slider_top_y is not None and slider_bottom_y is not None:
                # 计算滑块中心
                slider_center_y = (slider_top_y + slider_bottom_y) // 2
                
                if line_center_y is not None:
                    # 计算直线中心与滑块中心的偏差
                    deviation_y = line_center_y - slider_center_y
                    
                    if Config.VISION_VERBOSE:
                        print(f"[Vision] Y轴偏差(ROI): {deviation_y} 像素 (直线中心 - 滑块中心)")

            # --- deviation_y 两层滤波（限幅 + EMA）---
            raw_deviation_y = deviation_y   # 保留原始值用于调试
            if deviation_y is not None:
                raw = float(deviation_y)

                # 层一：跳跃限幅 —— 单帧变化超过阈值则截断
                if self._filtered_deviation is not None:
                    delta = raw - self._filtered_deviation
                    max_jump = Config.VISION_MAX_JUMP_PX
                    if abs(delta) > max_jump:
                        raw = self._filtered_deviation + max_jump * (1 if delta > 0 else -1)

                # 层二：EMA 低通滤波
                alpha = Config.VISION_EMA_ALPHA
                if self._filtered_deviation is None:
                    self._filtered_deviation = raw      # 首帧直接初始化
                else:
                    self._filtered_deviation = alpha * raw + (1 - alpha) * self._filtered_deviation

                deviation_y = round(self._filtered_deviation)

            # 在原图上显示偏差（原始值 + 滤波值）
            if raw_deviation_y is not None:
                cv2.putText(result_image, f"Dev raw:{raw_deviation_y} filt:{deviation_y} px", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # --- 步骤 7: 数据传递到控制线程 ---
            # 准备数据包
            if slider_top_y is not None and slider_bottom_y is not None:
                # 检测到滑块
                vision_data = {
                    'slider_center_y': slider_center_y,
                    'slider_top_y':    slider_top_y,
                    'slider_bottom_y': slider_bottom_y,
                    'line_center_y':   line_center_y if line_center_y is not None else None,
                    'deviation_y':     deviation_y   if deviation_y   is not None else None,
                    'raw_deviation_y': raw_deviation_y,   # 原始值（调试用）
                    'timestamp': time.time(),
                    'detected': True
                }
            else:
                # 未检测到滑块
                vision_data = {
                    'detected': False,
                    'timestamp': time.time()
                }
            
            # 放入队列（非阻塞）
            try:
                self.data_queue.put_nowait(vision_data)
            except queue.Full:
                # 队列满时丢弃旧数据，放入新数据
                try:
                    self.data_queue.get_nowait()  # 取出旧数据
                    self.data_queue.put_nowait(vision_data)  # 放入新数据
                except:
                    pass  # 如果出错就跳过

            # 计算性能指标
            loop_end = time.time()
            loop_time = (loop_end - loop_start) * 1000  # 毫秒
                
            # 计算 FPS（每秒更新一次）
            self.fps_counter += 1
            current_time = time.time()
            elapsed_time = current_time - self.fps_start_time
                
            if elapsed_time >= 1.0:
                self.current_fps = self.fps_counter / elapsed_time
                self.fps_counter = 0
                self.fps_start_time = current_time

            # --- 推送到调试服务器 ---
            if self.debug_server:
                # 推送所有中间图像（这里演示如何灵活添加）
                self.debug_server.push_image("1-原图", frame)
                
                # 推送性能指标（这里演示如何灵活添加）
                self.debug_server.push_metric("FPS", self.current_fps)
                self.debug_server.push_metric("循环耗时(ms)", loop_time)
                self.debug_server.push_metric("理论最大FPS", 1000.0 / loop_time if loop_time > 0 else 0)

          

            # 在图像上显示 FPS 和性能信息
            if self.enable_debug:
                # 创建半透明背景（右上角）
                overlay = result_image.copy()
                bg_x1, bg_y1 = result_image.shape[1] - 260, 5  # 右上角
                bg_x2, bg_y2 = result_image.shape[1] - 5, 100
                cv2.rectangle(overlay, (bg_x1, bg_y1), (bg_x2, bg_y2), (0, 0, 0), -1)
                cv2.addWeighted(overlay, 0.6, result_image, 0.4, 0, result_image)
                
                # 显示 FPS（大字体，绿色）
                cv2.putText(result_image, f"FPS: {self.current_fps:.1f}", (bg_x1 + 5, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                
                # 显示循环耗时（小字体，白色）
                cv2.putText(result_image, f"Loop: {loop_time:.1f}ms", (bg_x1 + 5, 55), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # 显示理论最大 FPS（小字体，黄色）
                max_fps = 1000.0 / loop_time if loop_time > 0 else 0
                cv2.putText(result_image, f"Max: {max_fps:.1f} FPS", (bg_x1 + 5, 80), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            
            # --- 标定模式：绘制参考横线 ---
            # 仅在 CONTROL_MODE == 'Motor_Motion_Calibration' 时绘制，用于人工标定像素坐标
            if True:
                img_width = result_image.shape[1]
                calib_color = (0, 165, 255)   # 亮橙色，醒目且不与其他标注冲突

                # 第一条横线：Y1
                cv2.line(result_image, (0, Config.CALIBRATION_Y1),
                         (img_width, Config.CALIBRATION_Y1), calib_color, 2)
                cv2.putText(result_image, f"CAL Y1={Config.CALIBRATION_Y1}px",
                            (5, Config.CALIBRATION_Y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, calib_color, 2)

                # 第二条横线：Y2
                cv2.line(result_image, (0, Config.CALIBRATION_Y2),
                         (img_width, Config.CALIBRATION_Y2), calib_color, 2)
                cv2.putText(result_image, f"CAL Y2={Config.CALIBRATION_Y2}px",
                            (5, Config.CALIBRATION_Y2 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, calib_color, 2)

            # 显示 OpenCV 窗口
            cv2.namedWindow("Vision Debug", cv2.WINDOW_AUTOSIZE)
            cv2.resizeWindow("Vision Debug", 1280, 720)
            cv2.imshow("Vision Debug", result_image)  # 显示带矩形框的结果图像
            
            # 按键处理
            key = cv2.waitKey(1) & 0xFF

            # 按 'q' 键退出
            if key == ord('q'):
                self.running = False

            # 按 's' 键保存原始图片（无任何HSV/预处理，仅原始摄像头帧）
            elif key == ord('s'):
                self._save_count += 1
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # 精确到毫秒
                filename = f"frame_{timestamp}_{self._save_count:04d}.png"
                save_path = os.path.join(self._save_dir, filename)
                cv2.imwrite(save_path, frame)
                print(f"[Vision] 原始图片已保存: {save_path}")

        self.cap.release()
        cv2.destroyAllWindows()