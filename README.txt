1.PS:请提前安装好python和以下库：

pip install webview pytz requests pywin32 geoip2 -i https://pypi.tuna.tsinghua.edu.cn/simple

2.Win+R，对话框中输入shell:startup打开文件夹，将start_moon_widget.bat的快捷方式放入（实现开机自启功能）

3.在桌面上右键，选择"新建" -> "快捷方式"。在位置字段中输入：

	pythonw.exe "完整路径\moon_widget\moon_widget.py"

（将"完整路径"替换为真实文件路径）（实现创建快捷方式功能）