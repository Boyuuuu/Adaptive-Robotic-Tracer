# AppConfig.py
class Config:
    # ==========================
    # 0. 控制模式选择
    # ==========================
    # 修改此字段即可切换控制算法，无需改动其他代码
    # 可选值（需与 ControllerManager.py 中注册的 key 一致）：
    #   'simple_incremental'       → 简单增量控制（Bang-Bang，固定步长）
    #   'pid'                      → PID 控制
    #   'Motor_Motion_Calibration' → 电机运动标定模式
    #   'false'                    → 关闭控制逻辑
    CONTROL_MODE = 'false'

    # ==========================
    # 1. 硬件通信参数
    # ==========================
    SERIAL_PORT = 'COM8'     # 请根据设备管理器修改，比如 'COM3'
    BAUD_RATE   = 115200     # 串口波特率

    # ==========================
    # 2. 摄像头与视觉参数
    # ==========================
    # 视觉算法选择，可选值（需与 VisionManager.py 注册的 key 一致）：
    #   'traditional' → 传统 OpenCV 色块/轮廓识别
    #   'yolo'        → 人工智能 YOLO 目标检测 (暂未实现)
    VISION_MODE    = 'yolo'

    YOLO_MODEL_PATH = r"E:\1111AdaptiveSlidingTable\Code\model\yolo_20260304_112156\best.pt"
    YOLO_DEVICE = ""
    YOLO_IMG_SIZE = 512
    YOLO_CONF_THRESHOLD = 0.50
    YOLO_IOU_THRESHOLD = 0.45

    CAM_INDEX      = 0      # 摄像头索引，0通常是默认摄像头
    FRAME_WIDTH    = 640    # 分辨率宽
    FRAME_HEIGHT   = 480    # 分辨率高
    VISION_VERBOSE = False  # 是否打印每帧检测日志（True=打印，False=静默）

    # deviation_y 滤波参数
    VISION_MAX_JUMP_PX = 10    # 跳跃限幅：单帧最大允许变化量（像素），超过则截断
    VISION_EMA_ALPHA   = 0.4   # EMA 平滑系数：0=完全不跟踪，1=无滤波；越小越平滑

    # 黑色滑台检测参数
    SLIDER_AREA_MIN = 250      # 滑台轮廓面积下限（像素²），排除小噪点
    SLIDER_AREA_MAX = 2000     # 滑台轮廓面积上限（像素²），排除背景大块

    # ROI (感兴趣区域) 设置，格式: (x_start, y_start, x_end, y_end)
    ROI_COORDS = (200, 15, 360, 450 )

    # 颜色阈值 (HSV模式)
    HSV_LOWER = (35, 43, 46)    # H最小值, S最小值, V最小值
    HSV_UPPER = (77, 255, 255)  # H最大值, S最大值, V最大值

    # ==========================
    # 3. 运动控制参数
    # ==========================
    FEED_RATE    = 4000    # G-code 进给速度 (mm/min)，所有控制器共用
    CONTROL_FREQ = 0.05   # 节流间隔 (秒)，0.05s ≈ 20Hz 上限

    # --- 3a. SimpleIncrementalController（Bang-Bang）专用 ---
    INCREMENTAL_DEADZONE_PX   = 25    # 死区（像素）：偏差绝对值 ≤ 此值时不发指令
    INCREMENTAL_STEP_DISTANCE = 2.0   # 每次移动固定步长 (mm)
    INCREMENTAL_FEED_RATE     = 6000  # Bang-Bang 专用进给速度 (mm/min)，需快速响应

    # --- 3b. PIDController 专用 ---
    # 调参建议：先只开 Kp，逐步加 Kd 抑制震荡，最后少量加 Ki 消除静差
    PID_DEADZONE_MM    = 1.0    # 死区（mm）：偏差绝对值 ≤ 此值时不发指令
    PID_KP             = 0.8    # 比例增益：偏差每 1mm → 输出 Kp mm
    PID_KI             = 0.0    # 积分增益：消除长期静差（初始设 0，避免积分饱和）
    PID_KD             = 0.0    # 微分增益：抑制超调
    PID_OUTPUT_LIMIT   = 5.0    # 输出限幅：单次最大移动量 (mm)，防止过冲
    PID_INTEGRAL_LIMIT = 10.0   # 积分限幅：防止积分饱和（Anti-windup）

    # ==========================
    # 4. 标定参数
    # ==========================
    # 4a. 像素-物理标定
    CALIBRATION_Y1    = 50   # 作为运动死区的上界限
    CALIBRATION_Y2    = 450  # 作为运动死区的下界限
    PIXEL_TO_MM_RATIO = 1.61538   # 1 像素 = 多少 mm（由物理标定测量后填入）

    # 4b. 电机运动标定参数
    Motor_Step_Angle               = 1.8      # 步进角 (°)
    Motor_Step_Per_Rotation        = 200      # 每转步数
    Motor_Driver_Fine              = 16       # 驱动器细分（200×16=3200 步/转）
    Motor_Mechanical_Pitch         = 72       # 机械导程 (mm/转)
    Motor_THEORETICAL_STEPS_PER_MM = 44.444  # 理论步数/mm = (细分×步数/转) ÷ 导程
    Motor_ACTUAL_STEPS_PER_MM      = 44.444  # 实际步数/mm（标定后填入，初始=理论值）

    CALIBRATION_STEP_MM   = 5.0    # 建立零点的初始小步长 (mm)
    CALIBRATION_TRAVEL_MM = 200.0  # 距离标定行程 (mm)

    GRBL_ACCELERATION     = 200    # 初始加速度 (mm/s²)，写入 $120，偏低保证安全
    ACCEL_CALIB_FEED_RATE = 18000   # 加速度标定专用速度 (mm/min)，与 $110 上限对齐
    ACCEL_CALIB_MAX_RATE  = 18000   # 标定期间临时写入 $110（X轴最大速率）
    BUSINESS_MAX_RATE     = 18000   # 业务控制器使用的 $110（标定完成后恢复此值）
    ACCEL_CALIB_TRAVEL_MM = 200.0  # 加速度标定来回行程 (mm)
    ACCEL_CALIB_REPEAT    = 3      # 来回重复次数
