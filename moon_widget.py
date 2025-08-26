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

class MoonWidget:
    def __init__(self):
        self.window = None
        self.update_interval = 1  # 更新间隔改为1秒
        self.is_running = True
        self.location = self.get_location()  # 获取位置信息
        self.moon_events = {}  # 存储月出月落时间
        self.local_tz = pytz.timezone(self.location["timezone"])  # 使用IP所在地的时区
        self.last_update_second = -1  # 记录上一次更新的秒数
        
        # 添加时间戳记录
        self.last_ip_update = 0  # 上次IP更新时间
        self.last_moon_events_update = 0  # 上次月出月落更新时间
        self.last_location = self.location.copy()  # 保存上次位置信息用于比较
        
        # 初始化Skyfield
        self.init_skyfield_async()
        
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
                print("skyfield库未安装，将使用简化算法计算月出月落时间")
                print("要获得更精确的结果，请安装: pip install skyfield")
            except Exception as e:
                SKYFIELD_AVAILABLE = False
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
                
    def get_public_ip(self):
        """获取本机公网IP地址"""
        try:
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
                        return {
                            'name': f"{response.city.name if response.city.name else '未知'}, {response.country.name if response.country.name else '未知'}",
                            'latitude': response.location.latitude,
                            'longitude': response.location.longitude,
                            'timezone': response.location.time_zone if response.location.time_zone else 'Asia/Shanghai'
                        }
            except Exception as e:
                print(f"使用geoip2数据库失败: {e}")
            
            # 方法2: 使用在线API (ipapi.co)
            try:
                response = requests.get(f'https://ipapi.co/{ip_address}/json/', timeout=3)
                data = response.json()
                if 'error' not in data:
                    return {
                        'name': f"{data.get('city', '未知')}, {data.get('country_name', '未知')}",
                        'latitude': data.get('latitude', 31.2304),
                        'longitude': data.get('longitude', 121.4737),
                        'timezone': data.get('timezone', 'Asia/Shanghai')
                    }
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
            
            # 如果通过IP获取失败，使用默认位置（上海）
            print("使用默认位置: 上海")
            return {
                "name": "上海",
                "latitude": 31.2304,
                "longitude": 121.4737,
                "timezone": "Asia/Shanghai"
            }
        except Exception as e:
            print(f"获取位置信息错误: {e}")
            return {
                "name": "上海",
                "latitude": 31.2304,
                "longitude": 121.4737,
                "timezone": "Asia/Shanghai"
            }
    
    def update_location_periodically(self):
        """每30秒更新一次位置信息，如果位置变化则标记需要更新月出月落时间"""
        current_time = time.time()
        if current_time - self.last_ip_update >= 30:  # 30秒更新一次
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
                # 使用简化算法作为备选
                self.calculate_moon_events_simple()
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
            # 回退到简化算法
            self.calculate_moon_events_simple()
    
    def calculate_moon_events_simple(self):
        """简化算法计算月出月落时间（备用方法）"""
        try:
            # 获取当前日期（使用本地时区）- 修复：使用有时区的时间
            now_utc = datetime.now(timezone.utc)
            local_now = now_utc.astimezone(self.local_tz)  # 使用本地时区
            
            # 计算儒略日
            jd = self.julian_day(now_utc)
            
            # 基于月球每天延迟约50分钟升起的事实
            days_since_new_moon = jd % 29.53
            moonrise_delay_minutes = 50 * days_since_new_moon
            
            # 计算月出时间（本地时区）
            moonrise_hour = (12 + moonrise_delay_minutes / 60) % 24
            moonrise_minute = (moonrise_hour - int(moonrise_hour)) * 60
            
            # 创建月出时间（使用本地时间）
            moonrise_time = local_now.replace(
                hour=int(moonrise_hour), 
                minute=int(moonrise_minute), 
                second=0, 
                microsecond=0
            )
            
            # 月落时间大约是月出时间后12小时50分钟
            moonset_time = moonrise_time + timedelta(hours=12, minutes=50)
            
            # 如果月出时间已经过去，计算下一次月出时间
            if moonrise_time < local_now:
                moonrise_time += timedelta(days=1)
                moonset_time += timedelta(days=1)
            
            # 如果月落时间已经过去，计算下一次月落时间
            if moonset_time < local_now:
                moonset_time += timedelta(days=1)
            
            # 格式化时间
            moonrise_str = moonrise_time.strftime("%H:%M")
            moonset_str = moonset_time.strftime("%H:%M")
            
            # 修复：确保月出月落时间显示顺序正确
            # 确定显示顺序 - 根据时间先后顺序
            if moonrise_time < moonset_time:
                first_event = "月出"
                first_time = moonrise_time.strftime("%m月%d日 %H:%M")
                second_event = "月落"
                second_time = moonset_time.strftime("%m月%d日 %H:%M")
            else:
                first_event = "月落"
                first_time = moonset_time.strftime("%m月%d日 %H:%M")
                second_event = "月出"
                second_time = moonrise_time.strftime("%m月%d日 %H:%M")
            
            self.moon_events = {
                "moonrise": moonrise_str,
                "moonset": moonset_str,
                "first_event": first_event,
                "first_time": first_time,
                "second_event": second_event,
                "second_time": second_time,
                "moonrise_dt": moonrise_time,
                "moonset_dt": moonset_time
            }
            
            print(f"使用简化算法计算月出月落时间: 月出 {self.moon_events['moonrise']}, 月落 {self.moon_events['moonset']}")
            print(f"显示顺序: {first_event} {first_time}, {second_event} {second_time}")
            
        except Exception as e:
            print(f"简化算法计算月出月落时间错误: {e}")
            self.moon_events = {
                "moonrise": "--:--",
                "moonset": "--:--",
                "first_event": "月出",
                "first_time": "--",
                "second_event": "月落",
                "second_time": "--",
                "moonrise_dt": None,
                "moonset_dt": None
            }
    
    def calculate_moon_events(self):
        """计算月出和月落时间 - 优先使用skyfield库"""
        global SKYFIELD_AVAILABLE
        
        # 验证星历数据
        if SKYFIELD_AVAILABLE:
            if not self.verify_and_reload_ephemeris():
                print("星历数据不可用，使用简化算法")
                self.calculate_moon_events_simple()
                return
        
        if SKYFIELD_AVAILABLE:
            self.calculate_moon_events_with_skyfield()
        else:
            self.calculate_moon_events_simple()
    
    def update_moon_events_periodically(self):
        """每3分钟或位置变化时更新月出月落时间"""
        current_time = time.time()
        # 检查是否需要更新月出月落时间（3分钟或位置变化）
        if (current_time - self.last_moon_events_update >= 180 or  # 3分钟 = 180秒
            (self.location["latitude"] != self.last_location["latitude"] or 
             self.location["longitude"] != self.last_location["longitude"] or
             self.location["timezone"] != self.last_location["timezone"])):  # 位置发生变化
            
            print("更新月出月落时间...")
            self.calculate_moon_events()
            self.last_moon_events_update = current_time
            self.last_location = self.location.copy()  # 更新上次位置信息
    
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
    
    def get_moon_data(self):
        """离线计算月球位置数据"""
        try:
            # 使用UTC时间进行计算 - 修复：使用有时区的时间
            now_utc = datetime.now(timezone.utc)
            now_local = now_utc.astimezone(self.local_tz)  # 使用本地时区
            
            jd = self.julian_day(now_utc)  # 儒略日（使用UTC时间）
            
            # 定期更新位置信息（每30秒）
            self.update_location_periodically()
            
            # 定期更新月出月落时间（每3分钟或位置变化时）
            self.update_moon_events_periodically()
            
            # 计算月球位置（改进的计算）
            moon_pos = self.calculate_moon_position(jd, now_utc)
            self.last_moon_pos = moon_pos  # 保存最后一次计算的位置
            
            # 计算月相
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
                "longitude": f"{self.location['longitude']:.4f}°",  # 添加经度显示
                "latitude": f"{self.location['latitude']:.4f}°",   # 添加纬度显示
                "moonrise": self.moon_events["moonrise"],
                "moonset": self.moon_events["moonset"],
                "first_event": self.moon_events["first_event"],
                "first_time": self.moon_events["first_time"],
                "second_event": self.moon_events["second_event"],
                "second_time": self.moon_events["second_time"],
                "visibility": visibility,
                "timezone": self.location["timezone"]
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
    
    def calculate_moon_position(self, jd, dt_utc):
        """改进计算月球位置，考虑当地经纬度"""
        # 基于更精确的算法计算月球位置
        
        # 计算时间参数（以世纪为单位）
        T = (jd - 2451545.0) / 36525.0
        
        # 月球平黄经
        Lp = 218.3164477 + 481267.88123421 * T - 0.0015786 * T**2 + T**3 / 538841 - T**4 / 65194000
        Lp = Lp % 360
        
        # 月球平近点角
        M = 134.96298139 + 477198.86739806 * T + 0.0086972 * T**2 + T**3 / 56250
        M = math.radians(M % 360)
        
        # 太阳平近点角
        Mprime = 357.52772333 + 35999.05034 * T - 0.0001603 * T**2 - T**3 / 300000
        Mprime = math.radians(Mprime % 360)
        
        # 月球升交点平黄经
        Omega = 125.04455501 - 1934.13618488 * T + 0.0020762 * T**2 + T**3 / 467410 - T**4 / 60616000
        Omega = math.radians(Omega % 360)
        
        # 计算月球经度
        # 主要周期项
        l = math.radians(Lp) + math.radians(6.288774 * math.sin(M) + 
                                          1.274018 * math.sin(2 * math.radians(Lp) - M) +
                                          0.658309 * math.sin(2 * math.radians(Lp)) +
                                          0.213616 * math.sin(2 * M) -
                                          0.185596 * math.sin(Mprime) -
                                          0.114336 * math.sin(2 * Omega))
        
        # 计算月球纬度
        b = math.radians(5.128189 * math.sin(Omega) +
                        0.280606 * math.sin(M + Omega) +
                        0.277693 * math.sin(M - Omega) +
                        0.173238 * math.sin(2 * math.radians(Lp) - Omega))
        
        # 计算距离（千米）
        distance = 385000.56 + 20905.355 * math.cos(M) + 3699.111 * math.cos(2 * math.radians(Lp) - M) + 2955.967 * math.cos(2 * math.radians(Lp))
        
        # 转换为赤道坐标
        # 黄赤交角
        epsilon = math.radians(23.4392911 - 0.0130042 * T)
        
        # 赤经
        ra = math.atan2(math.sin(l) * math.cos(epsilon) - math.tan(b) * math.sin(epsilon), math.cos(l))
        if ra < 0:
            ra += 2 * math.pi
        ra = math.degrees(ra) / 15  # 转换为小时
        
        # 赤纬
        dec = math.asin(math.sin(b) * math.cos(epsilon) + math.cos(b) * math.sin(epsilon) * math.sin(l))
        dec = math.degrees(dec)
        
        # 计算高度角和方位角（考虑当地经纬度）
        # 地方恒星时
        gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T**2 - T**3 / 38710000
        gmst = gmst % 360
        
        # 计算时角
        ha = (gmst + self.location["longitude"] - ra * 15) % 360
        if ha > 180:
            ha -= 360
        
        # 转换为弧度
        ha_rad = math.radians(ha)
        dec_rad = math.radians(dec)
        lat_rad = math.radians(self.location["latitude"])
        
        # 计算高度角
        sin_alt = math.sin(lat_rad) * math.sin(dec_rad) + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad)
        alt = math.degrees(math.asin(sin_alt))
        
        # 计算方位角
        cos_az = (math.sin(dec_rad) - math.sin(lat_rad) * sin_alt) / (math.cos(lat_rad) * math.cos(math.radians(alt)))
        az = math.degrees(math.acos(cos_az))
        
        # 调整方位角
        if math.sin(ha_rad) > 0:
            az = 360 - az
        
        return {
            "ra": ra,
            "dec": dec,
            "distance": distance,
            "altitude": alt,
            "azimuth": az
        }
    
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
                window_height = 650  # 增加高度以适应内容
                x = screen_width - window_width - 20  # 右侧留20像素边距
                y = 100  # 离顶部100像素
            except:
                # 如果无法获取屏幕尺寸，使用默认值
                x, y = 100, 100
                window_width, window_height = 300, 650  # 增加高度以适应内容
        except Exception as e:
            print(f"窗口创建错误: {e}")
            # 使用安全的默认值
            x, y = 100, 100
            window_width, window_height = 300, 650  # 增加高度以适应内容
    
        
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
                    height: 620px; /* 增加高度以适应内容 */
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
                    color: rgba(255, 255, 255, 0.5);
                }
                .close-btn {
                    position: absolute;
                    top: 5px;
                    right: 10px;
                    color: rgba(255, 255, 255, 0.5);
                    cursor: pointer;
                    font-size: 16px;
                }
                .close-btn:hover {
                    color: white;
                }
                #loading {
                    text-align: center;
                    margin: 20px 0;
                    font-size: 12px;
                    color: #aaccff;
                }
            </style>
        </head>
        <body>
            <div class="close-btn" onclick="window.pywebview.api.close_app()">×</div>
            
            <div class="header">
                <h2 style="margin: 0;">🌙 月球位置</h2>
            </div>
            
            <div id="loading">
                正在初始化...<br>
                <span id="loading-status">加载中，请稍候...</span>
            </div>
            
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
            
            <script>
                function updateMoonData(data) {
                    // 隐藏加载提示
                    document.getElementById('loading').style.display = 'none';
                    
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
                    if (phase > 0.9375 || phase <= 0.0625) moonEmoji = '🌑🌑'; // 新月
                    else if (phase <= 0.1875) moonEmoji = '🌒'; // 娥眉月
                    else if (phase <= 0.3125) moonEmoji = '🌓'; // 上弦月
                    else if (phase <= 0.4375) moonEmoji = '🌔'; // 盈凸月
                    else if (phase <= 0.5625) moonEmoji = '🌕'; // 满月
                    else if (phase <= 0.6875) moonEmoji = '🌖'; // 亏凸月
                    else if (phase <= 0.8125) moonEmoji = '🌗'; // 下弦月
                    else if (phase <= 0.9375) moonEmoji = '🌘'; // 残月
                    
                    document.getElementById('moon-phase').textContent = moonEmoji;
                    
                    // 更新最后更新时间
                    const now = new Date();
                    document.getElementById('last-update').textContent = 
                        `最后更新: ${now.toLocaleTimeString()}`;
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
                    phase: 0
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
        self.window.expose(self.close_app)
    
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
        
        # 启动隐藏任务栏图标的线程
        hide_icon_thread = threading.Thread(target=self.hide_taskbar_icon)
        hide_icon_thread.daemon = True
        hide_icon_thread.start()
        
        # 启动WebView
        webview.start(debug=False)

if __name__ == '__main__':
    # 设置为后台运行，不显示控制台窗口
    if sys.executable.endswith("pythonw.exe"):
        # 如果使用pythonw运行，已经是后台模式
        widget = MoonWidget()
        widget.run()
    else:
        # 如果使用python运行，尝试隐藏控制台窗口
        try:
            import win32gui
            import win32con
            # 隐藏控制台窗口
            win32gui.ShowWindow(win32gui.GetForegroundWindow(), win32con.SW_HIDE)
        except:
            pass
        
        widget = MoonWidget()
        widget.run()