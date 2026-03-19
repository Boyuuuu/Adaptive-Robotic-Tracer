# 自动标定与控制系统开发计划

## 📋 项目概述

### 目标
实现滑台的自动标定和精确控制系统，通过视觉反馈自动计算电机指令与像素位置的对应关系。

### 核心原理
1. 控制电机移动固定距离 XX
2. 视觉系统测量滑块实际移动的像素距离
3. 正反两次移动取平均，消除机械间隙影响
4. 计算标定系数：`像素/距离`
5. 使用标定系数实现精确控制

### 方案验证
```
初始状态：滑块中心 Y = 100 (像素)

步骤1：向上移动 XX 距离
  → 滑块中心 Y = 80 (像素)
  → 像素位置差1 = |100 - 80| = 20 像素

步骤2：向下移动 XX 距离（回到原点）
  → 滑块中心 Y = 100 (像素)

步骤3：向下移动 XX 距离
  → 滑块中心 Y = 120 (像素)
  → 像素位置差2 = |100 - 120| = 20 像素

步骤4：计算标定系数
  → 平均像素位置差 = (20 + 20) / 2 = 20 像素
  → 标定系数 = 20 像素 / XX 距离
  → 例如：20 像素 / 10mm = 2 像素/mm
```

---

## 🛠️ 开发阶段

### 阶段 1：基础数据采集
**预计时间**：1-2 小时  
**目标**：实现视觉数据到控制线程的传递

#### 步骤 1.1：修改 Vision.py - 数据传递

**需要修改的位置**：`Vision.py` 的 `run()` 方法

**添加内容**：
```python
# 在计算完 slider_center_y 后，将数据放入队列
if slider_top_y is not None and slider_bottom_y is not None:
    slider_center_y = (slider_top_y + slider_bottom_y) // 2
    
    # 准备数据包
    vision_data = {
        'slider_center_y': slider_center_y,
        'slider_top_y': slider_top_y,
        'slider_bottom_y': slider_bottom_y,
        'line_center_y': line_center_y if line_center_y is not None else None,
        'deviation_y': deviation_y if line_center_y is not None else None,
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
    # 队列满时丢弃旧数据
    try:
        self.data_queue.get_nowait()
        self.data_queue.put_nowait(vision_data)
    except:
        pass
```

**需要导入**：
```python
import queue
```

#### 步骤 1.2：修改 Controller.py - 接收数据

**需要修改的位置**：`Controller.py` 的 `run()` 方法

**添加内容**：
```python
def run(self):
    print("[Control] 控制线程启动...")
    
    while self.running:
        try:
            # 从队列读取视觉数据（超时1秒）
            vision_data = self.data_queue.get(timeout=1.0)
            
            if vision_data['detected']:
                slider_y = vision_data['slider_center_y']
                print(f"[Control] 滑块位置: Y={slider_y}")
                
                # TODO: 后续在这里添加控制逻辑
            else:
                print("[Control] 未检测到滑块")
                
        except queue.Empty:
            # 超时，继续等待
            continue
        except Exception as e:
            print(f"[Control] 错误: {e}")
            time.sleep(0.1)
    
    print("[Control] 控制线程退出")
```

#### 步骤 1.3：测试数据传递

**运行程序**：
```bash
python main.py
```

**预期输出**：
```
[Vision] 滑块位置(ROI): 上=80, 下=120
[Control] 滑块位置: Y=100
[Vision] 滑块位置(ROI): 上=81, 下=121
[Control] 滑块位置: Y=101
...
```

**验证标准**：
- ✅ 控制台持续输出滑块位置
- ✅ 位置数据与视觉线程一致
- ✅ 无报错或异常

---

### 阶段 2：手动标定测试
**预计时间**：2-3 小时  
**目标**：手动控制电机，验证标定方案可行性

#### 步骤 2.1：创建手动控制脚本

**新建文件**：`manual_calibration_test.py`

**文件内容**：
```python
"""
手动标定测试脚本
用于验证标定方案的可行性
"""
import time
import threading
from queue import Queue
from Vision import VisionThread
from Controller import ControlThread

class ManualCalibrationTest:
    def __init__(self):
        self.data_queue = Queue(maxsize=10)
        self.vision_thread = VisionThread(self.data_queue, enable_debug=True)
        self.control_thread = ControlThread(self.data_queue)
        
        self.positions = []  # 记录位置
        
    def start(self):
        """启动线程"""
        self.vision_thread.start()
        self.control_thread.start()
        
        print("=" * 50)
        print("手动标定测试")
        print("=" * 50)
        print("指令:")
        print("  r - 记录当前位置")
        print("  w - 向上移动（手动控制电机）")
        print("  s - 向下移动（手动控制电机）")
        print("  c - 计算像素差")
        print("  q - 退出")
        print("=" * 50)
        
        self.run_manual_control()
    
    def run_manual_control(self):
        """手动控制循环"""
        while True:
            cmd = input("输入指令: ").strip().lower()
            
            if cmd == 'r':
                self.record_position()
            elif cmd == 'w':
                print("[提示] 请手动控制电机向上移动，然后按 'r' 记录位置")
            elif cmd == 's':
                print("[提示] 请手动控制电机向下移动，然后按 'r' 记录位置")
            elif cmd == 'c':
                self.calculate_difference()
            elif cmd == 'q':
                self.stop()
                break
            else:
                print("[错误] 未知指令")
    
    def record_position(self):
        """记录当前滑块位置"""
        try:
            # 获取最新的视觉数据
            vision_data = self.data_queue.get(timeout=1.0)
            
            if vision_data['detected']:
                pos = vision_data['slider_center_y']
                self.positions.append(pos)
                print(f"[记录] 位置 {len(self.positions)}: Y={pos}")
            else:
                print("[错误] 未检测到滑块")
        except:
            print("[错误] 无法获取视觉数据")
    
    def calculate_difference(self):
        """计算位置差"""
        if len(self.positions) < 2:
            print("[错误] 至少需要记录2个位置")
            return
        
        print("\n" + "=" * 50)
        print("位置记录:")
        for i, pos in enumerate(self.positions):
            print(f"  位置 {i+1}: Y={pos}")
        
        print("\n位置差计算:")
        for i in range(1, len(self.positions)):
            diff = abs(self.positions[i] - self.positions[i-1])
            print(f"  位置{i+1} - 位置{i} = {diff} 像素")
        
        if len(self.positions) >= 3:
            # 计算平均值（假设是正向-反向-正向的模式）
            diff1 = abs(self.positions[1] - self.positions[0])
            diff2 = abs(self.positions[2] - self.positions[1])
            avg_diff = (diff1 + diff2) / 2
            print(f"\n平均像素差: {avg_diff:.2f} 像素")
            print(f"如果移动距离是 XX mm，则标定系数 = {avg_diff:.2f} / XX")
        
        print("=" * 50 + "\n")
        
        # 清空记录
        choice = input("是否清空记录？(y/n): ").strip().lower()
        if choice == 'y':
            self.positions.clear()
            print("[清空] 位置记录已清空")
    
    def stop(self):
        """停止所有线程"""
        print("\n正在退出...")
        self.vision_thread.running = False
        self.control_thread.running = False
        self.vision_thread.join()
        self.control_thread.join()
        print("已退出")

if __name__ == "__main__":
    test = ManualCalibrationTest()
    test.start()
```

#### 步骤 2.2：执行手动测试

**测试流程**：
1. 运行脚本：`python manual_calibration_test.py`
2. 按 `r` 记录初始位置
3. 手动控制电机向上移动固定距离
4. 按 `r` 记录移动后位置
5. 手动控制电机向下移动（回到原点）
6. 手动控制电机向下移动固定距离
7. 按 `r` 记录移动后位置
8. 按 `c` 计算像素差

**预期输出**：
```
[记录] 位置 1: Y=100
[记录] 位置 2: Y=80
[记录] 位置 3: Y=120

位置差计算:
  位置2 - 位置1 = 20 像素
  位置3 - 位置2 = 40 像素

平均像素差: 30.00 像素
如果移动距离是 XX mm，则标定系数 = 30.00 / XX
```

**验证标准**：
- ✅ 能够记录滑块位置
- ✅ 位置差计算正确
- ✅ 正反两次移动的像素差接近

---

### 阶段 3：自动标定流程
**预计时间**：4-6 小时  
**目标**：实现全自动标定，无需人工干预

#### 步骤 3.1：设计标定状态机

**新建文件**：`CalibrationController.py`

**状态定义**：
```python
from enum import Enum

class CalibrationState(Enum):
    """标定状态"""
    IDLE = 0              # 空闲
    CHECK_INITIAL = 1     # 检查初始位置
    WAIT_STABLE_0 = 2     # 等待稳定（初始）
    RECORD_INITIAL = 3    # 记录初始位置
    MOVE_FORWARD = 4      # 正向移动
    WAIT_STABLE_1 = 5     # 等待稳定（正向）
    RECORD_FORWARD = 6    # 记录正向位置
    MOVE_BACK = 7         # 返回原点
    WAIT_STABLE_2 = 8     # 等待稳定（返回）
    MOVE_BACKWARD = 9     # 反向移动
    WAIT_STABLE_3 = 10    # 等待稳定（反向）
    RECORD_BACKWARD = 11  # 记录反向位置
    CALCULATE = 12        # 计算标定系数
    DONE = 13             # 完成
    ERROR = 14            # 错误
```

#### 步骤 3.2：实现标定控制器

**CalibrationController.py 核心逻辑**：
```python
class CalibrationController:
    def __init__(self, data_queue, control_thread, move_distance=10):
        """
        Args:
            data_queue: 视觉数据队列
            control_thread: 控制线程（用于发送电机指令）
            move_distance: 标定移动距离（mm）
        """
        self.data_queue = data_queue
        self.control_thread = control_thread
        self.move_distance = move_distance
        
        self.state = CalibrationState.IDLE
        self.positions = []  # 记录的位置
        self.stable_counter = 0  # 稳定计数器
        self.last_position = None
        
        self.calibration_factor = None  # 标定系数（像素/mm）
    
    def start_calibration(self):
        """开始标定"""
        print("[标定] 开始自动标定流程...")
        self.state = CalibrationState.CHECK_INITIAL
        self.positions.clear()
        
        # 运行状态机
        while self.state != CalibrationState.DONE and self.state != CalibrationState.ERROR:
            self.update()
            time.sleep(0.1)
        
        if self.state == CalibrationState.DONE:
            print(f"[标定] 完成！标定系数 = {self.calibration_factor:.4f} 像素/mm")
            return self.calibration_factor
        else:
            print("[标定] 失败！")
            return None
    
    def update(self):
        """状态机更新"""
        if self.state == CalibrationState.CHECK_INITIAL:
            self._check_initial_position()
        elif self.state == CalibrationState.WAIT_STABLE_0:
            self._wait_stable(CalibrationState.RECORD_INITIAL)
        elif self.state == CalibrationState.RECORD_INITIAL:
            self._record_position("初始位置")
            self.state = CalibrationState.MOVE_FORWARD
        elif self.state == CalibrationState.MOVE_FORWARD:
            self._move_motor(self.move_distance, "正向")
            self.state = CalibrationState.WAIT_STABLE_1
        # ... 其他状态的实现
    
    def _check_initial_position(self):
        """检查初始位置是否合适"""
        vision_data = self._get_vision_data()
        if not vision_data or not vision_data['detected']:
            print("[标定] 错误：未检测到滑块")
            self.state = CalibrationState.ERROR
            return
        
        # 检查是否在视野中心附近
        slider_y = vision_data['slider_center_y']
        # TODO: 添加位置检查逻辑
        
        print(f"[标定] 初始位置检查通过: Y={slider_y}")
        self.state = CalibrationState.WAIT_STABLE_0
    
    def _wait_stable(self, next_state, threshold=2, count=10):
        """等待位置稳定"""
        vision_data = self._get_vision_data()
        if not vision_data or not vision_data['detected']:
            return
        
        current_pos = vision_data['slider_center_y']
        
        if self.last_position is None:
            self.last_position = current_pos
            self.stable_counter = 0
            return
        
        # 检查位置变化
        if abs(current_pos - self.last_position) < threshold:
            self.stable_counter += 1
        else:
            self.stable_counter = 0
        
        self.last_position = current_pos
        
        # 稳定足够次数后进入下一状态
        if self.stable_counter >= count:
            print(f"[标定] 位置已稳定: Y={current_pos}")
            self.stable_counter = 0
            self.last_position = None
            self.state = next_state
    
    def _record_position(self, label):
        """记录当前位置"""
        vision_data = self._get_vision_data()
        if vision_data and vision_data['detected']:
            pos = vision_data['slider_center_y']
            self.positions.append(pos)
            print(f"[标定] 记录{label}: Y={pos}")
    
    def _move_motor(self, distance, direction):
        """移动电机"""
        print(f"[标定] {direction}移动 {distance} mm")
        # TODO: 调用控制线程的移动函数
        # self.control_thread.move(distance)
    
    def _get_vision_data(self):
        """获取最新视觉数据"""
        try:
            return self.data_queue.get(timeout=0.5)
        except:
            return None
```

#### 步骤 3.3：完善状态机逻辑

**需要实现的状态**：
- ✅ `CHECK_INITIAL`：检查初始位置
- ✅ `WAIT_STABLE_X`：等待位置稳定
- ✅ `RECORD_XXX`：记录位置
- ✅ `MOVE_XXX`：移动电机
- ✅ `CALCULATE`：计算标定系数

**计算逻辑**：
```python
def _calculate_calibration_factor(self):
    """计算标定系数"""
    if len(self.positions) < 3:
        print("[标定] 错误：记录的位置不足")
        self.state = CalibrationState.ERROR
        return
    
    pos_initial = self.positions[0]
    pos_forward = self.positions[1]
    pos_backward = self.positions[2]
    
    # 计算像素差
    diff_forward = abs(pos_forward - pos_initial)
    diff_backward = abs(pos_backward - pos_initial)
    
    # 取平均
    avg_pixel_diff = (diff_forward + diff_backward) / 2
    
    # 计算标定系数（像素/mm）
    self.calibration_factor = avg_pixel_diff / self.move_distance
    
    print(f"[标定] 正向像素差: {diff_forward}")
    print(f"[标定] 反向像素差: {diff_backward}")
    print(f"[标定] 平均像素差: {avg_pixel_diff:.2f}")
    print(f"[标定] 移动距离: {self.move_distance} mm")
    print(f"[标定] 标定系数: {self.calibration_factor:.4f} 像素/mm")
    
    self.state = CalibrationState.DONE
```

#### 步骤 3.4：集成到主程序

**在 main.py 中添加**：
```python
from CalibrationController import CalibrationController

# 启动标定
calibration = CalibrationController(data_queue, control_thread, move_distance=10)
calibration_factor = calibration.start_calibration()

if calibration_factor:
    print(f"标定成功！系数 = {calibration_factor:.4f} 像素/mm")
else:
    print("标定失败！")
```

---

### 阶段 4：优化与完善
**预计时间**：2-3 小时  
**目标**：提高标定可靠性和准确性

#### 步骤 4.1：添加安全检查

**需要添加的检查**：
```python
def _check_safety(self, vision_data):
    """安全检查"""
    if not vision_data['detected']:
        print("[安全] 错误：滑块丢失")
        return False
    
    slider_y = vision_data['slider_center_y']
    
    # 检查是否超出视野
    if slider_y < 10 or slider_y > (ROI_HEIGHT - 10):
        print(f"[安全] 警告：滑块接近边界 Y={slider_y}")
        return False
    
    return True
```

#### 步骤 4.2：多次标定取平均

**实现逻辑**：
```python
def calibrate_multiple_times(self, num_runs=3):
    """多次标定取平均"""
    factors = []
    
    for i in range(num_runs):
        print(f"\n[标定] 第 {i+1}/{num_runs} 次标定")
        factor = self.start_calibration()
        
        if factor:
            factors.append(factor)
        else:
            print(f"[标定] 第 {i+1} 次失败")
    
    if len(factors) == 0:
        print("[标定] 所有标定均失败")
        return None
    
    # 计算平均值和标准差
    avg_factor = sum(factors) / len(factors)
    std_factor = (sum((f - avg_factor)**2 for f in factors) / len(factors)) ** 0.5
    
    print(f"\n[标定] 标定结果:")
    for i, f in enumerate(factors):
        print(f"  第{i+1}次: {f:.4f} 像素/mm")
    print(f"  平均值: {avg_factor:.4f} 像素/mm")
    print(f"  标准差: {std_factor:.4f}")
    
    # 评估质量
    if std_factor / avg_factor > 0.1:  # 变异系数 > 10%
        print("[标定] 警告：标定结果波动较大，建议重新标定")
    
    return avg_factor
```

#### 步骤 4.3：保存和加载标定结果

**新建文件**：`calibration_data.json`

**保存逻辑**：
```python
import json
from datetime import datetime

def save_calibration(self, factor, filename="calibration_data.json"):
    """保存标定结果"""
    data = {
        'calibration_factor': factor,
        'move_distance': self.move_distance,
        'timestamp': datetime.now().isoformat(),
        'positions': self.positions
    }
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)
    
    print(f"[标定] 已保存到 {filename}")

def load_calibration(filename="calibration_data.json"):
    """加载标定结果"""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        
        factor = data['calibration_factor']
        timestamp = data['timestamp']
        
        print(f"[标定] 已加载标定数据")
        print(f"  标定系数: {factor:.4f} 像素/mm")
        print(f"  标定时间: {timestamp}")
        
        return factor
    except FileNotFoundError:
        print(f"[标定] 未找到标定文件: {filename}")
        return None
```

**在 AppConfig.py 中添加**：
```python
# 标定参数
CALIBRATION_FILE = "calibration_data.json"
CALIBRATION_MOVE_DISTANCE = 10  # mm
CALIBRATION_RUNS = 3  # 标定次数
```

---

### 阶段 5：正常控制逻辑
**预计时间**：3-4 小时  
**目标**：使用标定系数实现精确控制

#### 步骤 5.1：实现基础控制器

**在 Controller.py 中添加**：
```python
class ControlThread(threading.Thread):
    def __init__(self, data_queue, calibration_factor=None):
        super().__init__()
        self.data_queue = data_queue
        self.calibration_factor = calibration_factor
        self.running = True
        
        # 控制参数
        self.deadzone = 5  # 死区（像素）
        self.max_move = 20  # 最大单次移动距离（mm）
    
    def run(self):
        print("[Control] 控制线程启动...")
        
        while self.running:
            try:
                vision_data = self.data_queue.get(timeout=1.0)
                
                if not vision_data['detected']:
                    print("[Control] 未检测到滑块，停止控制")
                    continue
                
                # 获取偏差
                deviation_y = vision_data.get('deviation_y')
                if deviation_y is None:
                    continue
                
                # 死区判断
                if abs(deviation_y) < self.deadzone:
                    # 在死区内，不移动
                    continue
                
                # 计算需要移动的距离
                if self.calibration_factor:
                    move_distance = deviation_y / self.calibration_factor
                    
                    # 限幅
                    move_distance = max(-self.max_move, min(self.max_move, move_distance))
                    
                    # 执行移动
                    self.move_motor(move_distance)
                    print(f"[Control] 偏差={deviation_y}px, 移动={move_distance:.2f}mm")
                else:
                    print("[Control] 警告：未进行标定，无法控制")
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Control] 错误: {e}")
                time.sleep(0.1)
    
    def move_motor(self, distance):
        """移动电机"""
        # TODO: 实现实际的电机控制
        # 调用串口发送指令
        pass
```

#### 步骤 5.2：添加 PID 控制（可选）

**PID 控制器**：
```python
class PIDController:
    def __init__(self, kp=1.0, ki=0.0, kd=0.0):
        self.kp = kp  # 比例系数
        self.ki = ki  # 积分系数
        self.kd = kd  # 微分系数
        
        self.last_error = 0
        self.integral = 0
    
    def update(self, error, dt):
        """更新 PID 控制器"""
        # 比例项
        p_term = self.kp * error
        
        # 积分项
        self.integral += error * dt
        i_term = self.ki * self.integral
        
        # 微分项
        derivative = (error - self.last_error) / dt if dt > 0 else 0
        d_term = self.kd * derivative
        
        # 更新状态
        self.last_error = error
        
        # 输出
        output = p_term + i_term + d_term
        return output
```

**集成到控制器**：
```python
self.pid = PIDController(kp=0.5, ki=0.0, kd=0.1)

# 在控制循环中
output = self.pid.update(deviation_y, dt=0.1)
move_distance = output / self.calibration_factor
```

#### 步骤 5.3：添加控制模式切换

**控制模式**：
```python
class ControlMode(Enum):
    IDLE = 0        # 空闲（不控制）
    MANUAL = 1      # 手动控制
    AUTO = 2        # 自动跟踪
    CALIBRATION = 3 # 标定模式
```

**模式切换逻辑**：
```python
def set_mode(self, mode):
    """切换控制模式"""
    self.mode = mode
    print(f"[Control] 切换到模式: {mode.name}")
    
    if mode == ControlMode.IDLE:
        self.stop_motor()
    elif mode == ControlMode.AUTO:
        if not self.calibration_factor:
            print("[Control] 错误：未标定，无法进入自动模式")
            self.mode = ControlMode.IDLE
```

---

## 📊 开发时间估算

| 阶段 | 预计时间 | 累计时间 |
|------|---------|---------|
| 阶段1：基础数据采集 | 1-2小时 | 1-2小时 |
| 阶段2：手动标定测试 | 2-3小时 | 3-5小时 |
| 阶段3：自动标定流程 | 4-6小时 | 7-11小时 |
| 阶段4：优化与完善 | 2-3小时 | 9-14小时 |
| 阶段5：正常控制逻辑 | 3-4小时 | 12-18小时 |

**总计**：12-18 小时（分 2-3 天完成）

---

## ✅ 验收标准

### 阶段 1
- ✅ 视觉数据能正确传递到控制线程
- ✅ 控制台持续输出滑块位置
- ✅ 无数据丢失或延迟

### 阶段 2
- ✅ 能够手动记录滑块位置
- ✅ 能够计算位置差
- ✅ 正反两次移动的像素差接近（误差 < 10%）

### 阶段 3
- ✅ 自动标定流程能完整运行
- ✅ 能够计算出标定系数
- ✅ 标定系数合理（例如：1-5 像素/mm）

### 阶段 4
- ✅ 多次标定结果一致（标准差 < 10%）
- ✅ 能够保存和加载标定数据
- ✅ 有完善的错误处理

### 阶段 5
- ✅ 能够根据偏差自动控制电机
- ✅ 滑块能够跟踪直线
- ✅ 跟踪精度在死区范围内（< 5 像素）

---

## 🎯 下一步行动

### 立即开始
1. **阶段 1.1**：修改 `Vision.py`，添加数据传递
2. **阶段 1.2**：修改 `Controller.py`，接收数据
3. **阶段 1.3**：运行测试，验证数据传递

### 需要准备
- ✅ 确保电机控制接口可用
- ✅ 确定标定移动距离（建议 10-20mm）
- ✅ 准备测试环境（滑块在视野中心）

### 建议
- 每完成一个阶段就测试验证
- 遇到问题及时调整方案
- 记录标定数据用于分析

---

## 📝 注意事项

### 机械方面
- ⚠️ 注意机械间隙（backlash）的影响
- ⚠️ 确保移动速度不要太快
- ⚠️ 检查电机是否有失步现象

### 视觉方面
- ⚠️ 确保滑块检测稳定
- ⚠️ 光照条件要一致
- ⚠️ 避免遮挡和反光

### 软件方面
- ⚠️ 添加超时保护
- ⚠️ 处理异常情况（检测失败、通信错误等）
- ⚠️ 记录日志便于调试

---

## 🎓 总结

这个开发计划遵循**从简单到复杂、从手动到自动**的原则：

1. **先验证数据传递**（最基础）
2. **再手动测试方案**（验证可行性）
3. **然后自动化流程**（核心功能）
4. **最后优化完善**（提高可靠性）
5. **集成控制逻辑**（实际应用）

每个阶段都有明确的目标和验收标准，便于逐步推进和调试。

**准备好开始了吗？** 建议从阶段 1 开始！🚀
