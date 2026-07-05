#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec  9 15:32:11 2018

@author: wpf
"""
#待解决：地球形状的考虑，不同时刻月影在地球上的切点或者投影点（食甚时食分的计算）
import datetime
import math
from skyfield.api import load
from skyfield.api import wgs84,E,W,S,N
from skyfield.framelib import itrs
from skyfield.positionlib import ICRF
from skyfield.units import Angle
import numpy as np

# ===== Skyfield timescale now() wrapper =====
_ts_now_override = None

def set_ts_now_override(jd):
    """设置timescale.now()的覆盖值（通常是一个 skyfield Time 对象）。"""
    global _ts_now_override
    _ts_now_override = jd

def clear_ts_now_override():
    """清除覆盖，使 get_ts_now() 返回真实的 ts.now()。"""
    global _ts_now_override
    _ts_now_override = None

def get_ts_now():
    """获取当前时间的 skyfield Time 对象，支持覆盖以便调试。"""
    if _ts_now_override is not None:
        return _ts_now_override
    return ts.now()


planets = load('de440s.bsp')
ts = load.timescale()



#常量20
re=6378136.6#地球半径大小差几千米，对下面的时间有较大影响，因此要精确计算出日食时间，需要计算出对应的地点，求出到地心距离
rs = 696300000.0 #太阳半径
rm = 1738000.0 #月亮半径
au=149597870700#天文单位
light_vel=299792458.0#光速

#迭代计算光行时
def light_time(jd,body1,body2):#body1在jd看到body2发出光时，body2的方向
    dt0=au/light_vel
    while True:
        pos_body1=planets[body1].at(ts.tdb_jd(jd.tdb-dt0/86400)).position.m#阳光离开天体2时的天体1的icrs坐标
        pos_body2=planets[body2].at(ts.tdb_jd(jd.tdb-dt0/86400)).position.m#阳光离开天体2时的天体2的icrs坐标
        d=0
        for i in range(3):
            d+=(pos_body1[i]-pos_body2[i])*(pos_body1[i]-pos_body2[i])
        dt=math.sqrt(d)/light_vel#光行时
        if math.fabs(dt0-dt)<1:#差值小于1秒
            return ts.tdb_jd(jd.tdb-dt0/86400)
        dt0=dt
        #n=n+1

#判断日食状态要用到的一些夹角,不同天体代号
def body_vector(jd,flag):
    #1.构造天体
    earth = planets[399]
    moon=planets[301]
    sun=planets[10]
    pos_earth=earth.at(jd).position.m
    pos_moon=moon.at(jd).position.m
    pos_sun=sun.at(jd).position.m
    #计算光行时并改正
    jd0=light_time(jd,301,10)
    pos_moon0=moon.at(jd0).position.m#太阳发出光时的地球icrs坐标
    pos_sun0=sun.at(jd0).position.m#太阳发出光时的太阳的icrs坐标
    #2.矢量计算
    #计算地轴指向（不再用obs_env）
    north_pole = earth + wgs84.latlon(90* N, 0 * E)
    p1=earth.at(jd).observe(moon).position.m
    p2=north_pole.at(jd).observe(moon).position.m
    pole_direction=p2-p1
    #矢量初始化
    if flag==0:#半影，偏食
        O1_B = rm / (rm+rs) * ( pos_moon0- pos_sun0)-pos_moon#月球半影锥点到太阳系质心矢量坐标，pos_moon0[i]- pos_sun0[i]是太阳发出光时日月相对位置
        O1_E = O1_B + pos_earth#月球半影锥点到地球距离矢量坐标
        O1_M = O1_B + pos_moon#月球半影锥点到月球距离矢量坐标
        return O1_E,O1_M,pole_direction
    elif flag==1 or flag==2 or flag==3:#全影，全食或环食
        O2_B = rm / (rm-rs) * ( pos_moon0- pos_sun0)-pos_moon#月球全影锥点到太阳系质心矢量，pos_moon0[i]- pos_sun0[i]是太阳发出光时日月相对位置
        O2_E=  O2_B + pos_earth#月球全影锥点到地球距离矢量坐标
        O2_M = O2_B + pos_moon#月球全影锥点到月球距离矢量坐标
        return O2_E,O2_M,pole_direction
    else:
        E_S=pos_sun0-pos_earth
        E_M=pos_moon-pos_earth
        return E_S,E_M,pole_direction

#判断月球全影锥点是否在椭圆里面
def in_out(E_A,O_E,a,b):
    theta=math.pi-diancheng(E_A,O_E)#和x轴夹角
    d=math.sqrt((a*math.cos(theta))**2+(b*math.sin(theta))**2)#椭圆的参数方程
    O_Elength=math.sqrt(O_E[0]**2+O_E[1]**2+O_E[2]**2)
    if d<O_Elength:#在椭圆外
        return 0
    else:
        return 1

#叉乘计算,返回一个单位矢量
def chacheng(O_E,O_S):
    O_U=[]
    s=0
    O_U.append(O_E[1]*O_S[2]-O_E[2]*O_S[1])
    O_U.append(O_E[2]*O_S[0]-O_E[0]*O_S[2])
    O_U.append(O_E[0]*O_S[1]-O_E[1]*O_S[0])
    for i in range(3):
        s+=O_U[i]*O_U[i]
    s=math.sqrt(s)
    for i in range(3):
        O_U[i]=O_U[i]/s
    return np.array(O_U)

#点乘计算,返回夹角
def diancheng(O_E,O_S):
    O_Elength=math.sqrt(O_E[0]**2+O_E[1]**2+O_E[2]**2)
    O_Slength=math.sqrt(O_S[0]**2+O_S[1]**2+O_S[2]**2)
    vpd_OES=O_E[0]*O_S[0]+O_E[1]*O_S[1]+O_E[2]*O_S[2]
    return math.acos(vpd_OES/(O_Elength*O_Slength))

#判断椭圆和直线是否有交点
def ellipse_line(E_A,E_B,O_E,O_T,a,b):
    #求O_T和O_E以及椭圆长半轴和短半轴的夹角
    theta1=diancheng(O_T,E_A)
    theta2=diancheng(O_T,E_B)
    theta3=diancheng(O_T,O_E)
    theta4=diancheng(O_E,E_B)
    O_Elength=math.sqrt(O_E[0]**2+O_E[1]**2+O_E[2]**2)
    k=math.cos(theta2)/math.cos(theta1)
    if theta4>theta2:
        d=O_Elength/math.sin(theta2)*math.sin(theta3)#角的正弦公式
    else:
        d=-O_Elength/math.sin(theta2)*math.sin(theta3)#角的正弦公式
    #求椭圆x^2/a^2+y^2/b^2=1和y=kx+d的解
    '''print(O_Elength,theta2,theta3,math.sin(theta2),math.sin(theta3))
    print(a,b,k,d)
    print((a*k*d)**2,(a*a*k*k+b*b),(d*d-b*b))'''
    delta=(a*k*d)**2-(a*a*k*k+b*b)*(d*d-b*b)
    if delta<0:
        return delta,0,[0.0,0.0,0.0]
    else:
        x1=(-a*a*k*d+a*math.sqrt(delta))/(a*a*k*k+b*b)
        y1=k*x1+d
        E_T1=E_A*x1+E_B*y1
        O_T1=O_E+E_T1#椭圆和直线的第一个交点为T1
        r1=O_T1[0]/O_T[0]
        x2=(-a*a*k*d-a*math.sqrt(delta))/(a*a*k*k+b*b)
        y2=k*x2+d
        E_T2=E_A*x2+E_B*y2
        O_T2=O_E+E_T2#椭圆和直线的第二个交点为T2
        r2=O_T2[0]/O_T[0]
        #print(r1,O_T1[1]/O_T[1],O_T1[2]/O_T[2])
        #print(r2,O_T2[1]/O_T[1],O_T2[2]/O_T[2])
        if r1>r2:
            return delta,r1,E_T1
        else:
            return delta,r2,E_T2

#求椭圆的长半轴、短半轴指向单位矢量和对应的值
def ellipse(jd,flag):
    O_E,O_M,E_P=body_vector(jd,flag)
    O_Y=chacheng(O_E,O_M)#垂直于太阳质心，地心，月心所在平面的单位矢量坐标
    O_X=chacheng(O_Y,O_M)#垂直于太阳质心，O1_Y，月心所在平面的单位矢量坐标
    E_A=chacheng(O_Y,E_P)#太阳质心，地心，月心所在平面和赤道面夹线的单位矢量坐标，也是前者切地球椭球面所定的椭圆长半轴
    E_B=chacheng(O_Y,E_A)#太阳质心，地心，月心所在平面切地球椭球面所定的椭圆短半轴
    theta=diancheng(O_Y,E_P)#太阳质心，地心，月心所在平面和赤道面夹角
    a=6377830#长半轴长度
    b=math.sqrt((a*math.cos(theta))**2+(6356909*math.sin(theta))**2)#短半轴长度，就是纬度为theta或者180-theta的地方的地心距
    return O_E,O_M,E_A,E_B,O_X,a,b

#求出半影/全影影锥和地球表面切点的切点，返回地心到其的gcrs矢量坐标
def tangent_point(jd,flag):#flag偏食为0，全食为,1，环食为2,全食或者环食食甚为3
    O_E,O_M,E_A,E_B,O_X,a,b=ellipse(jd,flag)
    O_Mlength=math.sqrt(O_M[0]**2+O_M[1]**2+O_M[2]**2)
    thetaM_O=math.asin(rm/O_Mlength)
    if flag==0 or flag==1:#偏食（偏食食甚）和全食
        rat=-1.0*O_Mlength*math.tan(thetaM_O)
    elif flag==2:#环食
        rat=1.0*O_Mlength*math.tan(thetaM_O)
    else:#全食或者环食食甚，用来计算食分
        rat=0.0
    O_T = O_M+rat*O_X
    return ellipse_line(E_A,E_B,O_E,O_T,a,b)

#由地表某点求得的gcrs坐标反求地心距
def gcrs2latlon(v,jd):
    v = ICRF([v[0],v[1],v[2]],t=jd)
    sub_latlon=v.frame_latlon(itrs)
    '''lat=sub_latlon[0].degrees*math.pi/180
    a=(6378000*math.cos(lat))**2
    b=(6357000*math.sin(lat))**2
    c=a*(6378000**2)
    d=b*(6357000**2)
    geo_distance=math.sqrt((c+d)/(a+b))
    print(sub_latlon[0],sub_latlon[1],geo_distance)'''
    return sub_latlon[0],sub_latlon[1]

'''0 SOLAR SYSTEM BARYCENTER, 1 MERCURY BARYCENTER, 2 VENUS BARYCENTER, 3 EARTH BARYCENTER, 4 MARS BARYCENTER,
5 JUPITER BARYCENTER, 6 SATURN BARYCENTER, 7 URANUS BARYCENTER, 8 NEPTUNE BARYCENTER, 9 PLUTO BARYCENTER,
10 SUN, 199 MERCURY, 299 VENUS, 301 MOON, 399 EARTH'''

#二分法迭代求天象时间
def iteration(jd,sta,dt):#jd：要求的开始时间，sta：不同的状态函数,dt:初始时间步长
    s1=sta(jd)#初始状态
    s0=s1
    while True:
        jd=ts.tdb_jd(jd.tdb+dt)#改变时间
        s=sta(jd)
        if s0!=s:
            s0=s
            dt=-dt/2#使时间改变量折半减小
        if abs(dt)<0.1/86400.0 and s!=s1:#s!=s1是为了让求得的时间在天象发生之后
            break
    return jd

#初亏，复圆
#def external_penumbra_contact(jd):
def partial_eclipse(jd):
    delt,ratio,ET=tangent_point(jd,0)
    #print("偏食",ratio)
    if delt<0:#初亏之前或者复圆之后
        return 0
    else:
        return 1

#全食开始（食既），结束（生光）
def total_eclipse(jd):
    delt,ratio,ET=tangent_point(jd,1)
    #print("全食",ratio)
    if delt<0 or ratio<0:#不满足全食的条件只有一种（日食整体概况而言，角度和距离要都不满足，某个点来看只有角度条件）
        return 0
    else:
        return 1

#环食开始，结束
def annular_eclipse(jd):
    delt,ratio,ET=tangent_point(jd,2)
    #print("环食",ratio)
    if delt<0 or ratio>0:#不满足环食的条件有两种（日食整体概况而言，距离或者角度不满足一个即可，某个点来看只有角度条件）
        return 0
    else:
        return 1

#计算食甚时间
#计算食分，偏食和没有中心食发生的全食和环食都要计算太阳和地球的切点，也就是日出或者日落食甚的地点
def magnitude_theta(E_T,E_S,E_M):#E_T,E_S,E_M分别是地球中心到表面一点，到太阳质心，到月亮质心的矢量，返回从地表T点看太阳月亮的夹角
    T_S=E_S-E_T
    T_M=E_M-E_T
    thetaSM=diancheng(T_S,T_M)
    T_Slength=math.sqrt(T_S[0]**2+T_S[1]**2+T_S[2]**2)
    T_Mlength=math.sqrt(T_M[0]**2+T_M[1]**2+T_M[2]**2)
    thetaS=math.asin(rs/T_Slength)
    thetaM=math.asin(rm/T_Mlength)
    return thetaS,thetaM,thetaSM

def partial_non_central_mag(E_A,E_B,E_S,E_M,a,b,jd):#求偏食和没有中心食发生的全食和环食的食分，先求出太阳质心在地心椭圆的切点
    x=E_S[0]*E_A[0]+E_S[1]*E_A[1]+E_S[2]*E_A[2]#太阳质心在椭圆X轴投影
    y=E_S[0]*E_B[0]+E_S[1]*E_B[1]+E_S[2]*E_B[2]#太阳质心在椭圆Y轴投影
    delta=math.sqrt((a*y*y)**2+(b*x*y)**2-(b*a*y)**2)
    x1=(a**2*(b**2-delta))/((a*y)**2+(b*x)**2)
    y11=b/a*math.sqrt(a**2-x1**2)
    y12=-b/a*math.sqrt(a**2-x1**2)
    if abs(-(b/a)**2*x1/y11-(x-x1)/(y-y11))<abs(-(b/a)**2*x1/y12-(x-x1)/(y-y12)):#得到一个切点的x值，对应两个y值，找到切线斜率一致的那个才是
        y1=y11
    else:
        y1=y12
    E_T1=E_A*x1+E_B*y1
    thetaS1,thetaM1,thetaSM1=magnitude_theta(E_T1,E_S,E_M)
    if thetaS1+thetaM1>thetaSM1:
        mag=(thetaS1+thetaM1-thetaSM1)/(2*thetaS1)
        latlon=gcrs2latlon(E_T1,jd)
        return mag,latlon
    else:
        x2=(a**2*(b**2+delta))/((a*y)**2+(b*x)**2)
        y21=b/a*math.sqrt(a**2-x2**2)
        y22=-b/a*math.sqrt(a**2-x2**2)
        if abs(-(b/a)**2*x2/y21-(x-x2)/(y-y21))<abs(-(b/a)**2*x2/y22-(x-x2)/(y-y22)):#得到一个切点的x值，对应两个y值，找到切线斜率一致的那个才是
            y2=y21
        else:
            y2=y22
        E_T2=E_A*x2+E_B*y2
        thetaS2,thetaM2,thetaSM2=magnitude_theta(E_T2,E_S,E_M)
        mag=(thetaS2+thetaM2-thetaSM2)/(2*thetaS2)
        latlon=gcrs2latlon(E_T2,jd)
        return mag,latlon

def magnitude(jd,flag):
    E_S,E_M,E_P=body_vector(jd,4)
    O_E,O_M,E_A,E_B,O_X,a,b=ellipse(jd,flag)
    if flag==0:#偏食
        mag,latlon=partial_non_central_mag(E_A,E_B,E_S,E_M,a,b,jd)
    else:#全食或者环食
        delt,ratio,E_T=tangent_point(jd,3)
        if delt>0:#有中心食（食甚时月亮中心和太阳中心重合，日月连线在地表有交点）发生
            thetaS,thetaM,thetaSM=magnitude_theta(E_T,E_S,E_M)
            mag=math.tan(thetaM)/math.tan(thetaS)
            latlon=gcrs2latlon(E_T,jd)
            #print(thetaSM,thetaS,thetaM)
        else:#没有中心食发生
            mag,latlon=partial_non_central_mag(E_A,E_B,E_S,E_M,a,b,jd)
    return mag,latlon

#计算视赤道坐标和视黄道坐标
def celestial_coor(jd,n):
    earth = planets['earth']
    apparent=earth.at(jd).observe(planets[n]).apparent()
    lon, lat, distance = apparent.radec(epoch='date')#求太阳的视赤经视赤纬和距离（epoch设为所求时间）
    e_lat, e_lon, e_distance = apparent.ecliptic_latlon(epoch='date')#求太阳的视黄纬视黄经和距离（epoch设为所求时间）
    return e_lon._degrees*math.pi/180.0,e_lat._degrees*math.pi/180.0,lon._degrees*math.pi/180.0,lat._degrees*math.pi/180.0#返回天体的视赤经/黄经和视赤纬/黄纬，单位为弧度

#判断∠EOM在增大还是减小，进而求∠EOM的极大值或者极小值时间（需要和黄经值结合判断）
def dtheta(jd):
    O1_E0,O1_M0,E_P0=body_vector(jd,0)
    O1_E,O1_M,E_P=body_vector(ts.tdb_jd(jd.tdb+0.1/86400),0)
    thetaEM0_O1=math.acos((O1_E0[0]*O1_M0[0]+O1_E0[1]*O1_M0[1]+O1_E0[2]*O1_M0[2])/(math.sqrt(O1_E0[0]**2+O1_E0[1]**2+O1_E0[2]**2)*math.sqrt(O1_M0[0]**2+O1_M0[1]**2+O1_M0[2]**2)))
    thetaEM1_O1=math.acos((O1_E[0]*O1_M[0]+O1_E[1]*O1_M[1]+O1_E[2]*O1_M[2])/(math.sqrt(O1_E[0]**2+O1_E[1]**2+O1_E[2]**2)*math.sqrt(O1_M[0]**2+O1_M[1]**2+O1_M[2]**2)))
    if thetaEM0_O1<thetaEM1_O1:#∠EOM在增大
        return 0
    else:
        return 1

#给定一个时间，求下一次∠EOM最小的时刻（接近满月的那个时刻）
def next_min_thetaEM(jd):
    t=jd
    while True:
        t=iteration(t,dtheta,3)#一次极值到下一次极值要1/4个月左右，3天足够小，不至于跳过一次极值
        sun_coor=celestial_coor(t,10)
        moon_coor=celestial_coor(t,301)
        if abs(abs(sun_coor[0]-moon_coor[0]))*180/math.pi<5:#新月时刻日月黄经差为0
            return t

#给定一个时间，求下次月食的食甚时刻
def greatest_eclipse(jd):
    while True:
        t=next_min_thetaEM(jd)
        f1=partial_eclipse(t)
        f2=total_eclipse(t)
        f3=annular_eclipse(t)
        
        if f1==1:
            # 计算食分
            if f2==1 or f3==1:
                mag,latlon=magnitude(t,1)
            else:
                mag,latlon=magnitude(t,0)
            
            # 添加食分阈值检查：只有食分大于0.01才认为是真正的日食
            if mag > 0.01:
                if f2==1:
                    return t,1,mag,latlon
                elif f3==1:
                    return t,2,mag,latlon
                else:
                    return t,0,mag,latlon
            else:
                # 食分太小，不是真正的日食，继续查找下一个
                print(f"忽略食分过小的日食: {mag:.4f}")
        
        jd=ts.tdb_jd(t.tdb+20)

#计算jd时间开始接下来的num次日食时间
def solar_eclipse(jd,num):
    eclipse_list = []
    for i in range(num):
        # 食甚
        t5,flag,mag,latlon5=greatest_eclipse(jd)

        # 简化输出
        if flag == 0:
            eclipse_type = "日偏食"
        elif flag == 1:
            eclipse_type = "日全食"
        elif flag == 2:
            eclipse_type = "日环食"
        else:
            eclipse_type = "全环食"
            
        time_str = ts.tdb_jd(t5.tdb+1/3).utc_strftime(format='%Y-%m-%d %H:%M:%S')
        print(f"食甚时间: {time_str}, 类型: {eclipse_type}, 食分: {mag:.3f}")
        
        # 添加到返回列表
        eclipse_list.append({
            'time': time_str,
            'type': eclipse_type,
            'magnitude': mag,
            'latitude': latlon5[0],
            'longitude': latlon5[1]
        })
        
        jd=ts.tdb_jd(t5.tdb+25)#一般一次月食到下次再发生至少一个月的时间
    
    return eclipse_list

def calculate_future_eclipses(start_time=None, years=5):
    """
    计算未来指定年数的日食信息
    
    Args:
        start_time: 起始时间，格式为 'YYYY-MM-DD'，默认为当前时间
        years: 计算未来多少年的日食，默认为5年
    
    Returns:
        list: 日食信息列表，每个元素包含时间、类型、食分等信息
    """
    if start_time:
        try:
            year, month, day = map(int, start_time.split('-'))
            jd = ts.tt(year, month, day, 12, 0, 0)
        except ValueError:
            print("输入格式错误，使用当前时间")
            jd = get_ts_now()
    else:
        jd = get_ts_now()
    
    # 估算未来years年内的日食次数（每年约2-5次）
    num_eclipses = years * 3  # 保守估计
    
    print(f"计算未来{years}年内的日食...")
    print("="*50)
    
    eclipses = solar_eclipse(jd, num_eclipses)
    return eclipses

def main():
    print("日食计算程序")
    print("请输入起始时间（格式：YYYY-MM-DD），或直接按回车使用当前时间：")
    user_input = input().strip()
    
    if user_input:
        start_time = user_input
    else:
        start_time = None
    
    eclipses = calculate_future_eclipses(start_time, 5)
    
    print("\n计算完成！")
    return eclipses

if __name__ == "__main__":
    main()