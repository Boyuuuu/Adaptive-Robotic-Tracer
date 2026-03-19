import serial
import time

# 确保 COM 口是你设备管理器里的那个
port = 'COM8' 
baudrate = 115200

try:
    ser = serial.Serial(port, baudrate, timeout=1)
    time.sleep(2) # 等待 ESP32 重启

    def send(cmd):
        print(f"发送指令: {cmd}")
        ser.write((cmd + '\n').encode())
        while True:
            res = ser.readline().decode().strip()
            if res == 'ok':
                break
            if 'error' in res.lower():
                print(f"!!! 收到错误反馈: {res}")
                break

    # --- 初始化序列 ---
    send("$X")          # 强制解锁 (Kill Alarm Lock)    send("G21")         # 设置单位为毫米 (Millimeters)
    send("G91")         # 设置为相对坐标 (Relative Mode)
    
    # 设置电机保持电流 (255代表永不释放，调试时非常有用，可以防止杜邦线接触不良导致的丢步)
    send("$1=255") 

    # --- 运动指令 ---
    print("准备开始旋转...")
    # G0 是快速移动，X10 代表移动 10mm，F600 代表速度 600mm/min
    send("G0 X30 F600") 
    
    time.sleep(2) # 停顿2秒
    
    # 往回转
    send("G0 X-30 F600")

    print("运动结束！")
    ser.close()

except Exception as e:
    print(f"连接失败: {e}")