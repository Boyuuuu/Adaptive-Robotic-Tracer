"""
set_grbl_status.py
一次性脚本：向 GRBL 发送 $10=3，开启状态报告中的 Bf:（规划器缓冲区）字段。
运行成功后可以删除此文件。
"""

import serial
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Root'))
from AppConfig import Config

PORT      = Config.SERIAL_PORT
BAUD_RATE = Config.BAUD_RATE

print(f"正在连接 {PORT}（波特率 {BAUD_RATE}）...")

try:
    ser = serial.Serial(PORT, BAUD_RATE, timeout=2)
except serial.SerialException as e:
    print(f"❌ 串口连接失败: {e}")
    sys.exit(1)

# 等待 GRBL 启动完成
time.sleep(2)
ser.flushInput()
print("✅ 串口已连接，GRBL 已就绪\n")

# ── 第一步：发送 $10=3（开启 MPos + Bf 字段）────────────────
CMD = "$10=3"
print(f"发送: {CMD}")
ser.write(f"{CMD}\n".encode())

# 读取 GRBL 响应
deadline = time.time() + 3.0
while time.time() < deadline:
    raw = ser.readline()
    line = raw.decode('utf-8', errors='ignore').strip()
    if not line:
        continue
    print(f"  GRBL 响应: {line}")
    if line == 'ok':
        print(f"\n✅ {CMD} 写入成功！")
        break
    elif line.startswith('error'):
        print(f"\n❌ GRBL 拒绝指令: {line}")
        ser.close()
        sys.exit(1)

# ── 第二步：发送 ? 验证 Bf: 字段出现 ───────────────────────
print("\n发送 '?' 验证 Bf: 字段...")
time.sleep(0.1)
ser.write(b'?')

deadline = time.time() + 2.0
while time.time() < deadline:
    raw = ser.readline()
    line = raw.decode('utf-8', errors='ignore').strip()
    if not line:
        continue
    print(f"  状态响应: {line}")
    if line.startswith('<'):
        if 'Bf:' in line:
            print("\n✅ 验证成功！Bf: 字段已出现，缓冲区监控已启用。")
        else:
            print("\n⚠️  状态行中未找到 Bf: 字段，请检查 GRBL 固件版本（需要 v1.1）。")
        break

ser.close()
print("\n串口已关闭，脚本完成。")
