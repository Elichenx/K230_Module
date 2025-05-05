import time, os, sys
from machine import Pin
from machine import FPIOA
from media.sensor import *  #导入sensor模块，使用摄像头相关接口
from media.display import * #导入display模块，使用display相关接口
from media.media import *   #导入media模块，使用meida相关接口
import image                #导入Image模块，使用Image相关接口
import lcd
DETECT_WIDTH = lcd.DETECT_WIDTH
DETECT_HEIGHT = lcd.DETECT_HEIGHT

lcd_screen = lcd.init_lcd()
# 实例化FPIOA
fpioa = FPIOA()


# 构造GPIO对象
key0 = Pin(64, Pin.IN, pull=Pin.PULL_UP, drive=7)
#key1 = Pin(0, Pin.IN, pull=Pin.PULL_UP, drive=7)

try:
    try:
        os.mkdir("/sdcard/PHOTO")
    except Exception:
        pass

    # 添加照片计数器和显示信息变量
    photo_counter = 0
    display_text = "按下按键开始拍照"

    sensor = Sensor(width=1920, height=1080)
    sensor.reset()
    sensor.set_hmirror(True)
    sensor.set_vflip(True)
    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.set_pixformat(Sensor.RGB565)

    # 设置通道1输出格式，用于图像保存
    sensor.set_framesize(Sensor.SXGAM, chn=CAM_CHN_ID_1)  # 输出帧大小SXGAM(1280x960)
    sensor.set_pixformat(Sensor.RGB565, chn=CAM_CHN_ID_1) # 设置输出图像格式，选择通道1

    # 初始化LCD显示器，同时IDE缓冲区输出图像,显示的数据来自于sensor通道0。
#    Display.init(Display.VIRT, width = 640, height = 480, to_ide = False)
    MediaManager.init()  # 初始化media资源管理器

    sensor.run()  # 启动sensor

    while True:
        os.exitpoint() # 检测IDE中断
        img =None
        img_show = sensor.snapshot(chn=CAM_CHN_ID_0) # 从通道1捕获一张图
        img_show.lens_corr(strength=1.5)
        # 始终显示信息在左上角
        img_show.draw_string_advanced(0, 0, 13, display_text, color=(255, 255, 255))

        # 读取按键状态，并做相应的按键解释
        if key0.value() == 1:
            img = sensor.snapshot(chn=CAM_CHN_ID_1) # 从通道1捕获一张图
            img.lens_corr(strength=1.5)
            # 使用计数器生成文件名
            filename = "/sdcard/PHOTO/photo_{:04d}.jpg".format(photo_counter)
            img.save(filename)
            # 更新显示信息
            display_text = f" photo_{photo_counter:04d}.jpg已保存"
            print("KEY snapshot success - saved as:", filename)
            photo_counter += 1  # 增加计数器
            time.sleep_ms(500)  # 增加延迟防止连拍太快

        lcd_screen.show(img_show)
# IDE中断释放资源代码
except KeyboardInterrupt as e:
    print("user stop: ", e)
except BaseException as e:
    print(f"Exception {e}")
finally:
    # sensor stop run
    if isinstance(sensor, Sensor):
        sensor.stop()
    # deinit display
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # release media buffer
    MediaManager.deinit()
