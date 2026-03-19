import cv2
import time

def test_camera(cam_index=0):
    # 初始化摄像头
    cap = cv2.VideoCapture(cam_index)
    
    # 设置分辨率（建议不要太高，以保证实时性）
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("错误：无法打开摄像头，请检查索引号或连接线。")
        return

    print("摄像头已启动。按下 'q' 键退出程序。")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("未能接收到画面，正在重试...")
            break

        # 获取画面中心坐标
        height, width = frame.shape[:2]
        center_x, center_y = width // 2, height // 2

        # --- 视觉辅助线 (模拟你的标线跟踪基准) ---
        # 绘制画面中心垂直线（代表你 X 轴的 0 位）
        cv2.line(frame, (center_x, 0), (center_x, height), (0, 255, 0), 1)
        # 绘制水平线
        cv2.line(frame, (0, center_y), (width, center_y), (0, 255, 0), 1)
        
        # 在画面上显示帧率
        fps = cap.get(cv2.CAP_PROP_FPS)
        cv2.putText(frame, f"FPS: {int(fps)}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # 显示画面
        cv2.imshow('划线车视觉调试窗口', frame)

        # 按 'q' 退出
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    # 如果电脑自带摄像头，外接摄像头索引通常是 1
    test_camera(cam_index=0)