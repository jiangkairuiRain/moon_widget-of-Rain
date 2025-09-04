# moon_widget

### a widget on desktop to show information about the moon

<br>

- 1.PS:请提前安装好python和以下库（记得把python加入path）:

        pip install pywebview pytz requests pywin32 geoip2 skyfield -i https://pypi.tuna.tsinghua.edu.cn/simple

<br>

- 2.将start_moon_widget.bat文件先重命名为start_moon_widget.txt，用记事本打开，全选并复制所有内容，点击"文件"新建标签页，将内容粘贴到新标签页中，点击"文件"->"另存为"，在"保存"对话框中，确保"编码"选择为UTF-8，以start_moon_widget.txt命名，点击"保存"，覆盖原文件，最后将start_moon_widget.txt重新改为start_moon_widget.bat（把LF格式改为CRLF格式）

<br>

- 3.运行一遍start_moon_widget.bat，若弹出安全警告，则不要勾选"打开此文件前总是询问"，点击"运行"（防止每次打开都进行询问）

<br>

- 4.Win+R，对话框中输入shell:startup打开文件夹，将start_moon_widget.bat的快捷方式放入此文件夹（实现开机自启功能）

<br>

- 5.在桌面上右键，选择"新建" -> "快捷方式"。在位置字段中输入：

	    pythonw.exe "完整路径\moon_widget.py"

    将"完整路径"替换为真实文件路径，上述的双引号""，在输入路径时，不要删去（实现创建快捷方式功能）

<br>

- 6.把2、3中创建的快捷方式，"右键"->"属性"->"快捷方式"->"更改图标"->"浏览"，选择文件夹中的moon.ico，点击"确定"->"应用"->"确定"（更改图标）