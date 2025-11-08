import os
from skyfield.api import load

# 将路径替换为你的 de440s.bsp 文件的真实路径
file_path = "de440s.bsp"

# 检查路径是否正确
print(f"检查路径: {file_path}")
print(f"文件是否存在: {os.path.isfile(file_path)}")
if os.path.isfile(file_path):
    print(f"文件大小: {os.path.getsize(file_path)} 字节") # 文件大小可能超过100MB

# 尝试加载
try:
    print("正在尝试加载...")
    planets = load(file_path)
    print("✅ 星历文件加载成功！")
except Exception as e:
    print(f"❌ 加载失败: {e}")