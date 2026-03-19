# Code/Vision/Camera.py
import cv2
import threading
import time

class ThreadedCamera:
    """
    多线程摄像头获取类 (Threaded Capture)
    特性：
    1. 多线程读取：能够独立在一个后台线程不断读取摄像头，缓存最新一帧。
       无论上层识别算法耗时多长（哪怕20ms+），都能保证拿到此时此刻最“新鲜”的图像。
    2. 健壮性：具有自动防掉线和重连处理。
    3. 配置解耦：不用知道上层业务，配置仅为基本相机参数。
    """
    def __init__(self, cam_index=0, width=640, height=480, fps=60):
        # 1. 保存配置，做到对外面业务脱敏
        self.cam_index = cam_index
        self.width = width
        self.height = height
        self.fps = fps
        
        self.cap = None
        self.latest_frame = None
        self.running = False
        self._lock = threading.Lock()
        
        # 2. 开机立刻初始化摄像头
        self._connect()
        
        # 3. 启动后台抓图精灵（daemon线程）
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _connect(self):
        """内部方法：打开设备并应用配置分辨率"""
        if self.cap is not None:
            self.cap.release()
            
        self.cap = cv2.VideoCapture(self.cam_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        
        with self._lock:
            # 抢跑测速，确认下是不是好的
            ret, frame = self.cap.read()
            if ret:
                self.latest_frame = frame
                print(f"[Camera] 摄像头 {self.cam_index} 连接成功！")
            else:
                self.latest_frame = None
                print(f"[Camera] 无法读取摄像头 {self.cam_index}，请确认连接。")

    def _capture_loop(self):
        """抓图无限循环 (多线程运行)"""
        while self.running:
            # 掉线重连保护机制
            if self.cap is None or not self.cap.isOpened():
                print("[Camera] 检测到摄像头离线，正在尝试重新连接 ...")
                self._connect()
                time.sleep(1) # 不要狂刷，重连失败就等1秒再连
                continue
                
            ret, frame = self.cap.read()
            if ret:
                # 关键：这里直接盖掉老的数据，不搞 Queue，以此解决图像积压问题
                with self._lock:
                    self.latest_frame = frame
            else:
                print("[Camera] 摄像头画面断流或异常读取，将尝试重启 ...")
                with self._lock:
                    self.latest_frame = None
                self.cap.release()
                self.cap = None

    def get_frame(self):
        """
        状态查询接口 API: 获取最新一帧图像 (线程安全)。被 VisionManager 或外界调用。
        
        Returns:
            (是否成功读取: bool, 图像副本: np.ndarray)
        """
        with self._lock:
            if self.latest_frame is not None:
                # 必须 .copy() 复制出来
                # 不然你在画框涂涂改改，原数据也会被污染
                return True, self.latest_frame.copy()
            else:
                return False, None

    def is_ready(self) -> bool:
        """状态查询接口 API: 查看当前摄像头是否顺利在吐正确的图片"""
        with self._lock:
            return self.latest_frame is not None

    def stop(self):
        """状态查询接口 API: 安全结束线程并释放句柄"""
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap is not None:
            self.cap.release()
            print("[Camera] 摄像头已被安全关闭和释放。")
