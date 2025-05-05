import time
import math
import os
import gc
import sys

from media.sensor import *
from media.display import *
from media.media import *

import lcd
DETECT_WIDTH = lcd.DETECT_WIDTH
DETECT_HEIGHT = lcd.DETECT_HEIGHT

lcd_screen = lcd.init_lcd()

# 定义可用的标签族
tag_families = 0
tag_families |= image.TAG16H5  # 4x4 方形标签
tag_families |= image.TAG25H7   # 5x7 方形标签
tag_families |= image.TAG25H9   # 5x9 方形标签
tag_families |= image.TAG36H10  # 6x10 方形标签
tag_families |= image.TAG36H11  # 6x11 方形标签（默认）
tag_families |= image.ARTOOLKIT # ARToolKit 标签

# 函数: 获取标签族的名称
def family_name(tag):
    family_dict = {
        image.TAG16H5: "TAG16H5",
        image.TAG25H7: "TAG25H7",
        image.TAG25H9: "TAG25H9",
        image.TAG36H10: "TAG36H10",
        image.TAG36H11: "TAG36H11",
        image.ARTOOLKIT: "ARTOOLKIT",
    }
    return family_dict.get(tag.family(), "未知标签族")

sensor = None

try:
    # construct a Sensor object with default configure
    sensor = Sensor(width = DETECT_WIDTH, height = DETECT_HEIGHT)
    # sensor reset
    sensor.reset()
    # set hmirror
    sensor.set_hmirror(True)
    # sensor vflip
    sensor.set_vflip(True)

    # set chn0 output size
    sensor.set_framesize(width = DETECT_WIDTH, height = DETECT_HEIGHT)
    # set chn0 output format
    sensor.set_pixformat(Sensor.GRAYSCALE)

    sensor.set_framesize(w =320, h =240,chn=CAM_CHN_ID_1)
    sensor.set_pixformat(Sensor.RGB565,chn=CAM_CHN_ID_1)
    # init media manager
    MediaManager.init()
    # sensor start run
    sensor.run()
    fps = time.clock()
    while True:
        fps.tick()

        # 检查是否应该退出
        os.exitpoint()

        img = sensor.snapshot()
        img_show = sensor.snapshot(chn=CAM_CHN_ID_1)
        for tag in img.find_apriltags(families=tag_families):
            img_show.draw_rectangle([v for v in tag.rect()], color=(0, 255, 0))
        #            img_show.draw_cross(tag.cx(), tag.cy(), color=(0, 255, 0))
            # Replace print with draw_string_advanced
            tag_info = "二维码: %s, ID: %d, 旋转角度: %.1f" % (
                family_name(tag),
                tag.id(),
                (180 * tag.rotation()) / math.pi
            )
            img_show.draw_string_advanced(0, 20, 15, tag_info, color=(0, 255, 255))

        img_show.draw_string_advanced(0, 0, 15, 'FPS: '+str("%.2f"%(fps.fps())), color=(255, 255, 255))

        lcd_screen.show(img_show)

        gc.collect()
except KeyboardInterrupt:
    print("用户停止")
except BaseException as e:
    print(f"异常 '{e}'")
finally:
    # 停止 sensor
    if isinstance(sensor, Sensor):
        sensor.stop()
    # 销毁 display
    Display.deinit()

    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)

    # 释放媒体缓冲区
    MediaManager.deinit()
