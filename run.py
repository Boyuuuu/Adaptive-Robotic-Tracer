import sys
import os

# 获取当前脚本所在目录（e:\1111AdaptiveSlidingTable\Code）
_project_root = os.path.dirname(os.path.abspath(__file__))
# 将 Root 目录加入 sys.path，以便 main.py 中的相对导入能对应
_root_dir = os.path.join(_project_root, "Root")
sys.path.insert(0, _root_dir)

# 导入并运行主程序
if __name__ == "__main__":
    from main import main
    main()
