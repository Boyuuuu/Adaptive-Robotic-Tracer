# CalibrationController.py
# 电机运动标定控制器
# 触发条件：AppConfig.CONTROL_MODE = 'Motor_Motion_Calibration'
#
# 【设计说明】
#   标定是一次性顺序交互流程，不适合放在按帧触发的 control_logic() 中。
#   因此本类重写了 run()，将基类的帧循环替换为标定步骤序列。
#   control_logic() 保留为空实现（不会被调用）。
#
# 【标定总流程】
#   启动
#    ├─ 安全提示（滑块靠近电机侧）
#    ├─ 写入 $100 理论步数/mm
#    ├─ [询问] 跳过距离标定? y=跳过 / n=执行
#    │    └─ 正向+反向距离标定 → 计算并写入 $100 实际值
#    └─ [询问] 跳过加速度标定? y=跳过 / n=执行
#         └─ 循环：写入 $120 → 来回运动 N 次 → 用户判断 → 调整或确认

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Root'))
from AppConfig import Config

from ControlMode.BaseController import BaseControlThread


class CalibrationController(BaseControlThread):

    # ══════════════════════════════════════════════════════════
    # 主流程 run()
    # ══════════════════════════════════════════════════════════

    def run(self):
        print(f"\n[{self.name}] 电机标定程序启动")

        if not self.ser or not self.ser.is_open:
            print(f"[{self.name}] ❌ 串口未连接，标定中止。")
            self._cleanup()
            return

        self._print_config_summary()

        # ── 安全提示（共用）────────────────────────────────────
        print("\n" + "=" * 60)
        print("⚠️  安全提示")
        print("   请确认滑块已手动移动至【靠近电机一侧】的极限位置！")
        print("   确认完成后，输入 y 并按 Enter 继续...")
        print("=" * 60)
        if not self._wait_confirm():
            print(f"[{self.name}] 用户取消，标定退出。")
            self._cleanup()
            return

        # ── 写入理论 $100 作为基准 ────────────────────────────
        self._write_grbl_param("$100", Config.Motor_THEORETICAL_STEPS_PER_MM,
                               desc="理论步数/mm（距离标定基准）")

        # ══════════════════════════════════════════════════════
        # 阶段一：距离标定（可跳过）
        # ══════════════════════════════════════════════════════
        print("\n" + "─" * 60)
        print("【阶段一】电机距离标定")
        print("  是否执行距离标定？（y=执行 / n=跳过）")
        if self._wait_confirm():
            fwd_ratio = self._run_single_calibration("正向标定", step_direction=+1)
            rev_ratio = self._run_single_calibration("反向标定", step_direction=-1)
            suggested_steps = self._print_distance_summary(fwd_ratio, rev_ratio)
            if suggested_steps is not None:
                self._apply_grbl_steps_per_mm(suggested_steps)
        else:
            print("  已跳过距离标定。")

        # ══════════════════════════════════════════════════════
        # 阶段二：加速度标定（可跳过）
        # ══════════════════════════════════════════════════════
        print("\n" + "─" * 60)
        print("【阶段二】加速度标定（$120）")
        print("  是否执行加速度标定？（y=执行 / n=跳过）")
        if self._wait_confirm():
            self._run_acceleration_calibration()
        else:
            print("  已跳过加速度标定。")

        print(f"\n[{self.name}] 所有标定已完成，程序退出。")
        self._cleanup()

    # ══════════════════════════════════════════════════════════
    # 阶段一：距离标定
    # ══════════════════════════════════════════════════════════

    def _run_single_calibration(self, phase_name: str, step_direction: int) -> float | None:
        """单方向距离标定，返回 实测/指令 比值，失败返回 None。"""
        travel_mm = Config.CALIBRATION_TRAVEL_MM
        step_mm   = Config.CALIBRATION_STEP_MM * step_direction
        direction_label = "正向" if step_direction > 0 else "反向"

        print(f"\n{'─' * 60}")
        print(f"【{phase_name}】开始")

        # 步骤 1：建立零点
        print(f"\n步骤 1：电机{direction_label}前进 {abs(step_mm):.1f}mm，建立零点...")
        if not self.move_motor(step_mm):
            print(f"  ❌ 建立零点失败，跳过本阶段。")
            return None
        print(f"  ✓ 零点已建立。")

        # 步骤 2：等待确认
        print(f"\n步骤 2：确认滑块已稳定，输入 y 继续...")
        if not self._wait_confirm():
            return None

        # 步骤 3：行驶标定行程
        print(f"\n步骤 3：电机{direction_label}行驶 {travel_mm:.1f}mm（指令值）...")
        if not self.move_motor(travel_mm * step_direction):
            print(f"  ❌ 行驶指令失败，跳过本阶段。")
            return None
        print(f"  ✓ 行驶完成。")

        # 步骤 4：用户输入实测距离
        print(f"\n步骤 4：请用卡尺/钢尺测量滑块实际移动距离（mm）：")
        actual_mm = self._input_float("  实测距离 (mm): ")
        if actual_mm is None:
            print(f"  输入无效，跳过本阶段。")
            return None

        ratio = actual_mm / travel_mm
        print(f"\n  ✓ {phase_name}结果：")
        print(f"     指令距离 = {travel_mm:.2f} mm")
        print(f"     实测距离 = {actual_mm:.2f} mm")
        print(f"     误差比   = {ratio:.5f}  （{(ratio-1)*100:+.2f}%）")
        return ratio

    def _print_distance_summary(self, fwd_ratio, rev_ratio) -> float | None:
        print(f"\n{'=' * 60}")
        print("【距离标定结果汇总】")

        ratios = [r for r in [fwd_ratio, rev_ratio] if r is not None]
        if not ratios:
            print("  ⚠️  无有效数据。")
            return None

        avg_ratio = sum(ratios) / len(ratios)
        if fwd_ratio is not None:
            print(f"  正向误差比: {fwd_ratio:.5f}  ({(fwd_ratio-1)*100:+.2f}%)")
        else:
            print(f"  正向误差比: 未完成")
        if rev_ratio is not None:
            print(f"  反向误差比: {rev_ratio:.5f}  ({(rev_ratio-1)*100:+.2f}%)")
        else:
            print(f"  反向误差比: 未完成")

        theoretical   = Config.Motor_THEORETICAL_STEPS_PER_MM
        current       = Config.Motor_ACTUAL_STEPS_PER_MM
        suggested     = theoretical / avg_ratio

        print(f"\n  平均误差比       : {avg_ratio:.5f}  ({(avg_ratio-1)*100:+.2f}%)")
        print(f"  理论步数/mm      : {theoretical:.5f}")
        print(f"  当前实际步数/mm  : {current:.5f}")
        print(f"  建议实际步数/mm  : {suggested:.5f}")
        print(f"\n  AppConfig.py 建议修改：Motor_ACTUAL_STEPS_PER_MM = {suggested:.5f}")
        print("=" * 60)
        return suggested

    def _apply_grbl_steps_per_mm(self, steps_per_mm: float):
        print(f"\n是否将 $100={steps_per_mm:.5f} 写入 GRBL？（y=写入 / n=跳过）")
        if not self._wait_confirm():
            print(f"  已跳过，手动发送：$100={steps_per_mm:.5f}")
            return
        ok = self._write_grbl_param("$100", steps_per_mm, desc="实际步数/mm")
        if ok:
            print(f"  请同步更新 AppConfig.py：Motor_ACTUAL_STEPS_PER_MM = {steps_per_mm:.5f}")

    # ══════════════════════════════════════════════════════════
    # 阶段二：加速度标定
    # ══════════════════════════════════════════════════════════

    def _run_acceleration_calibration(self):
        """
        加速度标定流程：
          1. 写入初始加速度 $120 = GRBL_ACCELERATION
          2. 循环：来回运动 ACCEL_CALIB_REPEAT 次
          3. 用户判断是否平滑
             - 不平滑 → 用户输入新 $120 → 写入 → 重复测试
             - 平滑   → 询问是否确认当前值，或输入最终值写入
        """
        travel_mm     = Config.ACCEL_CALIB_TRAVEL_MM
        repeats       = Config.ACCEL_CALIB_REPEAT
        calib_feed    = Config.ACCEL_CALIB_FEED_RATE   # 标定专用高速（G1）
        calib_max     = Config.ACCEL_CALIB_MAX_RATE    # 标定期间临时 $110
        biz_max       = Config.BUSINESS_MAX_RATE       # 标定完成后恢复的 $110
        business_feed = Config.FEED_RATE               # 业务控制器速度（仅提示）
        current_accel = Config.GRBL_ACCELERATION

        print(f"\n{'─' * 60}")
        print(f"【加速度标定】开始")
        print(f"  标定专用速度  : {calib_feed} mm/min（G1）")
        print(f"  标定 $110 上限: {calib_max} mm/min → 标定期间临时写入")
        print(f"  业务 $110 上限: {biz_max} mm/min → 标定完成后恢复")
        print(f"  来回行程      : ±{travel_mm:.0f}mm × {repeats} 次")
        print(f"  初始加速度 $120 = {current_accel} mm/s²")

        # 写入初始加速度，并临时解除 $110 速度上限
        self._write_grbl_param("$120", current_accel, desc="初始加速度")
        self._write_grbl_param("$110", calib_max,     desc="标定临时最大速率")

        # 查询 GRBL 当前设置，确认 $110/$120 是否生效
        print(f"\n  [诊断] 查询 GRBL 当前设置（$$）...")
        if self.ser and self.ser.is_open:
            self.ser.reset_input_buffer()
            self.ser.write(b"$$\n")
            import time
            time.sleep(0.5)
            lines = []
            while self.ser.in_waiting:
                line = self.ser.readline().decode(errors='ignore').strip()
                if line:
                    lines.append(line)
            # 只打印与速度/加速度相关的行
            for ln in lines:
                if any(k in ln for k in ['$110', '$111', '$112', '$120', '$121', '$122']):
                    print(f"    {ln}")
            if not lines:
                print("  [诊断] 未收到 GRBL 响应，请检查串口。")


        while True:
            # ── 来回运动 ────────────────────────────────────────
            print(f"\n  开始来回运动（共 {repeats} 次，请观察运动是否平滑）...")
            success = True
            for i in range(repeats):
                print(f"  第 {i+1}/{repeats} 次 → 前进 {travel_mm:.0f}mm...", end=" ", flush=True)
                if not self._move_g1(travel_mm, calib_feed):
                    print("❌ 失败")
                    success = False
                    break
                print(f"返回 {travel_mm:.0f}mm...", end=" ", flush=True)
                if not self._move_g1(-travel_mm, calib_feed):
                    print("❌ 失败")
                    success = False
                    break
                print("✓")

            if not success:
                print("  ⚠️  运动指令失败，退出加速度标定。")
                self._write_grbl_param("$110", biz_max, desc="恢复业务最大速率")
                return

            # ── 用户判断 ────────────────────────────────────────
            print(f"\n  当前 $120 = {current_accel} mm/s²")
            print("  运动是否平滑？（y=平滑，可以继续 / n=需要调整）")

            if self._wait_confirm():
                # 平滑 → 询问是否确认当前值还是手动输入最终值
                print(f"\n  是否以当前 $120={current_accel} 作为最终值写入 GRBL？")
                print("  （y=确认当前值 / n=手动输入最终值）")
                if self._wait_confirm():
                    final_accel = current_accel
                else:
                    final_accel = self._input_float(f"  请输入最终 $120 值 (mm/s²): ")
                    if final_accel is None:
                        print("  输入无效，保持当前值。")
                        final_accel = current_accel

                self._write_grbl_param("$120", final_accel, desc="最终加速度")
                self._write_grbl_param("$110", biz_max,     desc="恢复业务最大速率")
                print(f"\n  ✓ 加速度标定完成！最终 $120 = {final_accel} mm/s²")
                print(f"  $110 已恢复为 {biz_max} mm/min，业务控制器无需额外操作。")
                print(f"  请同步更新 AppConfig.py：")
                print(f"    GRBL_ACCELERATION = {int(final_accel)}")
                return

            else:
                # 需要调整 → 用户输入新值
                new_accel = self._input_float(
                    f"  请输入新的 $120 值 (mm/s²，当前={current_accel}): "
                )
                if new_accel is None:
                    print("  输入无效，保持当前值，重新测试。")
                else:
                    current_accel = new_accel
                    self._write_grbl_param("$120", current_accel, desc="新加速度")

    # ══════════════════════════════════════════════════════════
    # 公共工具方法
    # ══════════════════════════════════════════════════════════

    def _move_g1(self, distance_mm: float, feed_rate: float) -> bool:
        """
        以 G1（线性插补）指定速度移动，阔平 move_motor（使用 G0 忽略 F）的局限。
        仅用于加速度标定过程。
        """
        if not self.ser or not self.ser.is_open:
            print(f"[{self.name}] 错误：串口未连接")
            return False
        cmd = f"G1 X{distance_mm:.2f} F{feed_rate:.0f}"
        return self._send_gcode_and_wait(cmd)

    def _write_grbl_param(self, param: str, value: float, desc: str = "") -> bool:
        """向 GRBL 写入参数并等待 ok，返回是否成功。"""
        cmd = f"{param}={value:.5f}" if isinstance(value, float) else f"{param}={value}"
        label = f"（{desc}）" if desc else ""
        print(f"  写入 {cmd} {label}...", end=" ", flush=True)
        ok = self._send_gcode_and_wait(cmd)
        print("✓" if ok else "❌ 失败")
        return ok

    def _wait_confirm(self) -> bool:
        """等待用户输入 y/Y，其他输入视为取消。"""
        try:
            ans = input("  输入 [y] 确认 / 其他任意键取消: ").strip().lower()
            return ans == 'y'
        except (EOFError, KeyboardInterrupt):
            return False

    def _input_float(self, prompt: str) -> float | None:
        """提示输入正浮点数，失败返回 None。"""
        try:
            val = float(input(prompt).strip())
            if val <= 0:
                print("  ⚠️  输入值必须大于 0。")
                return None
            return val
        except (ValueError, EOFError, KeyboardInterrupt):
            print("  ⚠️  输入无效。")
            return None

    def _print_config_summary(self):
        print("=" * 60)
        print(f"[{self.name}] 标定参数摘要")
        print(f"  步进角              : {Config.Motor_Step_Angle}°")
        print(f"  驱动器细分          : {Config.Motor_Driver_Fine}  ({Config.Motor_Step_Per_Rotation}步/转 × {Config.Motor_Driver_Fine} = {Config.Motor_Step_Per_Rotation * Config.Motor_Driver_Fine}步/转)")
        print(f"  机械导程            : {Config.Motor_Mechanical_Pitch} mm/转")
        print(f"  理论步数/mm         : {Config.Motor_THEORETICAL_STEPS_PER_MM:.4f}")
        print(f"  实际步数/mm         : {Config.Motor_ACTUAL_STEPS_PER_MM:.4f}")
        print(f"  初始加速度 $120     : {Config.GRBL_ACCELERATION} mm/s²")
        print(f"  距离标定行程        : {Config.CALIBRATION_TRAVEL_MM:.0f} mm")
        print(f"  加速度标定行程      : {Config.ACCEL_CALIB_TRAVEL_MM:.0f} mm × {Config.ACCEL_CALIB_REPEAT} 次")
        print("=" * 60)

    # ══════════════════════════════════════════════════════════
    # control_logic（不会被调用，保留以满足基类接口）
    # ══════════════════════════════════════════════════════════

    def control_logic(self, vision_data: dict):
        """标定模式不使用帧循环，此方法不会被调用。"""
        pass
