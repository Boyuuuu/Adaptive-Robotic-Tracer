# DebugServer.py - 灵活的视觉调试服务器
from flask import Flask, Response, render_template_string, jsonify
import cv2
import numpy as np
import threading
import time
from collections import defaultdict
import base64

class DebugServer:
    """
    灵活的调试服务器 - 支持动态添加图像流和性能指标
    
    使用方法:
        # 1. 创建服务器
        debug_server = DebugServer(port=5000)
        debug_server.start()
        
        # 2. 在你的代码中推送图像
        debug_server.push_image("原图", frame)
        debug_server.push_image("ROI", roi_frame)
        debug_server.push_image("HSV", hsv)
        debug_server.push_image("Mask", mask)
        
        # 3. 推送性能指标
        debug_server.push_metric("FPS", 30.5)
        debug_server.push_metric("处理延迟(ms)", 15.2)
        debug_server.push_metric("偏差(mm)", error_mm)
    """
    
    def __init__(self, port=5000):
        self.app = Flask(__name__)
        self.port = port
        
        # 存储图像流 {流名称: 最新图像}
        self.image_streams = {}
        self.stream_lock = threading.Lock()
        
        # 存储性能指标 {指标名: 值}
        self.metrics = {}
        self.metrics_lock = threading.Lock()
        
        # 设置路由
        self._setup_routes()
        
        # 服务器线程
        self.server_thread = None
        
    def _setup_routes(self):
        """设置 Flask 路由"""
        
        @self.app.route('/')
        def index():
            """主页面 - 动态生成所有图像流"""
            return render_template_string(HTML_TEMPLATE)
        
        @self.app.route('/streams')
        def get_streams():
            """获取所有可用的图像流名称"""
            with self.stream_lock:
                return jsonify(list(self.image_streams.keys()))
        
        @self.app.route('/video_feed/<stream_name>')
        def video_feed(stream_name):
            """MJPEG 视频流"""
            return Response(
                self._generate_frames(stream_name),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )
        
        @self.app.route('/metrics')
        def get_metrics():
            """获取所有性能指标"""
            with self.metrics_lock:
                return jsonify(self.metrics)
    
    def _generate_frames(self, stream_name):
        """生成 MJPEG 帧"""
        while True:
            with self.stream_lock:
                if stream_name in self.image_streams:
                    frame = self.image_streams[stream_name]
                    
                    # 编码为 JPEG
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            time.sleep(0.03)  # ~30 FPS
    
    def push_image(self, stream_name, image):
        """
        推送图像到指定流
        
        Args:
            stream_name: 流名称，如 "原图", "ROI", "HSV", "Mask"
            image: OpenCV 图像 (numpy array)
        """
        if image is None or image.size == 0:
            return
        
        # 如果是单通道图像（灰度图/mask），转换为3通道
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        with self.stream_lock:
            self.image_streams[stream_name] = image.copy()
    
    def push_metric(self, metric_name, value):
        """
        推送性能指标
        
        Args:
            metric_name: 指标名称，如 "FPS", "处理延迟(ms)"
            value: 指标值（数字）
        """
        with self.metrics_lock:
            self.metrics[metric_name] = round(value, 2)
    
    def start(self):
        """启动服务器（在后台线程）"""
        if self.server_thread is not None:
            print("[DebugServer] 服务器已在运行")
            return
        
        self.server_thread = threading.Thread(
            target=self._run_server,
            daemon=True
        )
        self.server_thread.start()
        print(f"[DebugServer] 调试服务器已启动: http://localhost:{self.port}")
    
    def _run_server(self):
        """运行 Flask 服务器"""
        self.app.run(host='0.0.0.0', port=self.port, debug=False, threaded=True)


# HTML 模板 - 动态生成图像流网格
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>视觉调试面板</title>
    <meta charset="utf-8">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .metrics-panel {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        }
        
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            transition: transform 0.2s;
        }
        
        .metric-card:hover {
            transform: translateY(-5px);
        }
        
        .metric-name {
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 5px;
        }
        
        .metric-value {
            font-size: 1.8em;
            font-weight: bold;
        }
        
        .streams-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }
        
        .stream-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);
            transition: transform 0.3s;
        }
        
        .stream-card:hover {
            transform: scale(1.02);
        }
        
        .stream-title {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            font-size: 1.2em;
            font-weight: bold;
            text-align: center;
        }
        
        .stream-image {
            width: 100%;
            height: auto;
            display: block;
            background: #000;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: white;
            font-size: 1.2em;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 视觉调试面板</h1>
        
        <!-- 性能指标面板 -->
        <div class="metrics-panel">
            <h2 style="margin-bottom: 15px; color: #667eea;">📊 性能指标</h2>
            <div id="metrics-grid" class="metrics-grid">
                <div class="loading">正在加载指标...</div>
            </div>
        </div>
        
        <!-- 图像流网格 -->
        <div id="streams-grid" class="streams-grid">
            <div class="loading">正在加载图像流...</div>
        </div>
    </div>
    
    <script>
        // 动态加载图像流
        function loadStreams() {
            fetch('/streams')
                .then(response => response.json())
                .then(streams => {
                    const grid = document.getElementById('streams-grid');
                    
                    if (streams.length === 0) {
                        grid.innerHTML = '<div class="loading">暂无图像流</div>';
                        return;
                    }
                    
                    grid.innerHTML = '';
                    streams.forEach(streamName => {
                        const card = document.createElement('div');
                        card.className = 'stream-card';
                        card.innerHTML = `
                            <div class="stream-title">${streamName}</div>
                            <img class="stream-image" src="/video_feed/${encodeURIComponent(streamName)}" alt="${streamName}">
                        `;
                        grid.appendChild(card);
                    });
                });
        }
        
        // 动态加载性能指标
        function loadMetrics() {
            fetch('/metrics')
                .then(response => response.json())
                .then(metrics => {
                    const grid = document.getElementById('metrics-grid');
                    
                    const keys = Object.keys(metrics);
                    if (keys.length === 0) {
                        grid.innerHTML = '<div class="loading">暂无性能指标</div>';
                        return;
                    }
                    
                    grid.innerHTML = '';
                    keys.forEach(metricName => {
                        const card = document.createElement('div');
                        card.className = 'metric-card';
                        card.innerHTML = `
                            <div class="metric-name">${metricName}</div>
                            <div class="metric-value">${metrics[metricName]}</div>
                        `;
                        grid.appendChild(card);
                    });
                });
        }
        
        // 初始加载
        loadStreams();
        loadMetrics();
        
        // 定期刷新流列表（检测新增的流）
        setInterval(loadStreams, 3000);
        
        // 定期刷新指标
        setInterval(loadMetrics, 500);
    </script>
</body>
</html>
'''
