# Controller.py
import threading
import serial
import time
import queue
from AppConfig import Config

class ControlThread(threading.Thread):
    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self.running = True
        self.ser = None

        # 连接 DLC32 主板
        try:
            self.ser = serial.Serial(Config.SERIAL_PORT, Config.BAUD_RATE, timeout=0.1)
            print(f"[Controller] 成功连接到 {Config.SERIAL_PORT}")
            time.sleep(2) # 等待 ESP32 重启
            
            # 初始化：相对坐标模式(G91)，毫米单位(G21)
            self.ser.write(b"G21 G91\n")
            
        except Exception as e:
            print(f"[Controller] 串口连接失败: {e}")
            self.running = False

    def run(self):
        print("[Control] 控制线程启动...")
        print("[Control] 使用简单增量控制模式（无需标定）")
        
        while self.running:
            try:
                # 从队列读取视觉数据（超时1秒）
                vision_data = self.data_queue.get(timeout=1.0)
                
                if vision_data['detected']:
                    # 获取偏差数据
                    deviation_y = vision_data.get('deviation_y')
                    
                    if deviation_y is not None:
                        # ========== 简单增量控制逻辑 ==========
                        # 死区：偏差小于25像素时不动作
                        if abs(deviation_y) <= 25:
                            # print("[Control] 在死区内，不移动")
                            continue
                        
                        # 根据偏差方向决定移动方向（已反转）
                        # deviation_y > 0: 直线在滑块上方，需要向下移动（负方向）
                        # deviation_y < 0: 直线在滑块下方，需要向上移动（正方向）
                        if deviation_y > 25:
                            # 向下移动固定距离
                            move_distance = -Config.STEP_DISTANCE  # 负数
                            direction = "下"
                        else:  # deviation_y < -25
                            # 向上移动固定距离
                            move_distance = Config.STEP_DISTANCE  # 正数
                            direction = "上"
                        
                        # 执行移动
                        success = self.move_motor(move_distance)
                        
                        if success:
                            print(f"[Control] 偏差={deviation_y:+.0f}px → 向{direction}移动 {abs(move_distance):.1f}mm")
                        
                        # 控制频率（避免发送太快）
                        time.sleep(Config.CONTROL_FREQ)
                        # ======================================
                    else:
                        # 检测到滑块但没有检测到直线
                        print("[Control] 未检测到目标直线")
                else:
                    print("[Control] 未检测到滑块")
                    
            except queue.Empty:
                # 超时，继续等待
                continue
            except Exception as e:
                print(f"[Control] 错误: {e}")
                time.sleep(0.1)
        
        print("[Control] 控制线程退出")
        
        # 关闭串口
        if self.ser:
            self.ser.close()
            print("[Controller] 串口已关闭")
    
    def move_motor(self, distance_mm):
        """
        移动电机指定距离
        
        Args:
            distance_mm: 移动距离（毫米）
                        正数：向上移动（X轴正方向）
                        负数：向下移动（X轴负方向）
        
        Returns:
            bool: 是否成功发送指令
        """
        if not self.ser or not self.ser.is_open:
            print("[Control] 错误：串口未连接")
            return False
        
        try:
            # 构建 G-code 指令
            # G0 = 快速移动
            # X = 移动距离（已设置 G91 相对坐标模式）
            # F = 进给速度（mm/min）
            gcode = f"G0 X{distance_mm:.2f} F{Config.FEED_RATE}\n"
            
            # 发送指令
            self.ser.write(gcode.encode('utf-8'))
            
            return True
            
        except Exception as e:
            print(f"[Control] 发送指令失败: {e}")
            return False