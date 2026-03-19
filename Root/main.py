# main.py
from queue import Queue
from VisionManager import VisionManager
from ControllerManager import create_controller
from AppConfig import Config
import sys
import os
import time

# CalibrationController 位于 Code/ControlMode，需要将 Code 加入搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def main():
    # 1. 创建共享队列（容量为1，控制器始终消费最新一帧）
    shared_queue = Queue(maxsize=1)

    # 2. 创建视觉线程 (使用了全新封装的模块化架构)
    vision_t = VisionManager(shared_queue)

    # 3. 根据 CONTROL_MODE 决定是否启动控制器
    #    CONTROL_MODE = 'false' → 纯视觉模式，不创建串口/控制线程
    #    其他值（含 'Motor_Motion_Calibration'）→ 通过 ControllerManager 创建对应控制器
    vision_only = (
        Config.CONTROL_MODE == 'false'
    )
    if vision_only:
        print(f"[Main] 纯视觉模式（CONTROL_MODE={Config.CONTROL_MODE}）")
        vision_t.start()

        try:
            while vision_t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Main] 收到退出信号，正在停止...")

        vision_t.running = False
        vision_t.join()

    else:
        controller_t = create_controller(shared_queue)
        vision_t.start()
        controller_t.start()

        # 主线程守护：任意子线程退出时主线程一起退出
        try:
            while vision_t.is_alive() and controller_t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Main] 收到退出信号，正在停止...")

        # 优雅退出
        vision_t.running = False
        controller_t.stop()

        vision_t.join()
        controller_t.join()

    print("[Main] 程序已完全退出。")

if __name__ == "__main__":
    main()