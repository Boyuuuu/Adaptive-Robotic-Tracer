import serial
import time

# 这里的 'COM3' 请替换为你设备管理器中显示的实际编号
port = 'COM9' 
baudrate = 115200

try:
    # 初始化串口
    ser = serial.Serial(port, baudrate, timeout=1)
    
    # ESP32 串口打开后通常会触发重启，建议等待 2 秒让固件初始化
    time.sleep(2)
    
    # 清空输入缓冲区
    ser.reset_input_buffer()

    # 发送一个回车符，激活 GRBL 状态回传
    ser.write(b"\n\n")
    time.sleep(0.5)

    # 发送 '$' 指令获取当前所有参数配置
    print(f"--- 正在向 {port} 发送读取配置指令 ---")
    ser.write(b"$$\n")

    # 读取返回内容
    while True:
        line = ser.readline().decode('utf-8').strip()
        if not line:
            break
        print(f"收到: {line}")

    ser.close()
    print("--- 测试结束 ---")

except Exception as e:
    print(f"发生错误: {e}")