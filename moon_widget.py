import webview
import threading
import time
import json
import math
from datetime import datetime, timedelta, timezone
import pytz
import sys
import os
import socket
import requests
import geoip2.database
from urllib.request import urlopen

# 全局变量
SKYFIELD_AVAILABLE = False
ts = None
eph = None
sun = None
moon = None
earth = None
HIDE_CONSOLE = False  # 新增：控制是否隐藏控制台窗口的全局变量

def hide_console_window():
    """隐藏控制台窗口"""
    if HIDE_CONSOLE and sys.platform == 'win32':
        try:
            import win32gui
            import win32con
            # 获取控制台窗口句柄
            console_window = win32gui.GetForegroundWindow()
            # 隐藏控制台窗口
            win32gui.ShowWindow(console_window, win32con.SW_HIDE)
            print("控制台窗口已隐藏")
        except Exception as e:
            print(f"隐藏控制台窗口失败: {e}")

class MoonWidget:
    def __init__(self):
        self.window = None
        self.update_interval = 1  # 更新间隔改为1秒
        self.is_running = True
        self.location = self.get_location()  # 获取位置信息
        self.moon_events = {}  # 存储月出月落时间
        self.local_tz = pytz.timezone(self.location["timezone"])  # 使用IP所在地的时区
        self.last_update_second = -1  # 记录上一次更新的秒数
        self.is_topmost = False  # 初始状态为不置顶

        # 添加时间戳记录
        self.last_ip_update = 0  # 上次IP更新时间
        self.last_moon_events_update = 0  # 上次月出月落更新时间
        self.last_location = self.location.copy()  # 保存上次位置信息用于比较
        
        # 添加网络状态和位置记忆功能
        self.network_available = True  # 默认网络可用
        self.last_known_location = self.load_last_known_location()  # 加载上次已知位置
        
        # 初始化Skyfield
        self.init_skyfield_async()

        self.eclipse_events = []  # 存储日月食事件
        self.last_eclipse_update = 0  # 上次日月食更新时间
        
        # 添加日月食类型映射
        self.eclipse_types = {
            0: "日偏食",
            1: "日环食",
            2: "日全食",
            3: "月偏食",
            4: "月全食"
        }
        
        # 添加Skyfield初始化状态
        self.skyfield_error = None
        
    def calculate_eclipses(self):
        """计算未来7天内的日月食事件"""
        try:
            global SKYFIELD_AVAILABLE, ts, eph
            
            if not SKYFIELD_AVAILABLE:
                print("Skyfield不可用，无法计算日月食")
                self.eclipse_events = []
                return
                
            # 检查星历数据是否可用
            if not self.verify_and_reload_ephemeris():
                print("星历数据不可用，无法计算日月食")
                self.eclipse_events = []
                return
                
            # 获取当前时间（UTC）
            now_utc = datetime.now(timezone.utc)
            start_time = ts.utc(now_utc)
            end_time = ts.utc(now_utc + timedelta(days=7))  # 未来7天
            
            print(f"查找日月食事件的时间范围: {start_time.utc_datetime()} 到 {end_time.utc_datetime()}")
            
            # 查找日月食事件 - 使用正确的方法名
            from skyfield import almanac
            # 检查是否有eclipse_types方法
            if hasattr(almanac, 'eclipse_types'):
                t, y = almanac.find_discrete(start_time, end_time, almanac.eclipse_types(eph))
            else:
                print("当前Skyfield版本不支持eclipse_types方法")
                self.eclipse_events = []
                return
            
            print(f"找到 {len(t)} 个日月食事件")
            
            eclipse_list = []
            for i, (time_tt, eclipse_type) in enumerate(zip(t, y)):
                # 转换时间为本地时区
                eclipse_time_utc = time_tt.utc_datetime()
                eclipse_time_local = eclipse_time_utc.replace(tzinfo=timezone.utc).astimezone(self.local_tz)
                
                # 格式化事件信息
                eclipse_info = {
                    "time": eclipse_time_local.strftime("%m月%d日 %H:%M"),
                    "type": self.eclipse_types.get(eclipse_type, f"未知类型({eclipse_type})"),
                    "raw_type": int(eclipse_type)
                }
                
                eclipse_list.append(eclipse_info)
                print(f"日月食事件: {eclipse_info['time']} - {eclipse_info['type']}")
            
            self.eclipse_events = eclipse_list
            
        except Exception as e:
            print(f"计算日月食事件错误: {e}")
            import traceback
            traceback.print_exc()
            self.eclipse_events = []

    def set_topmost(self, topmost):
        """设置窗口置顶状态"""
        try:
            if sys.platform == 'win32':
                import win32gui
                import win32con
                
                # 如果窗口句柄可用，直接使用
                if hasattr(self.window, 'hwnd') and self.window.hwnd:
                    hwnd = self.window.hwnd
                else:
                    # 否则通过窗口标题查找
                    def find_window(hwnd, extra):
                        if win32gui.GetWindowText(hwnd) == "月球位置":
                            extra.append(hwnd)
                        return True
                    
                    windows = []
                    win32gui.EnumWindows(find_window, windows)
                    
                    if windows:
                        hwnd = windows[0]
                        # 保存句柄以便下次使用
                        if not hasattr(self.window, 'hwnd'):
                            self.window.hwnd = hwnd
                
                if hwnd:
                    # 设置窗口置顶属性
                    win32gui.SetWindowPos(
                        hwnd,
                        win32con.HWND_TOPMOST if topmost else win32con.HWND_NOTOPMOST,
                        0, 0, 0, 0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                    )
                    print(f"窗口置顶状态已设置为: {'置顶' if topmost else '取消置顶'}")
                    self.is_topmost = topmost
                    return True
        except Exception as e:
            print(f"设置窗口置顶状态失败: {e}")
        
        return False

    def load_last_known_location(self):
        """加载上次已知的位置信息"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'moon_widget_config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if 'last_known_location' in config:
                        print("加载上次已知位置信息")
                        return config['last_known_location']
        except Exception as e:
            print(f"加载上次已知位置失败: {e}")
        return None
        
    def save_last_known_location(self):
        """保存当前已知的位置信息"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'moon_widget_config.json')
            config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            # 确保self.location存在
            if hasattr(self, 'location') and self.location:
                config['last_known_location'] = self.location
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                
            print("保存位置信息到配置文件")
        except Exception as e:
            print(f"保存位置信息失败: {e}")
    
    def init_skyfield_async(self):
        """在后台线程中初始化Skyfield"""
        def init_skyfield():
            global SKYFIELD_AVAILABLE, ts, eph, sun, moon, earth
            try:
                from skyfield.api import load, wgs84
                from skyfield import almanac
                
                # 指定本地星历表文件路径
                de421_path = os.path.join(os.path.dirname(__file__), 'de421.bsp')
                if os.path.exists(de421_path):
                    print("从本地加载星历数据...")
                    ts = load.timescale()
                    eph = load(de421_path)
                else:
                    print("从网络加载星历数据，请耐心等待...")
                    ts = load.timescale()
                    eph = load('de421.bsp')
                
                sun, moon, earth = eph['sun'], eph['moon'], eph['earth']
                SKYFIELD_AVAILABLE = True
                print("Skyfield初始化完成")
                
                # 通知主线程初始化完成
                if self.window:
                    try:
                        self.window.evaluate_js("document.getElementById('loading-status').textContent = 'Skyfield初始化完成';")
                    except:
                        pass
                    
            except ImportError:
                SKYFIELD_AVAILABLE = False
                self.skyfield_error = "skyfield库未安装，无法计算精确数据"
                print("skyfield库未安装，无法计算精确数据")
                print("要获得精确结果，请安装: pip install skyfield")
            except Exception as e:
                SKYFIELD_AVAILABLE = False
                self.skyfield_error = f"加载skyfield时出错: {e}"
                print(f"加载skyfield时出错: {e}")
        
        # 在后台线程中初始化Skyfield
        skyfield_thread = threading.Thread(target=init_skyfield)
        skyfield_thread.daemon = True
        skyfield_thread.start()
        
    def verify_and_reload_ephemeris(self):
        """验证星历数据并必要时重新加载"""
        global SKYFIELD_AVAILABLE, ts, eph, sun, moon, earth
        
        try:
            # 检查星历数据是否有效
            if eph is None:
                raise Exception("星历数据未初始化")
                
            # 尝试使用星历数据进行简单计算
            from skyfield.api import load
            test_ts = load.timescale()
            test_time = test_ts.utc(datetime.now(timezone.utc))  # 修复：使用有时区的时间
            
            # 尝试计算月球位置
            astrometric = eph['earth'].at(test_time).observe(eph['moon'])
            apparent = astrometric.apparent()
            
            # 如果计算成功，星历数据有效
            print("星历数据验证成功")
            return True
            
        except Exception as e:
            print(f"星历数据验证失败: {e}")
            print("尝试重新加载星历数据...")
            
            try:
                # 尝试重新加载星历数据
                de421_path = os.path.join(os.path.dirname(__file__), 'de421.bsp')
                if os.path.exists(de421_path):
                    ts = load.timescale()
                    eph = load(de421_path)
                else:
                    ts = load.timescale()
                    eph = load('de421.bsp')
                    
                sun, moon, earth = eph['sun'], eph['moon'], eph['earth']
                SKYFIELD_AVAILABLE = True
                print("星历数据重新加载成功")
                return True
            except Exception as reload_error:
                print(f"星历数据重新加载失败: {reload_error}")
                SKYFIELD_AVAILABLE = False
                return False
                
    def check_network_status(self):
        """检查网络连接状态"""
        try:
            # 尝试连接到一个可靠的网站
            urlopen('https://www.baidu.com', timeout=3)
            self.network_available = True
            return True
        except:
            self.network_available = False
            return False
            
    def get_public_ip(self):
        """获取本机公网IP地址"""
        try:
            # 检查网络状态
            if not self.check_network_status():
                print("网络不可用，使用上次已知位置")
                if self.last_known_location:
                    return self.last_known_location
                else:
                    return None
                    
            # 尝试通过多个服务获取IP，增加成功率
            services = [
                'https://api.ipify.org',
                'https://ident.me',
                'https://checkip.amazonaws.com'
            ]
            
            for service in services:
                try:
                    # 添加超时参数
                    ip = urlopen(service, timeout=3).read().decode('utf8').strip()
                    if ip and len(ip.split('.')) == 4:
                        return ip
                except Exception as e:
                    print(f"从 {service} 获取IP失败: {e}")
                    continue
                    
            return None
        except Exception as e:
            print(f"获取公网IP失败: {e}")
            return None
    
    def get_location_from_ip(self, ip_address):
        """通过IP地址获取地理位置信息"""
        try:
            # 方法1: 使用geoip2离线数据库
            try:
                # 数据库文件路径 - 需要用户自行下载或提供
                db_path = os.path.join(os.path.dirname(__file__), 'GeoLite2-City.mmdb')
                if os.path.exists(db_path):
                    with geoip2.database.Reader(db_path) as reader:
                        response = reader.city(ip_address)
                        location_data = {
                            'name': f"{response.city.name if response.city.name else '未知'}, {response.country.name if response.country.name else '未知'}",
                            'latitude': response.location.latitude,
                            'longitude': response.location.longitude,
                            'timezone': response.location.time_zone if response.location.time_zone else 'Asia/Shanghai'
                        }
                        # 保存为上次已知位置
                        self.last_known_location = location_data
                        self.save_last_known_location()
                        return location_data
            except Exception as e:
                print(f"使用geoip2数据库失败: {e}")
            
            # 方法2: 使用在线API (ipapi.co)
            try:
                response = requests.get(f'https://ipapi.co/{ip_address}/json/', timeout=3)
                data = response.json()
                if 'error' not in data:
                    location_data = {
                        'name': f"{data.get('city', '未知')}, {data.get('country_name', '未知')}",
                        'latitude': data.get('latitude', 31.2304),
                        'longitude': data.get('longitude', 121.4737),
                        'timezone': data.get('timezone', 'Asia/Shanghai')
                    }
                    # 保存为上次已知位置
                    self.last_known_location = location_data
                    self.save_last_known_location()
                    return location_data
            except Exception as e:
                print(f"使用ipapi.co API失败: {e}")
                
            return None
        except Exception as e:
            print(f"通过IP获取位置失败: {e}")
            return None
    
    def get_location(self):
        """尝试获取位置信息，失败则使用默认位置（上海）"""
        try:
            # 获取公网IP
            public_ip = self.get_public_ip()
            if public_ip:
                print(f"检测到公网IP: {public_ip}")
                
                # 通过IP获取位置
                location = self.get_location_from_ip(public_ip)
                if location:
                    print(f"通过IP获取位置成功: {location['name']}")
                    return location
            
            # 如果通过IP获取失败，尝试使用上次已知位置
            if self.last_known_location:
                print(f"使用上次已知位置: {self.last_known_location['name']}")
                return self.last_known_location
                
            # 如果上次已知位置也不可用，使用默认位置（上海）
            print("使用默认位置: 上海")
            default_location = {
                "name": "上海",
                "latitude": 31.2304,
                "longitude": 121.4737,
                "timezone": "Asia/Shanghai"
            }
            # 保存默认位置为上次已知位置
            self.last_known_location = default_location
            self.save_last_known_location()
            return default_location
        except Exception as e:
            print(f"获取位置信息错误: {e}")
            # 尝试使用上次已知位置
            if self.last_known_location:
                print(f"发生错误，使用上次已知位置: {self.last_known_location['name']}")
                return self.last_known_location
            else:
                print("发生错误，使用默认位置: 上海")
                return {
                    "name": "上海",
                    "latitude": 31.2304,
                    "longitude": 121.4737,
                    "timezone": "Asia/Shanghai"
                }
    
    def update_location_periodically(self):
        """每10秒更新一次位置信息，如果位置变化则标记需要更新月出月落时间"""
        current_time = time.time()
        if current_time - self.last_ip_update >= 10:  # 10秒更新一次
            print("更新位置信息...")
            new_location = self.get_location()
            if new_location:
                # 检查位置是否发生变化
                location_changed = (
                    abs(new_location["latitude"] - self.location["latitude"]) > 0.01 or 
                    abs(new_location["longitude"] - self.location["longitude"]) > 0.01 or
                    new_location["timezone"] != self.location["timezone"]
                )
                
                if location_changed:
                    print(f"位置已更新: {new_location['name']}")
                    self.location = new_location
                    self.local_tz = pytz.timezone(self.location["timezone"])
                    # 位置变化时需要重新计算月出月落
                    self.last_moon_events_update = 0  # 强制下次更新月出月落
                    self.last_location = self.location.copy()  # 更新上次位置信息
            self.last_ip_update = current_time
    
    def calculate_moon_events_with_skyfield(self):
        """使用skyfield库精确计算月出月落时间"""
        try:
            global SKYFIELD_AVAILABLE, ts, eph, moon, earth
            
            if not SKYFIELD_AVAILABLE:
                raise ImportError("skyfield库不可用")
                
            print(f"位置信息: 纬度={self.location['latitude']}, 经度={self.location['longitude']}, 时区={self.location['timezone']}")
            
            # 检查星历数据是否加载成功
            if eph is None:
                raise Exception("星历数据未加载")
                
            # 创建观察者位置
            from skyfield.api import wgs84
            observer = wgs84.latlon(self.location["latitude"], self.location["longitude"])
            
            # 获取当前时间（UTC）- 修复：使用有时区的时间
            now_utc = datetime.now(timezone.utc)
            t0 = ts.utc(now_utc)
            
            # 计算未来72小时内的月出月落事件（增加时间范围）
            t1 = ts.utc(now_utc + timedelta(hours=72))
            
            print(f"查找月出月落事件的时间范围: {t0.utc_datetime()} 到 {t1.utc_datetime()}")
            
            # 查找月出月落事件
            from skyfield import almanac
            f = almanac.risings_and_settings(eph, moon, observer)
            times, events = almanac.find_discrete(t0, t1, f)
            
            print(f"找到 {len(times)} 个事件")
            
            # 检查是否找到事件
            if len(times) == 0:
                print("警告: 未找到月出月落事件，可能处于极地地区或计算时间范围不足")
                self.moon_events = {
                    "moonrise": "--:--",
                    "moonset": "--:--",
                    "first_event": "月出",
                    "first_time": "未找到",
                    "second_event": "月落",
                    "second_time": "未找到",
                    "moonrise_dt": None,
                    "moonset_dt": None
                }
                return
                
            # 提取月出和月落时间
            moonrise_times = []
            moonset_times = []
            
            for i, (time, event) in enumerate(zip(times, events)):
                # event: 1表示升起（月出），0表示落下（月落）
                if event == 1:  # 月出
                    moonrise_times.append(time.utc_datetime())
                    print(f"事件 {i}: 月出 at {time.utc_datetime()}")
                else:  # 月落
                    moonset_times.append(time.utc_datetime())
                    print(f"事件 {i}: 月落 at {time.utc_datetime()}")
            
            # 找到下一个月出和月落
            next_moonrise = None
            next_moonset = None
            
            # 查找下一个即将发生的月出和月落
            for rise_time in moonrise_times:
                if rise_time > now_utc:
                    next_moonrise = rise_time
                    break
                    
            for set_time in moonset_times:
                if set_time > now_utc:
                    next_moonset = set_time
                    break
            
            # 处理没有找到月出或月落的情况
            if not next_moonrise and moonrise_times:
                # 如果当前时间之后没有月出，取最后一个事件
                next_moonrise = moonrise_times[-1]
                
            if not next_moonset and moonset_times:
                # 如果当前时间之后没有月落，取最后一个事件
                next_moonset = moonset_times[-1]
            
            # 转换为本地时间
            if next_moonrise:
                moonrise_local = next_moonrise.replace(tzinfo=timezone.utc).astimezone(self.local_tz)
            else:
                moonrise_local = None
                
            if next_moonset:
                moonset_local = next_moonset.replace(tzinfo=timezone.utc).astimezone(self.local_tz)
            else:
                moonset_local = None
            
            # 格式化时间
            if moonrise_local:
                moonrise_str = moonrise_local.strftime("%H:%M")
                next_moonrise_str = moonrise_local.strftime("%m月%d日 %H:%M")
            else:
                moonrise_str = "--:--"
                next_moonrise_str = "--"
                
            if moonset_local:
                moonset_str = moonset_local.strftime("%H:%M")
                next_moonset_str = moonset_local.strftime("%m月%d日 %H:%M")
            else:
                moonset_str = "--:--"
                next_moonset_str = "--"
            
            # 修复：确保月出月落时间显示顺序正确
            # 确定显示顺序 - 根据时间先后顺序
            if moonrise_local and moonset_local:
                if moonrise_local < moonset_local:
                    first_event = "月出"
                    first_time = next_moonrise_str
                    second_event = "月落"
                    second_time = next_moonset_str
                else:
                    first_event = "月落"
                    first_time = next_moonset_str
                    second_event = "月出"
                    second_time = next_moonrise_str
            else:
                first_event = "月出"
                first_time = next_moonrise_str
                second_event = "月落"
                second_time = next_moonset_str
            
            self.moon_events = {
                "moonrise": moonrise_str,
                "moonset": moonset_str,
                "first_event": first_event,
                "first_time": first_time,
                "second_event": second_event,
                "second_time": second_time,
                "moonrise_dt": moonrise_local,
                "moonset_dt": moonset_local
            }
            
            print(f"使用skyfield计算月出月落时间: 月出 {self.moon_events['moonrise']}, 月落 {self.moon_events['moonset']}")
            print(f"显示顺序: {first_event} {first_time}, {second_event} {second_time}")
            
        except Exception as e:
            print(f"使用skyfield计算月出月落时间错误: {e}")
            import traceback
            traceback.print_exc()  # 打印完整的错误堆栈
            
            # 设置错误信息
            self.moon_events = {
                "moonrise": "--:--",
                "moonset": "--:--",
                "first_event": "月出",
                "first_time": "计算错误",
                "second_event": "月落",
                "second_time": "计算错误",
                "moonrise_dt": None,
                "moonset_dt": None
            }
    
    def calculate_moon_events(self):
        """计算月出和月落时间 - 只使用skyfield库"""
        global SKYFIELD_AVAILABLE
        
        # 验证星历数据
        if SKYFIELD_AVAILABLE:
            if not self.verify_and_reload_ephemeris():
                print("星历数据不可用，无法计算月出月落")
                self.moon_events = {
                    "moonrise": "--:--",
                    "moonset": "--:--",
                    "first_event": "月出",
                    "first_time": "星历数据不可用",
                    "second_event": "月落",
                    "second_time": "星历数据不可用",
                    "moonrise_dt": None,
                    "moonset_dt": None
                }
                return
        
        if SKYFIELD_AVAILABLE:
            self.calculate_moon_events_with_skyfield()
        else:
            # Skyfield不可用，设置错误信息
            self.moon_events = {
                "moonrise": "--:--",
                "moonset": "--:--",
                "first_event": "月出",
                "first_time": "需要安装skyfield库",
                "second_event": "月落",
                "second_time": "需要安装skyfield库",
                "moonrise_dt": None,
                "moonset_dt": None
            }
    
    def update_moon_events_periodically(self):
        """每1分钟或位置变化时更新月出月落时间"""
        current_time = time.time()
        # 检查是否需要更新月出月落时间（1分钟或位置变化）
        if (current_time - self.last_moon_events_update >= 60 or  # 1分钟 = 60秒
            (self.location["latitude"] != self.last_location["latitude"] or 
             self.location["longitude"] != self.last_location["longitude"] or
             self.location["timezone"] != self.last_location["timezone"])):  # 位置发生变化
            
            print("更新月出月落时间...")
            self.calculate_moon_events()
            self.last_moon_events_update = current_time
            self.last_location = self.location.copy()  # 更新上次位置信息
        
        if current_time - self.last_eclipse_update >= 21600:  # 6小时 = 21600秒
            print("更新日月食信息...")
            self.calculate_eclipses()
            self.last_eclipse_update = current_time
    
    def get_azimuth_direction(self, azimuth):
        """将方位角转换为方向（东、南、西、北等）"""
        directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
        index = round(azimuth / 45) % 8
        return directions[index]
    
    def is_moon_visible(self):
        """检查月球是否可见（在地平线以上）"""
        try:
            # 修复：使用有时区的时间
            now_local = datetime.now(timezone.utc).astimezone(self.local_tz)
            
            # 如果月球位置数据不可用，返回未知
            if not hasattr(self, 'last_moon_pos'):
                return "未知"
            
            # 检查高度角是否大于0（在地平线以上）
            if self.last_moon_pos['altitude'] > 0:
                return "可见"
            else:
                return "不可见"
        except:
            return "未知"
    
    def update_network_status(self):
        """定期更新网络状态并通知界面"""
        while self.is_running:
            # 每5秒检查一次网络状态
            time.sleep(5)
            
            # 检查网络状态
            was_online = self.network_available
            self.check_network_status()
            
            # 如果状态变化，通知界面更新
            if self.window and was_online != self.network_available:
                try:
                    self.window.evaluate_js(f"updateNetworkStatus({json.dumps(self.network_available)})")
                except Exception as e:
                    print(f"更新网络状态错误: {e}")

    def calculate_moon_position_with_skyfield(self):
        """使用Skyfield计算月球位置"""
        try:
            global SKYFIELD_AVAILABLE, ts, eph, moon, earth
            
            if not SKYFIELD_AVAILABLE:
                raise ImportError("skyfield库不可用")
                
            # 检查星历数据是否加载成功
            if eph is None:
                raise Exception("星历数据未加载")
                
            # 获取当前时间（UTC）
            now_utc = datetime.now(timezone.utc)
            t = ts.utc(now_utc)
            
            # 创建观察者位置
            from skyfield.api import wgs84
            observer = wgs84.latlon(self.location["latitude"], self.location["longitude"])
            
            # 计算月球位置（相对于观察者）- 修复方法调用
            apparent = (earth + observer).at(t).observe(moon).apparent()
            
            # 获取赤经和赤纬
            ra, dec, distance = apparent.radec()
            
            # 获取高度角和方位角
            alt, az, _ = apparent.altaz()
            
            return {
                "ra": ra.hours,
                "dec": dec.degrees,
                "distance": distance.km,
                "altitude": alt.degrees,
                "azimuth": az.degrees
            }
            
        except Exception as e:
            print(f"使用Skyfield计算月球位置错误: {e}")
            import traceback
            traceback.print_exc()
            return None

    # 修改 get_moon_data 方法，在返回数据中添加网络状态
    def get_moon_data(self):
        """获取月球数据 - 使用Skyfield计算"""
        try:
            # 使用UTC时间进行计算 - 修复：使用有时区的时间
            now_utc = datetime.now(timezone.utc)
            now_local = now_utc.astimezone(self.local_tz)  # 使用本地时区
            
            # 定期更新位置信息（每10秒）
            self.update_location_periodically()
            
            # 定期更新月出月落时间（每3分钟或位置变化时）
            self.update_moon_events_periodically()
            
            # 计算月球位置（使用Skyfield）
            moon_pos = None
            if SKYFIELD_AVAILABLE:
                moon_pos = self.calculate_moon_position_with_skyfield()
            
            # 如果Skyfield计算失败，返回错误信息
            if moon_pos is None:
                moon_pos = {
                    "ra": 0,
                    "dec": 0,
                    "distance": 0,
                    "altitude": 0,
                    "azimuth": 0
                }
            
            self.last_moon_pos = moon_pos  # 保存最后一次计算的位置
            
            # 计算月相
            jd = self.julian_day(now_utc)  # 儒略日（使用UTC时间）
            moon_phase = self.calculate_moon_phase(jd)
            
            # 获取方位角方向
            azimuth_direction = self.get_azimuth_direction(moon_pos['azimuth'])
            
            # 检查月球可见性
            visibility = self.is_moon_visible()
            
            # 格式化数据
            moon_data = {
                "time": now_local.strftime("%Y-%m-%d %H:%M:%S"),
                "ra": f"{moon_pos['ra']:.2f}时",  # 赤经单位改为"时"
                "dec": f"{moon_pos['dec']:.2f}°",  # 赤纬单位是度
                "distance": f"{moon_pos['distance']:.0f} km",
                "altitude": f"{moon_pos['altitude']:.1f}°",
                "azimuth": f"{moon_pos['azimuth']:.1f}° ({azimuth_direction})",  # 添加方位方向
                "phase": moon_phase,
                "location": self.location["name"],
                "longitude": f"{abs(self.location['longitude']):.4f}°{'E' if self.location['longitude'] >= 0 else 'W'}",  # 经度显示，正数为东经(E)，负数为西经(W)
                "latitude": f"{abs(self.location['latitude']):.4f}°{'N' if self.location['latitude'] >= 0 else 'S'}",    # 纬度显示，正数为北纬(N)，负数为南纬(S)
                "moonrise": self.moon_events["moonrise"],
                "moonset": self.moon_events["moonset"],
                "first_event": self.moon_events["first_event"],
                "first_time": self.moon_events["first_time"],
                "second_event": self.moon_events["second_event"],
                "second_time": self.moon_events["second_time"],
                "visibility": visibility,
                "online": self.network_available,
                "timezone": self.location["timezone"],
                "eclipses": self.eclipse_events,
                "skyfield_available": SKYFIELD_AVAILABLE,
                "skyfield_error": self.skyfield_error
            }
            
            return moon_data
        except Exception as e:
            print(f"计算月球数据错误: {e}")
            return None
    
    def julian_day(self, dt):
        """计算儒略日"""
        a = (14 - dt.month) // 12
        y = dt.year + 4800 - a
        m = dt.month + 12 * a - 3
        
        jdn = dt.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
        jd = jdn + (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0
        
        return jd
    
    def calculate_moon_phase(self, jd):
        """计算月相(0=新月, 0.5=满月)"""
        # 月相周期约29.53天
        phase = ((jd - 2451550.1) / 29.53) % 1
        if phase < 0:
            phase += 1
        return phase
    
    def update_moon_data(self):
        """定期更新月球数据 - 每秒更新"""
        while self.is_running:
            # 获取当前时间的秒部分
            current_second = datetime.now().second
            
            # 每秒更新一次
            moon_data = self.get_moon_data()
            if moon_data and self.window:
                try:
                    self.window.evaluate_js(f"updateMoonData({json.dumps(moon_data)})")
                    self.last_update_second = current_second
                except Exception as e:
                    print(f"更新数据错误: {e}")
            
            # 短暂休眠以减少CPU使用
            time.sleep(1)
    
    def create_window(self):
        try:
            # 尝试获取屏幕尺寸
            try:
                import win32api
                import win32con
                
                screen_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                
                # 窗口尺寸和位置 - 增加高度以确保内容完全显示
                window_width = 300
                window_height = 750  # 增加高度以适应内容
                x = screen_width - window_width - 20  # 右侧留20像素边距
                y = 100  # 离顶部100像素
            except:
                # 如果无法获取屏幕尺寸，使用默认值
                x, y = 100, 100
                window_width, window_height = 300, 750  # 增加高度以适应内容
        except Exception as e:
            print(f"窗口创建错误: {e}")
            # 使用安全的默认值
            x, y = 100, 100
            window_width, window_height = 300, 750  # 增加高度以适应内容
    
        
        # HTML内容
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {
                    margin: 0;
                    padding: 15px;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    background-color: rgba(10, 10, 20, 0.85);
                    color: #e0e0ff;
                    border-radius: 10px;
                    backdrop-filter: blur(5px);
                    -webkit-backdrop-filter: blur(5px);
                    overflow: hidden;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    height: 750px; /* 增加高度以适应内容 */
                    box-sizing: border-box;
                }
                .header {
                    text-align: center;
                    margin-bottom: 15px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.2);
                    padding-bottom: 10px;
                }
                .location {
                    text-align: center;
                    font-size: 12px;
                    color: #aaccff;
                    margin-bottom: 15px;
                }
                .data-row {
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 8px;
                    font-size: 13px;
                }
                .label {
                    font-weight: bold;
                    color: #aaccff;
                }
                .moon-phase {
                    text-align: center;
                    margin: 15px 0;
                    font-size: 60px;
                }
                .visibility {
                    text-align: center;
                    margin: 10px 0;
                    font-size: 14px;
                    font-weight: bold;
                }
                .visible {
                    color: #7fff7f;
                }
                .not-visible {
                    color: #ff7f7f;
                }
                .unknown {
                    color: #ffff7f;
                }
                .moon-events {
                    margin: 15px 0;
                    padding: 15px 0;
                    border-top: 1px solid rgba(255, 255, 255, 0.1);
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }
                .event-row {
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 5px;
                    font-size: 12px;
                }
                .last-update {
                    text-align: center;
                    margin-top: 15px;
                    font-size: 10px;
                    color: rgba(255, 255, 255, 5);
                }
                .close-btn {
                    position: absolute;
                    top: 5px;
                    right: 10;
                    color: rgba(255, 255, 255, 0.5);
                    cursor: pointer;
                    font-size: 16px;
                }
                .close-btn:hover {
                    color: white;
                }
                .topmost-btn {
                    position: absolute;
                    top: 5px;
                    right: 30px;  /* 在关闭按钮左侧 */
                    color: rgba(255, 255, 255, 0.5);
                    cursor: pointer;
                    font-size: 16px;
                }
                .topmost-btn:hover {
                    color: white;
                }
                .topmost-btn.pinned {
                    color: gold;
                }
                #loading {
                    text-align: center;
                    margin: 20px 0;
                    font-size: 12px;
                    color: #aaccff;
                }
                .network-status {
                    position: absolute;
                    top: 5px;
                    left: 10px;
                    font-size: 12px;
                }
                .online {
                    color: #7fff7f;
                }
                .offline {
                    color: #ff7f7f;
                }
                .eclipse-section {
                    margin: 15px 0;
                    padding: 15px 0;
                    border-top: 1px solid rgba(255, 255, 255, 0.1);
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                    max-height: 120px; /* 限制高度 */
                    overflow-y: auto;  /* 添加滚动条 */
                }
                .eclipse-header {
                    text-align: center;
                    font-weight: bold;
                    margin-bottom: 8px;
                    color: #aaccff;
                }
                .eclipse-item {
                    font-size: 11px;
                    margin-bottom: 5px;
                    display: flex;
                    justify-content: space-between;
                }
                .eclipse-time {
                    color: #ffff7f;
                }
                .eclipse-type {
                    color: #ff7f7f;
                }
                .no-eclipse {
                    text-align: center;
                    font-size: 11px;
                    color: rgba(255, 255, 255, 0.5);
                }
                .skyfield-error {
                    text-align: center;
                    margin: 10px 0;
                    padding: 10px;
                    background-color: rgba(255, 0, 0, 0.2);
                    border-radius: 5px;
                    font-size: 11px;
                    color: #ff7f7f;
                }
            </style>
        </head>
        <body>
            <div class="close-btn" onclick="window.pywebview.api.close_app()">×</div>
            <div class="network-status" id="network-status">● 在线</div>
            <div class="topmost-btn" id="topmost-btn" onclick="toggleTopmost()">📌</div>

            <div class="header">
                <h2 style="margin: 0;">🌙 月球位置</h2>
            </div>
            
            <div id="loading">
                正在初始化...<br>
                <span id="loading-status">加载中，请稍候...</span>
            </div>
            
            <div id="skyfield-error" class="skyfield-error" style="display: none;"></div>
            
            <div class="location">
                位置: <span id="location">--</span>
            </div>
            
            <div class="data-row">
                <span class="label">经度:</span>
                <span id="longitude">--</span>
            </div>
            
            <div class="data-row">
                <span class="label">纬度:</span>
                <span id="latitude">--</span>
            </div>
            
            <div class="data-row">
                <span class="label">时间 (<span id="timezone">--</span>):</span>
                <span id="time">--:--:--</span>
            </div>
            
            <div class="data-row">
                <span class="label">赤经 (J2000):</span>
                <span id="ra">--</span>
            </div>
            
            <div class="data-row">
                <span class="label">赤纬 (J2000):</span>
                <span id="dec">--</span>
            </div>
            
            <div class="data-row">
                <span class="label">地月距离:</span>
                <span id="distance">--</span>
            </div>
            
            <div class="data-row">
                <span class="label">方位角:</span>
                <span id="azimuth">--</span>
            </div>
            
            <div class="data-row">
                <span class="label">高度角:</span>
                <span id="altitude">--</span>
            </div>
            
            <!-- 月出月落时间放在高度角下面 -->
            <div class="moon-events">
                <div class="event-row">
                    <span class="label" id="first-event-label">--</span>
                    <span id="first-event-time">--</span>
                </div>
                <div class="event-row">
                    <span class="label" id="second-event-label">--</span>
                    <span id="second-event-time">--</span>
                </div>
            </div>
            
            <!-- 月球emoji放在月出月落时间下面 -->
            <div class="moon-phase" id="moon-phase">🌑</div>
            
            <div class="visibility" id="visibility-container">
                可见性: <span id="visibility">--</span>
            </div>
            
            <div class="last-update" id="last-update">最后更新: --</div>
            
            <div class="eclipse-section">
                <div class="eclipse-header">未来7天日月食</div>
                <div id="eclipse-list">
                    <div class="no-eclipse">加载中...</div>
                </div>
            </div>

            <script>
                function updateEclipseData(eclipses) {
                    const eclipseList = document.getElementById('eclipse-list');
                    
                    if (eclipses.length === 0) {
                        eclipseList.innerHTML = '<div class="no-eclipse">未来7天内无日月食事件</div>';
                        return;
                    }
                    
                    let html = '';
                    eclipses.forEach(eclipse => {
                        // 根据类型设置不同的图标
                        let icon = '🌙'; // 默认月亮
                        if (eclipse.raw_type < 3) { // 日食
                            icon = '☀️';
                        }
                        
                        html += `
                            <div class="eclipse-item">
                                <span class="eclipse-time">${icon} ${eclipse.time}</span>
                                <span class="eclipse-type">${eclipse.type}</span>
                            </div>
                        `;
                    });
                    
                    eclipseList.innerHTML = html;
                }

                function updateMoonData(data) {
                    // 隐藏加载提示
                    document.getElementById('loading').style.display = 'none';
                    
                    // 显示或隐藏Skyfield错误信息
                    const errorEl = document.getElementById('skyfield-error');
                    if (data.skyfield_available) {
                        errorEl.style.display = 'none';
                    } else {
                        errorEl.style.display = 'block';
                        errorEl.textContent = data.skyfield_error || 'Skyfield不可用，部分功能受限';
                    }
                    
                    document.getElementById('location').textContent = data.location;
                    document.getElementById('longitude').textContent = data.longitude;
                    document.getElementById('latitude').textContent = data.latitude;
                    document.getElementById('timezone').textContent = data.timezone;
                    document.getElementById('time').textContent = data.time;
                    document.getElementById('ra').textContent = data.ra;
                    document.getElementById('dec').textContent = data.dec;
                    document.getElementById('distance').textContent = data.distance;
                    document.getElementById('azimuth').textContent = data.azimuth;
                    document.getElementById('altitude').textContent = data.altitude;
                    
                    // 更新月出月落事件显示
                    document.getElementById('first-event-label').textContent = data.first_event + ':';
                    document.getElementById('first-event-time').textContent = data.first_time;
                    document.getElementById('second-event-label').textContent = data.second_event + ':';
                    document.getElementById('second-event-time').textContent = data.second_time;
                    
                    document.getElementById('visibility').textContent = data.visibility;
                    
                    // 更新可见性样式
                    const visibilityEl = document.getElementById('visibility-container');
                    visibilityEl.className = 'visibility';
                    if (data.visibility === '可见') {
                        visibilityEl.classList.add('visible');
                    } else if (data.visibility === '不可见') {
                        visibilityEl.classList.add('not-visible');
                    } else {
                        visibilityEl.classList.add('unknown');
                    }
                    
                    // 更新月相表情
                    const phase = parseFloat(data.phase);
                    let moonEmoji = '🌑'; // 新月
                    if (phase > 0.9375 || phase <= 0.0625) moonEmoji = '🌑'; // 新月
                    else if (phase <= 0.1875) moonEmoji = '🌒'; // 娥眉月
                    else if (phase <= 0.3125) moonEmoji = '🌓'; // 上弦月
                    else if (phase <= 0.4375) moonEmoji = '🌔'; // 盈凸月
                    else if (phase <= 0.5625) moonEmoji = '🌕'; // 满月
                    else if (phase <= 0.6875) moonEmoji = '🌖'; // 亏凸月
                    else if (phase <= 0.8125) moonEmoji = '🌗'; // 下弦月
                    else if (phase <= 0.9375) moonEmoji = '🌘'; // 残月
                    
                    document.getElementById('moon-phase').textContent = moonEmoji;
                    
                    // 更新日月食信息
                    updateEclipseData(data.eclipses || []);

                    // 更新最后更新时间
                    const now = new Date();
                    document.getElementById('last-update').textContent = 
                        `最后更新: ${now.toLocaleTimeString()}`;
                    // 更新网络状态
                    updateNetworkStatus(data.online);
                }
                
                function updateNetworkStatus(online) {
                    const statusEl = document.getElementById('network-status');
                    if (online) {
                        statusEl.textContent = '● 在线';
                        statusEl.className = 'network-status online';
                    } else {
                        statusEl.textContent = '● 离线 (使用缓存位置)';
                        statusEl.className = 'network-status offline';
                    }
                }
                
                function toggleTopmost() {
                    const btn = document.getElementById('topmost-btn');
                    // 先立即更新UI状态，让用户有即时反馈
                    const isCurrentlyPinned = btn.classList.contains('pinned');
                    btn.classList.toggle('pinned', !isCurrentlyPinned);
                    
                    // 然后调用API设置实际状态
                    window.pywebview.api.set_topmost(!isCurrentlyPinned).then(function(success) {
                        if (!success) {
                            // 如果操作失败，恢复原来的状态
                            btn.classList.toggle('pinned', isCurrentlyPinned);
                            console.log('置顶操作失败');
                        }
                    });
                }

                function hideLoading() {
                    document.getElementById('loading').style.display = 'none';
                }
                
                

                // 初始显示
                updateMoonData({
                    location: "获取中...",
                    longitude: "--",
                    latitude: "--",
                    timezone: "--",
                    time: "--:--:--",
                    ra: "--",
                    dec: "--",
                    distance: "--",
                    azimuth: "--",
                    altitude: "--",
                    first_event: "月出",
                    first_time: "--",
                    second_event: "月落",
                    second_time: "--",
                    visibility: "--",
                    phase: 0,
                    skyfield_available: true
                });
            </script>
        </body>
        </html>
        """
        
        # 创建窗口 - 移除on_top参数，使其可以被其他窗口覆盖
        self.window = webview.create_window(
            '月球位置',
            html=html_content,
            width=window_width,
            height=window_height,
            x=x,
            y=y,
            frameless=True,
            easy_drag=True,  # 允许拖动
            transparent=True,
            focus=False    # 不获取焦点
        )
        
        # 绑定关闭方法
        self.window.expose(self.close_app, self.set_topmost)
    
    def close_app(self):
        """关闭应用 - 修改为仅关闭窗口而不是终止进程"""
        self.is_running = False
        try:
            # 仅关闭窗口，而不是终止整个进程
            if self.window:
                self.window.destroy()
        except Exception as e:
            print(f"关闭窗口时出错: {e}")
    
    def hide_taskbar_icon(self):
        """隐藏任务栏图标 - 每10秒尝试一次，直到成功"""
        while self.is_running:
            try:
                import win32gui
                import win32con
                
                # 查找窗口句柄
                def find_window(hwnd, extra):
                    if win32gui.GetWindowText(hwnd) == "月球位置":
                        extra.append(hwnd)
                    return True
                
                windows = []
                win32gui.EnumWindows(find_window, windows)
                
                if windows:
                    hwnd = windows[0]
                    # 设置窗口样式为工具窗口，不显示在任务栏
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, 
                                        win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_TOOLWINDOW)
                    print("任务栏图标已隐藏")
                    return True  # 成功隐藏，退出循环
                    
            except Exception as e:
                print(f"隐藏任务栏图标失败: {e}")
            
            # 每10秒尝试一次
            time.sleep(10)
    
    def run(self):
        """运行应用"""
        # 创建窗口
        self.create_window()
        
        # 启动数据更新线程
        update_thread = threading.Thread(target=self.update_moon_data)
        update_thread.daemon = True
        update_thread.start()
        
        # 启动网络状态监控极线程
        network_thread = threading.Thread(target=self.update_network_status)
        network_thread.daemon = True
        network_thread.start()
        
        # 启动隐藏任务栏图标的线程
        hide_icon_thread = threading.Thread(target=self.hide_taskbar_icon)
        hide_icon_thread.daemon = True
        hide_icon_thread.start()
        
        # 启动WebView
        webview.start(debug=False)

if __name__ == '__main__':
    # 如果设置了隐藏控制台，则尝试隐藏
    if HIDE_CONSOLE:
        hide_console_window()
    
    # 设置为后台运行，不显示控制台窗口
    if sys.executable.endswith("pythonw.exe"):
        # 如果使用pythonw运行，已经是后台模式
        widget = MoonWidget()
        widget.run()
    else:
        # 如果使用python运行，根据全局变量决定是否隐藏控制台
        widget = MoonWidget()
        widget.run()