import torch
import time

def test_cuda_environment():
    print("="*30)
    print("      深度学习环境检测")
    print("="*30)

    # 1. PyTorch & CUDA 基础检查
    print(f"PyTorch 版本: {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    print(f"CUDA 是否可用: {cuda_available}")

    if not cuda_available:
        print("\n[!] 警告: CUDA 不可用，程序将运行在 CPU 上。")
        return

    # 2. 版本信息
    print(f"CUDA 运行时版本: {torch.version.cuda}")
    print(f"cuDNN 是否可用: {torch.backends.cudnn.enabled}")
    print(f"cuDNN 版本: {torch.backends.cudnn.version()}")
    
    # 3. 显卡硬件信息
    device_count = torch.cuda.device_count()
    print(f"检测到 GPU 数量: {device_count}")
    for i in range(device_count):
        print(f"  - GPU {i}: {torch.cuda.get_device_name(i)}")
        print(f"    硬件算力 (Capability): {torch.cuda.get_device_capability(i)}")

    # 4. 性能实测（矩阵乘法）
    print("\n" + "-"*30)
    print("正在进行 GPU 加速实测...")
    
    # 创建两个大矩阵（模拟高负载运算）
    size = 5000
    a = torch.randn(size, size).to('cuda')
    b = torch.randn(size, size).to('cuda')

    # 预热 GPU
    _ = torch.matmul(a, b)
    torch.cuda.synchronize()

    # 正式测试
    start_time = time.time()
    for _ in range(10):
        c = torch.matmul(a, b)
    torch.cuda.synchronize()  # 等待 GPU 计算完成
    end_time = time.time()

    print(f"测试完成！5000x5000 矩阵乘法 (10次循环) 耗时: {end_time - start_time:.4f} 秒")
    print("-"*30)
    print("恭喜！你的环境已准备就绪。")

if __name__ == "__main__":
    test_cuda_environment()