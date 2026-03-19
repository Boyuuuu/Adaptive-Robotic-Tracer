# BaseController.py
# 控制线程基类：封装串口通信、G-code同步发送等通用逻辑
# 子类只需实现 control_logic(vision_data) 一个方法

import threading
import serial
import time
import queue
import sys
import os

# 将 Root 目录加入模块搜索路径，以便导入 AppConfig
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Root'))
from AppConfig import Config


class BaseControlThread(threading.Thread):
    """
    控制线程基类

    职责边界：
        - 串口连接与初始化（G21/G91）
        - G-code 发送并阻塞等待 GRBL 的 ok 响应（解决指令堆积/不同步问题）
        - 主循环框架：从队列取数据 → 调用 control_logic()
        - 资源释放（串口关闭）

    子类职责：
        - 只需实现 control_logic(vision_data) 方法，填写具体控制算法
    """

    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self.running = True
        self.daemon = True                          # 随主线程退出，防止进程残留
        self.name = self.__class__.__name__         # 线程名 = 子类类名，方便日志区分
        self.ser = self._init_serial()              # 串口初始化

    # ══════════════════════════════════════════════════════════
    # 1. 串口初始化
    # ══════════════════════════════════════════════════════════

    def _init_serial(self):
        """
        连接串口，等待 GRBL 启动，并发送初始化指令。

        Returns:
            serial.Serial 对象，或 None（连接失败时）
        """
        try:
            ser = serial.Serial(
                Config.SERIAL_PORT,
                Config.BAUD_RATE,
                timeout=0.1   # readline() 单次读超时，短值让循环可以快速检查 deadline
            )
            print(f"[{self.name}] 成功连接到 {Config.SERIAL_PORT}")

            # 等待 ESP32/GRBL 重启完成（GRBL 上电后会打印欢迎信息）
            time.sleep(2)

            # 清空 GRBL 启动时输出的欢迎字符串，避免干扰后续 ok 解析
            ser.flushInput()

            # 发送初始化指令：毫米单位(G21) + 相对坐标模式(G91)
            ok = self._send_gcode_and_wait("G21 G91", ser=ser)
            if ok:
                print(f"[{self.name}] 初始化指令 G21 G91 已确认（收到 ok）")
            else:
                print(f"[{self.name}] 警告：初始化指令未收到 ok 响应，请检查串口连接")

            return ser

        except serial.SerialException as e:
            print(f"[{self.name}] 串口连接失败: {e}")
            self.running = False
            return None

    # ══════════════════════════════════════════════════════════
    # 2. G-code 同步发送（核心方法，解决堆积/不同步问题）
    # ══════════════════════════════════════════════════════════

    def _send_gcode_and_wait(self, cmd: str, ser=None) -> bool:
        """
        发送一行 G-code，并阻塞等待 GRBL 回复 'ok' 或 'error:X'。

        【设计说明】
            GRBL 协议保证：每收到一条完整指令，必然回复一行响应。
            - 'ok'      → 指令被接受并加入执行队列
            - 'error:X' → 指令非法，被拒绝
            此方法通过等待响应，确保调用方在 GRBL 确认前不会发送下一条指令，
            从而从根本上解决指令在控制板缓冲区堆积的问题。

        Args:
            cmd: G-code 字符串（不含换行符），例如 "G0 X2.00 F600"
            ser: 串口对象，传入时使用外部对象（初始化阶段用），
                 默认为 None 则使用 self.ser

        Returns:
            True  → 收到 'ok'
            False → 收到 'error:X' 或等待超时（5秒）
        """
        _ser = ser if ser is not None else self.ser

        if not _ser or not _ser.is_open:
            print(f"[{self.name}] 串口未就绪，无法发送: {cmd}")
            return False

        try:
            # 发送指令（末尾加换行，GRBL 以 \n 作为指令终结符）
            _ser.write(f"{cmd}\n".encode('utf-8'))

            # 阻塞等待 GRBL 响应，最长 5 秒
            # 注意：serial timeout=0.1s，readline() 无数据时返回 b''（空字节）
            # 必须显式处理空响应，否则空字符串会悄悄跳过所有分支，导致超时后返回 False
            deadline = time.time() + 5.0
            while time.time() < deadline:
                raw = _ser.readline()
                line = raw.decode('utf-8', errors='ignore').strip()

                if not line:
                    # readline() 超时，本次没有数据，继续等待下一行
                    continue

                if line == 'ok':
                    return True
                elif line.startswith('error'):
                    print(f"[{self.name}] GRBL 拒绝指令 [{cmd}]: {line}")
                    return False
                else:
                    # GRBL 有时输出状态消息（如 <Idle|MPos:...>），忽略继续等待
                    print(f"[{self.name}] 忽略 GRBL 消息: {line}")

            print(f"[{self.name}] 等待 ok 超时（指令: {cmd}）")
            return False

        except Exception as e:
            print(f"[{self.name}] 发送指令时发生异常: {e}")
            return False

    def _wait_for_buffer_free(self, min_free: int = 15, timeout: float = 10.0) -> bool:
        """
        持续发送 '?' 查询 GRBL 规划器缓冲区，直到可用块数 >= min_free。

        【设计说明】
            不等电机完全停止（Idle），而是等缓冲区几乎排空：
                min_free=15 → 缓冲区最多剩 1 条指令在执行
            效果：
                - 当前指令快执行完时，立刻塞入下一条 → 运动近乎连续，消除卡顿
                - 下一条指令基于最新视觉帧计算 → 保证实时性
                - 缓冲区不会堆积旧指令 → 避免控制滞后

        Args:
            min_free: 规划器缓冲区最少剩余可用块数，默认 15（即只允许 1 条在跑）
            timeout:  最长等待时间（秒）

        Returns:
            True  → 缓冲区已达到要求
            False → 超时或串口未就绪
        """
        if not self.ser or not self.ser.is_open:
            return False

        deadline = time.time() + timeout
        while time.time() < deadline:
            # 发送实时查询指令 '?'（GRBL 实时命令，不需要换行符）
            self.ser.write(b'?')

            # 读取响应，寻找包含 Bf: 字段的状态行
            # 格式示例：<Run|MPos:0.000,0.000,0.000|Bf:15,128|FS:600,0>
            inner_deadline = time.time() + 0.1
            while time.time() < inner_deadline:
                raw = self.ser.readline()
                line = raw.decode('utf-8', errors='ignore').strip()

                if line.startswith('<') and 'Bf:' in line:
                    try:
                        # 截取 Bf: 后面的第一个数字（规划器可用块数）
                        bf_part = line.split('Bf:')[1].split('|')[0].rstrip('>')
                        available = int(bf_part.split(',')[0])
                        if available >= min_free:
                            return True
                        # 可用数不足，跳出内层循环，继续轮询
                        break
                    except (IndexError, ValueError):
                        pass  # 解析失败，继续读下一行
                # 忽略 ok 及其他非状态行

            time.sleep(0.005)  # 5ms 轮询间隔（~200Hz），避免刷爆串口

        print(f"[{self.name}] 等待缓冲区可用超时（min_free={min_free}）")
        return False

    # ══════════════════════════════════════════════════════════
    # 3. 电机移动（通用接口，供子类直接调用）
    # ══════════════════════════════════════════════════════════

    def move_motor(self, distance_mm: float, feed_rate: float = None) -> bool:
        """
        以相对坐标模式移动电机指定距离（阻塞，直到 GRBL 确认）。

        Args:
            distance_mm: 移动距离（毫米）
                         正数 → X轴正方向（向上）
                         负数 → X轴负方向（向下）
            feed_rate:   进给速度 (mm/min)，默认使用 Config.FEED_RATE
                         子类可传入专用速度（例如 SimpleIncremental 使用高速）

        Returns:
            True  → GRBL 已接受指令
            False → 串口未连接或 GRBL 拒绝指令
        """
        if not self.ser or not self.ser.is_open:
            print(f"[{self.name}] 错误：串口未连接")
            return False

        f = feed_rate if feed_rate is not None else Config.FEED_RATE
        gcode = f"G1 X{distance_mm:.2f} F{f:.0f}"
        
        # 1. 发送并等待 ok（确认指令被 GRBL 接受，几乎是立即返回）
        if not self._send_gcode_and_wait(gcode):
            return False

        # 2. 等待缓冲区几乎排空（Bf >= 15，即仅剩 1 条指令在执行）
        #    不等 Idle，避免电机完全停止造成 Stop-and-Go 卡顿
        return self._wait_for_buffer_free(min_free=15)

    # ══════════════════════════════════════════════════════════
    # 4. 主循环（子类通常不需要重写）
    # ══════════════════════════════════════════════════════════

    def run(self):
        print(f"[{self.name}] 控制线程启动 → 模式: {self.__class__.__name__}")

        while self.running:
            try:
                # 从队列获取视觉数据，超时 1 秒（避免永久阻塞）
                vision_data = self.data_queue.get(timeout=1.0)

                # 清空队列中在等待期间堆积的旧帧，只保留最新一帧
                # 原因：move_motor 等待缓冲区期间，视觉线程继续产帧，
                #       旧帧数据已过时，继续使用会导致控制滞后
                while not self.data_queue.empty():
                    try:
                        vision_data = self.data_queue.get_nowait()
                    except queue.Empty:
                        break

                if vision_data.get('detected'):
                    # 安全边界检查：滑块必须在 [CALIBRATION_Y1, CALIBRATION_Y2] 范围内
                    if not self._is_within_bounds(vision_data):
                        # 超界时不发指令，循环继续等待下一帧
                        continue
                    # ← 调用子类实现的具体控制算法
                    self.control_logic(vision_data)
                else:
                    print(f"[{self.name}] 未检测到目标，跳过本帧")

            except queue.Empty:
                # 正常超时（Vision 线程暂时无数据），继续等待
                continue
            except Exception as e:
                # 子类 control_logic 中的意外异常，打印后继续运行（不崩溃）
                print(f"[{self.name}] 控制循环出现异常: {type(e).__name__}: {e}")
                time.sleep(0.1)

        # 退出循环后释放资源
        self._cleanup()

    # ══════════════════════════════════════════════════════════
    # 5. 资源管理
    # ══════════════════════════════════════════════════════════

    def stop(self):
        """线程安全地停止控制循环（供外部调用）"""
        self.running = False

    def _cleanup(self):
        """线程退出时自动释放串口资源"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"[{self.name}] 串口已关闭")
        print(f"[{self.name}] 控制线程已退出")

    def _is_within_bounds(self, vision_data: dict) -> bool:
        """
        检查滑块是否在安全范围内（ROI 坐标系）。

        边界定义（来自 AppConfig）：
            CALIBRATION_Y1 → 上死区边界（滑块上缘不得小于此值）
            CALIBRATION_Y2 → 下死区边界（滑块下缘不得大于此值）

        超出任一边界时打印警告并返回 False，控制器不发运动指令。
        """
        top    = vision_data.get('slider_top_y')
        bottom = vision_data.get('slider_bottom_y')

        if top is None or bottom is None:
            return True   # 坐标未知时不拦截，让 control_logic 自己判断

        if top < Config.CALIBRATION_Y1:
            print(f"[{self.name}] ⚠️  滑块上缘 {top}px < 上死区 {Config.CALIBRATION_Y1}px，停止运动")
            return False

        if bottom > Config.CALIBRATION_Y2:
            print(f"[{self.name}] ⚠️  滑块下缘 {bottom}px > 下死区 {Config.CALIBRATION_Y2}px，停止运动")
            return False

        return True

    # ══════════════════════════════════════════════════════════
    # 6. 抽象接口（子类必须实现）
    # ══════════════════════════════════════════════════════════

    def control_logic(self, vision_data: dict):
        """
        【抽象方法】子类必须实现此方法来定义具体的控制算法。

        Args:
            vision_data: 来自 Vision 线程的数据字典，调用时保证 detected=True
                         包含字段:
                             detected       (bool)  : 是否检测到目标
                             deviation_y    (float) : Y轴偏差（像素），可能为None
                             slider_center_y(int)   : 滑块中心Y坐标
                             slider_top_y   (int)   : 滑块上边缘Y坐标
                             slider_bottom_y(int)   : 滑块下边缘Y坐标
                             line_center_y  (int)   : 直线中心Y坐标，可能为None
                             timestamp      (float) : 数据时间戳
        """
        raise NotImplementedError(
            f"类 '{self.__class__.__name__}' 必须实现 control_logic() 方法"
        )