# moon_widget

### a widget on desktop to show information about the moon

<br>

- 1.PS:请提前安装好python和以下库（记得把python加入path）:

        pip install webview pytz requests pywin32 geoip2 -i https://pypi.tuna.tsinghua.edu.cn/simple

<br>

- 2.Win+R，对话框中输入shell:startup打开文件夹，将start_moon_widget.bat的快捷方式放入此文件夹（实现开机自启功能）

<br>

- 3.在桌面上右键，选择"新建" -> "快捷方式"。在位置字段中输入：

	    pythonw.exe "完整路径\moon_widget.py"

    （将"完整路径"替换为真实文件路径）（实现创建快捷方式功能）

<br>

- 4.把2、3中创建的快捷方式，"右键"->"属性"->"快捷方式"->"更改图标"->"浏览"，选择文件夹中的moon.ico（更改图标）