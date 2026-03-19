import serial
import time

port = 'COM8' 
baudrate = 115200

try:
    ser = serial.Serial(port, baudrate, timeout=1)
    time.sleep(2) 

    def send(cmd):
        print(f"执行中: {cmd}")
        ser.write((cmd + '\n').encode())
        while True:
            res = ser.readline().decode().strip()
            if res == 'ok':
                break

    # --- 初始化 ---
    send("$X")          # 解锁
    send("G91")         # 相对坐标
    send("$1=255")      # 锁定电机
    
    # 临时设置参数，方便测试圈数
    send("$100=100")    # 每单位100步
    send("$120=50")     # 加速度设低一点(50)，因为3.6Nm电机惯性大，防止换向时急停抖动

    # --- 运动开始 ---
    print(">>> 动作1：正向旋转 2 圈 (CW)")
    send("G0 X64 F600") 
    time.sleep(1)       # 停顿1秒观察

    print(">>> 动作2：反向旋转 2 圈 (CCW)")
    send("G0 X-64 F600")

    time.sleep(1)       # 停顿1秒观察

    print(">>> 动作1：正向旋转 2 圈 (CW)")
    send("G0 X64 F600") 
    time.sleep(1)       # 停顿1秒观察

    print(">>> 动作2：反向旋转 2 圈 (CCW)")
    send("G0 X-64 F600")


    print("测试完成！电机应回到初始标记位置。")
    ser.close()

except Exception as e:
    print(f"运行出错: {e}")