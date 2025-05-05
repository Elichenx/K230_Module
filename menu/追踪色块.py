import time, image, os, gc, sys
from machine import FPIOA, Pin, SPI
from media.sensor import *
from media.display import *
from media.media import *
import lcd
from machine import I2C_Slave, Timer
import random
import lcd
from Aimodel import PipeLine, ScopedTiming
from SendData import IIC_Manager

# 初始化IIC管理器
iic_manager = IIC_Manager()

DETECT_WIDTH = lcd.DETECT_WIDTH
DETECT_HEIGHT = lcd.DETECT_HEIGHT

lcd_screen = lcd.init_lcd()
# 颜色识别阈值 (L Min, L Max, A Min, A Max, B Min, B Max) LAB模型
# 阈值元组
thresholds = [
    (15, 45, 25, 55, 5, 35),    # 黄色阈值
    (35, 65, 0, 30, 35, 65),  # 绿色阈值
    (10, 40, -5, 25, -65, -35)  # 蓝色阈值
]

colors1 = [(255, 0, 0), (255, 255, 0), (0, 0, 255)]
colors2 = ['红', '黄', '蓝']
sensor = None
data = None
crc2 = None
last_deflection_angle=0

last_data = None
last_crc2 = None
last_widest_blob = None
last_color_index = 0

#def handle_send_data(timer):
#    global data
#    if data is None:
#        return
#    try:
#        iic_manager.send_data(data[0], data[1], data[2], data[3])
#    except Exception as e:
#        print(f"发送数据失败: {e}")

def camera_init():
    global sensor

    sensor = Sensor(width=320, height=240)
    sensor.reset()
    sensor.set_hmirror(True)
    sensor.set_vflip(True)
    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.set_pixformat(Sensor.RGB565)

    # 使用虚拟显示输出，不使用 IDE 显示
#    Display.init(Display.VIRT, width= DETECT_WIDTH, height=DETECT_HEIGHT, fps=100, to_ide=False)

    # 初始化媒体管理器
    MediaManager.init()

    # 启动传感器
    sensor.run()

def camera_deinit():
    global sensor
    # 停止传感器运行
    sensor.stop()

    # 反初始化显示
    Display.deinit()

    # 设置退出点以允许休眠
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)

    # 短暂休眠
    time.sleep_ms(100)

    # 释放媒体缓冲区
    MediaManager.deinit()

#合并色块
def merge_blobs(blobs, max_distance):

    merged = []

    for blob in blobs:
        merged_flag = False
        for m in merged:
            # 计算中心点距离
            dx = blob.cx() - m['cx']
            dy = blob.cy() - m['cy']
            distance = (dx**2 + dy**2)**0.5
            if distance < max_distance:
                # 更新边界框
                m['x'] = min(m['x'], blob.x())
                m['y'] = min(m['y'], blob.y())
                m['w'] = max(m['x'] + m['w'], blob.x() + blob.w()) - m['x']
                m['h'] = max(m['y'] + m['h'], blob.y() + blob.h()) - m['y']
                # 更新中心点
                m['cx'] = (m['x'] + m['w'] // 2)
                m['cy'] = (m['y'] + m['h'] // 2)
                merged_flag = True
                break
        if not merged_flag:
            merged.append({
                'x': blob.x(),
                'y': blob.y(),
                'w': blob.w(),
                'h': blob.h(),
                'cx': blob.cx(),
                'cy': blob.cy()
            })
    return merged

def capture_picture():
    fps = time.clock()
    global last_data, last_widest_blob, last_color_index

    while True:
        fps.tick()
        os.exitpoint()

        img = sensor.snapshot()
        widest_blob = None
        max_width = 0
        max_color_index = 0
        found_blob = False

        # 遍历所有颜色
        for i in range(3):
            blobs = img.find_blobs([thresholds[i]], x_stride=25, y_stride=25)

            if blobs:
                merged_blobs = merge_blobs(blobs, max_distance=50)

                # 在当前颜色的合并色块中找最宽的
                for m in merged_blobs:
                    if m['w'] > max_width:
                        max_width = m['w']
                        widest_blob = m
                        max_color_index = i
                        found_blob = True

                    # 绘制所有检测到的色块
                    img.draw_rectangle(m['x'], m['y'], m['w'], m['h'], thickness=2, color=colors1[i])

                    relative_x = m['cx']
                    relative_y = m['cy']
                    coord_text = f"({relative_x},{relative_y})"
                    width_text = f"W:{m['w']}"  # 添加宽度显示

                    text_x = max(0, min(m['cx'] - 10, DETECT_WIDTH - 60))
                    text_y = max(0, m['cy'] - 10)

                    img.draw_string_advanced(text_x, text_y, 15, coord_text, color=(255, 255, 255))
                    img.draw_string_advanced(text_x, text_y + 20, 15, width_text, color=(255, 255, 255))

        # 数据发送逻辑
        global data, crc2
        if found_blob:  # 如果找到新的色块
            # 直接存储原始数据
            data = [
                1,  # color_data
                widest_blob['cx'],  # cx_data
                widest_blob['cy'],  # cy_data
                widest_blob['w']    # width_data
            ]

            last_data = data.copy()  # 创建数据副本
            last_widest_blob = dict(widest_blob)
            last_color_index = max_color_index

            # 在最宽色块上标注
            img.draw_string_advanced(widest_blob['x'], widest_blob['y'] - 20, 15,
                          "最宽色块", color=(255, 255, 255))
        else:  # 如果没找到色块，使用上一次的参数
            if last_data is not None:
                data = last_data
                # 绘制上一次检测到的位置（用虚线或不同颜色表示）
                if last_widest_blob:
                    img.draw_rectangle(last_widest_blob['x'], last_widest_blob['y'],
                                    last_widest_blob['w'], last_widest_blob['h'],
                                    thickness=1, color=(128, 128, 128))  # 灰色表示上一次位置
                    img.draw_string_advanced(last_widest_blob['x'], last_widest_blob['y'] - 20, 15,
                                  "上一次位置", color=(128, 128, 128))

        if data is not None:
            iic_manager.send_data(data[0], data[1], data[2], data[3])
        img.draw_string_advanced(0, 0, 15, 'FPS: '+str("%.3f"%(fps.fps())), color=(255, 255, 255))
        lcd_screen.show(img)
        img = None
        gc.collect()

try:
    print("初始化摄像头...")
    camera_init()
    camera_is_init = True

#    data_timer = Timer(-1)
#    data_timer.init(period=10, mode=Timer.PERIODIC, callback=handle_send_data)

    data = None  # 初始化全局变量
    crc2 = None  # 初始化全局变量

    capture_picture()
except Exception as e:
    print(f"发生异常: {e}")
finally:
    if 'camera_is_init' in locals() and camera_is_init:
        print("反初始化摄像头...")
        camera_deinit()

