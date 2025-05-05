#通过按键采集颜色阈值，按键切换模式
import time, image, os, gc, sys, random
from machine import FPIOA, Pin, SPI, SPI_LCD
from media.sensor import *
from media.display import *
from media.media import *
import lcd

DETECT_WIDTH = lcd.DETECT_WIDTH
DETECT_HEIGHT = lcd.DETECT_HEIGHT

lcd_screen = lcd.init_lcd()

thresholds = []  # 存储采集到的颜色阈值
display_colors = []  # 每个识别颜色对应的显示颜色
current_color_index = 0  # 当前采集的颜色序号
is_detecting = False    # 是否处于识别模式

def camera_init():
    global sensor

    sensor = Sensor(width=320, height=240)
    sensor.reset()
    sensor.set_hmirror(True)
    sensor.set_vflip(True)
    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.set_pixformat(Sensor.RGB565)
#    Display.init(Display.VIRT, width=320, height=240) #通过IDE缓冲区显示图像
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


def get_most_common_lab(img, x, y, w, h, samples=3, tolerance=10):
    """
    获取ROI区域内最常见的LAB值，并根据tolerance设置阈值范围
    samples: 采样次数
    tolerance: LAB各分量的容差范围
    """
    lab_counts = {}  # 用于统计LAB值出现次数

    # 多次采样
    for _ in range(samples):
        temp_img = sensor.snapshot()
        for row in range(y, y + h):
            for col in range(x, x + w):
                r, g, b = temp_img.get_pixel(col, row)
                l, a, b = image.rgb_to_lab((r, g, b))
                # 将LAB值离散化，减少统计复杂度
                l = l // 5 * 5  # 每5个单位作为一组
                a = a // 5 * 5
                b = b // 5 * 5
                lab = (l, a, b)
                lab_counts[lab] = lab_counts.get(lab, 0) + 1

    if not lab_counts:
        return (0, 100, -128, 127, -128, 127)

    # 找出出现次数最多的LAB值
    most_common_lab = max(lab_counts.items(), key=lambda x: x[1])[0]
    l, a, b = most_common_lab

    # 设置阈值范围
    l_min = max(0, l - tolerance)
    l_max = min(100, l + tolerance)
    a_min = max(-128, a - tolerance)
    a_max = min(127, a + tolerance)
    b_min = max(-128, b - tolerance)
    b_max = min(127, b + tolerance)

    threshold = (
        int(l_min), int(l_max),
        int(a_min), int(a_max),
        int(b_min), int(b_max)
    )

    return threshold

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
    threshold = None
    global current_color_index, is_detecting, thresholds, display_colors

    while True:
        fps.tick()
        os.exitpoint()
        global sensor

        img = sensor.snapshot()

        if not is_detecting:
            # 采集模式
            center_x = (DETECT_WIDTH // 2) - 30
            center_y = (DETECT_HEIGHT // 2) - 30
            w, h = 30, 30

            # 绘制ROI方框，使用白色
            img.draw_rectangle(center_x, center_y, w, h, color=(255, 255, 255), thickness=2)

            # 按键1被按下时获取新阈值和颜色
            if key1_pin.value() == 0:
                # 获取ROI中心点的颜色值
                center_color = img.get_pixel(center_x + w//2, center_y + h//2)
                display_colors.append(center_color)  # 存储实际颜色

                threshold = get_most_common_lab(img, center_x, center_y, w, h, samples=3, tolerance=10)
                thresholds.append(threshold)
                current_color_index += 1

                time.sleep_ms(20)  # 防止重复触发

            # 按键2被按下时切换到识别模式
            if key2_pin.value() == 1 and len(thresholds) > 0:
                is_detecting = True
                time.sleep_ms(200)

            # 显示提示信息
            img.draw_string_advanced(0, 0, 15, f"请采集颜色{current_color_index + 1} 已采集:{len(thresholds)}个", color=(255, 255, 255))
            if threshold:
                # 显示当前阈值
                img.draw_string_advanced(0, 30, 15, "得到LAB范围: "+str(threshold), color=(255, 255, 255))
        else:
            # 识别模式
            for i in range(len(thresholds)):
                blobs = img.find_blobs([thresholds[i]], x_stride=25, y_stride=25)

                if blobs:
                    merged_blobs = merge_blobs(blobs, max_distance=50)

                    for m in merged_blobs:
                        # 使用采集时获取的实际颜色绘制矩形
                        img.draw_rectangle(m['x'], m['y'], m['w'], m['h'], thickness=2, color=display_colors[i])

                        # 在右边显示宽度
                        width_text = f"W:{m['w']}"
                        img.draw_string_advanced(m['x'] + m['w'], m['y'] + m['h']//2, 15, width_text, color=(255, 255, 255))

                        # 在下边显示高度
                        height_text = f"H:{m['h']}"
                        img.draw_string_advanced(m['x'] + m['w']//2, m['y'] + m['h'], 15, height_text, color=(255, 255, 255))

                        # 显示颜色编号和相对坐标
                        relative_x = 160 - m['cx']
                        relative_y = 120 - m['cy']
                        coord_text = f"C{i+1}({relative_x},{relative_y})"

                        text_x = m['cx'] - 10
                        text_y = m['cy'] - 10

                        if text_x + 50 > DETECT_WIDTH:
                            text_x = DETECT_WIDTH - 60
                        if text_y < 0:
                            text_y = 0

                        img.draw_string_advanced(text_x, text_y, 15, coord_text, color=(255, 255, 255))

            # 按键2被按下时切换回采集模式
            if key2_pin.value() == 1:
                is_detecting = False
                thresholds = []  # 清空已采集的阈值
                display_colors = []  # 清空显示颜色
                current_color_index = 0
                time.sleep_ms(200)

        # 显示FPS
        img.draw_string_advanced(0, DETECT_HEIGHT-30, 15, 'FPS: '+str("%.2f"%(fps.fps())), color=(255, 255, 255))
        lcd_screen.show(img)
        gc.collect()

try:
    key1_pin = Pin(18, Pin.IN)  # 采集颜色的按键
    key2_pin = Pin(64, Pin.IN)  # 切换模式的按键

    camera_init()
    camera_is_init = True

    capture_picture()


except Exception as e:
    print(f"发生异常: { e}")
finally:
    if camera_is_init:
        print("反初始化摄像头...")
        camera_deinit()

