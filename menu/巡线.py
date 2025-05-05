#模拟红外传感器巡线
import time, os, gc, sys, math

from media.sensor import *
from media.display import *
from media.media import *
from machine import Pin, FPIOA, Timer
import lcd
from Aimodel import PipeLine, ScopedTiming
from SendData import IIC_Manager

iic_manager = IIC_Manager()

DETECT_WIDTH = lcd.DETECT_WIDTH
DETECT_HEIGHT = lcd.DETECT_HEIGHT
lcd_screen = lcd.init_lcd()

last_angle =0
last_err =0

#用灰度值的最大值和最小值来作为阈值
GRAYSCALE_THRESHOLD = [(0, 70)]

# 定义大的感兴趣区域和模拟红外传感器区域
MAIN_ROI = (0, 80, 340, 60)  # x, y, w, h

# 将五个检测区域平均分布在主区域内
SENSOR_WIDTH = 50  # 每个检测区域的宽度
SENSOR_Y=80
SENSOR_POSITIONS = [
    (0, SENSOR_Y),      # 最左
    (70, SENSOR_Y),     # 左
    (140, SENSOR_Y),    # 中
    (210, SENSOR_Y),    # 右
    (280, SENSOR_Y),    # 最右
]

sensor = None

data = None
crc2 = None
angle =None

last_deflection_angle=0

#def handle_send_data(timer):
#    """定时发送数据回调函数"""
#    iic_manager.send_data(
#              angle
#           )

# 添加传感器状态组合的转向权重配置
TURN_WEIGHTS = {
    # 单个传感器检测到的情况
    "10000": -30,  # 最左侧，大角度左转
    "01000": -10,  # 左侧，小角度左转
    "00100": 0,    # 中间，直行
    "00010": 10,   # 右侧，小角度右转
    "00001": 30,   # 最右侧，大角度右转

    # 两个相邻传感器检测到的情况
    "11000": -24,  # 最左两个，中等角度左转
    "01100": -5,  # 左中，小角度左转
    "00110": 5,   # 中右，小角度右转
    "00011": 24,   # 最右两个，中等角度右转

    # 三个相邻传感器检测到的情况
    "11100": -32,  # 偏左转
    "01110": 0,    # 居中修正
    "00111": 32,   # 偏右转

    # 其他特殊情况
    "10001": 0,    # 两边都检测到，可能是十字路口
    "11110": -30,    # 左直角
    "01111": 30,    # 右直角
}

try:

    sensor = Sensor(width=320, height=240,fps=90)
    sensor.reset()
    sensor.set_hmirror(True)
    sensor.set_vflip(True)

    sensor.set_framesize(id=2,width = DETECT_WIDTH, height = DETECT_HEIGHT)
    sensor.set_pixformat(Sensor.GRAYSCALE)

    sensor.set_framesize(id=2,width = DETECT_WIDTH, height = DETECT_HEIGHT,chn=CAM_CHN_ID_1)
    sensor.set_pixformat(Sensor.RGB565,chn=CAM_CHN_ID_1)

    # use IDE as output
#    Display.init(Display.VIRT, width = DETECT_WIDTH, height = DETECT_HEIGHT, fps = 100)

    MediaManager.init()
    sensor.run()
    fps = time.clock()

#    data_timer = Timer(-1)
#    data_timer.init(period=10, mode=Timer.PERIODIC, callback=handle_send_data)

    while True:
        fps.tick()
        os.exitpoint()
        img = sensor.snapshot()
        show_img = sensor.snapshot(chn=CAM_CHN_ID_1)

        # 在大区域内寻找所有色块
        blobs = img.find_blobs(GRAYSCALE_THRESHOLD, roi=MAIN_ROI, merge=True)

        # 绘制主要感兴趣区域
        show_img.draw_rectangle(MAIN_ROI, color=(255, 255, 0))

        # 初始化传感器状态
        sensor_values = [0, 0, 0, 0, 0]

        if blobs:
            for blob in blobs:
                # 获取色块的边界
                x1 = blob.rect()[0]  # 左边界
                x2 = blob.rect()[0] + blob.rect()[2]  # 右边界
                cy = blob.cy()

                # 在每个检测到的色块周围画矩形
                show_img.draw_rectangle(blob.rect(), color=(0, 0, 255))

                # 遍历所有检测区域
                for i, (x, y) in enumerate(SENSOR_POSITIONS):
                    sensor_area_left = x
                    sensor_area_right = x + SENSOR_WIDTH

                    # 检查色块是否与检测区域有重叠
                    # 情况1：色块左边界在检测区域内
                    # 情况2：色块右边界在检测区域内
                    # 情况3：色块完全包含检测区域
                    if (sensor_area_left <= x1 <= sensor_area_right) or \
                       (sensor_area_left <= x2 <= sensor_area_right) or \
                       (x1 <= sensor_area_left and x2 >= sensor_area_right):
                        sensor_values[i] = 1
                        # 在重叠区域画十字
                        overlap_x = max(x1, sensor_area_left)
                        show_img.draw_cross(int(overlap_x), int(cy), color=(255, 0, 0))

        # 绘制所有检测区域，根据是否检测到色块显示不同颜色
        for i, (x, y) in enumerate(SENSOR_POSITIONS):
            color = (0, 255, 0) if sensor_values[i] else (255, 0, 0)
            show_img.draw_rectangle((x, y, SENSOR_WIDTH, 50), color=color)
            # 显示每个检测区域的编号
            show_img.draw_string_advanced(x + 20, y + 25, 15, str(i), color=(255, 255, 255))

        # 修改转向角度计算逻辑
        if any(sensor_values):
            # 将传感器状态转换为字符串键值
            sensor_key = ''.join(str(v) for v in sensor_values)

            # 获取预设的转向角度，如果没有预设则使用权重计算
            if sensor_key in TURN_WEIGHTS:
                deflection_angle = TURN_WEIGHTS[sensor_key]
            else:
                # 使用加权平均作为默认方案
                weighted_sum = 0
                sensors_detected = 0
                for i, value in enumerate(sensor_values):
                    if value:
                        weighted_sum += (i - 2) * 25
                        sensors_detected += 1
                deflection_angle = weighted_sum / sensors_detected

            # 平滑处理：与上一次角度进行插值
            if last_deflection_angle is not None:
                deflection_angle = 0.7 * deflection_angle + 0.3 * last_deflection_angle

            last_deflection_angle = deflection_angle
        else:
            # 如果没有检测到线，保持上一次的转向角度
            if last_deflection_angle is not None:
                deflection_angle = last_deflection_angle
            else:
                deflection_angle = 0


        angle = round(deflection_angle)
        if angle is not None:
            iic_manager.send_data(
                      angle
                   )
        # 显示传感器状态·
        sensor_status = ''.join(['1' if v else '0' for v in sensor_values])
        show_img.draw_string_advanced(0, 80, 15, f'Sensors: {sensor_status}', color=(255, 255, 255))

        # 显示当前状态和角度

        show_img.draw_string_advanced(0, 0, 15, 'FPS: '+str("%.2f"%(fps.fps())), color=(255, 255, 255))
        show_img.draw_string_advanced(0, 20, 15, 'angle: '+str(angle), color=(255, 255, 255))
        lcd_screen.show(show_img)
#        Display.show_image(show_img) #显示图片
        gc.collect()

#        print(fps.fps())
except KeyboardInterrupt as e:
    print(f"user stop")
    data_timer.deinit()
except BaseException as e:
    print(f"Exception '{e}'")
finally:

    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)

    # release media buffer
    MediaManager.deinit()
