import time, image, os, gc, sys
from machine import FPIOA, Pin, SPI, SPI_LCD
from media.sensor import *
from media.display import *
from media.media import *
import lcd

DETECT_WIDTH = lcd.DETECT_WIDTH
DETECT_HEIGHT = lcd.DETECT_HEIGHT

lcd_screen = lcd.init_lcd()
# 颜色识别阈值 (L Min, L Max, A Min, A Max, B Min, B Max) LAB模型
# 下面的阈值元组是用来识别 黄色、绿色、蓝色三种颜色，你可以根据需要进行调整。
thresholds = [
    (49, 65, 13, 63, 35, 79),    # 黄色阈值
    (25, 39, -42, -19, 7, 121),  # 绿色阈值
    (41, 67, -42, 12, -65, -24)  # 蓝色阈值
]

colors1 = [(255, 255, 0), (0, 255, 0), (0, 0, 255)]
colors2 = ['黄', '绿', '蓝']
sensor = None

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
def merge_blobs(blobs, max_distance=60):

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
    while True:
        fps.tick()
        try:
            os.exitpoint()
            global sensor
            img = sensor.snapshot()

            for i in range(3):
                # 查找符合阈值的色块
                blobs = img.find_blobs([thresholds[i]], x_stride=25, y_stride=25)

                if blobs:
                    # 合并色块
                    merged_blobs = merge_blobs(blobs, max_distance=50)  # max_distance可根据实际情况调整

                    for m in merged_blobs:
                        # 绘制矩形框
                        img.draw_rectangle(m['x'], m['y'], m['w'], m['h'], thickness=2, color=colors1[i])

                        # 绘制中心坐标
                        coord_text = f"({m['cx']},{m['cy']})"
                        text_x = m['cx'] - 10  # 坐标文本的 x 位置
                        text_y = m['cy'] - 10 # 坐标文本的 y 位置

                        # 确保文本位置不超出屏幕边界
                        if text_x + 50 > DETECT_WIDTH:
                            text_x = DETECT_WIDTH - 60
                        if text_y < 0:
                            text_y = 0

                        img.draw_string(text_x, text_y, coord_text, color=(255, 255, 255), scale=1.5)

            # 显示 FPS 信息
            img.draw_string_advanced(0, 0, 15, 'FPS: '+str("%.3f"%(fps.fps())), color=(255, 255, 255))

            # 将结果显示到屏幕
            lcd_screen.show(img)
            img = None

            gc.collect()

        except KeyboardInterrupt as e:
            print("用户停止程序: ", e)
            break
        except BaseException as e:
            print(f"发生异常: {e}")
            break


#    os.exitpoint(os.EXITPOINT_ENABLE)
##    camera_is_init = False
try:
#    print("初始化摄像头...")
    camera_init()
    camera_is_init = True
#    print("开始捕捉图片...")
    capture_picture()
except Exception as e:
    print(f"发生异常: {e}")
finally:
    if camera_is_init:
        print("反初始化摄像头...")
        camera_deinit()

