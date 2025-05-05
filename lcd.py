import time
import image
import os
import gc
import sys
from machine import FPIOA, Pin, SPI, SPI_LCD, PWM
from media.sensor import *
from media.display import *
from media.media import *

# 定义屏幕尺寸常量，并在模块中导出
DETECT_WIDTH = ALIGN_UP(320, 16)
DETECT_HEIGHT = 240

# 使用全局变量存储 LCD 对象和背光PWM对象，确保只初始化一次
lcd_screen = None
pwm_backlight = None

def init_lcd():
    """
    初始化并配置 SPI_LCD 屏幕，返回 lcd 对象。
    如果已经初始化过，则直接返回已有的 lcd 对象。
    """
    global lcd_screen, pwm_backlight
    if lcd_screen is not None:
        return lcd_screen

    try:
        fpioa = FPIOA()
        # 配置 CS 引脚 (GPIO 19)
        fpioa.set_function(19, FPIOA.GPIO19)
        pin_cs = Pin(19, Pin.OUT, pull=Pin.PULL_NONE, drive=15)
        pin_cs.value(1)

        # 配置 DC 引脚 (GPIO 20)
        fpioa.set_function(20, FPIOA.GPIO20)
        pin_dc = Pin(20, Pin.OUT, pull=Pin.PULL_NONE, drive=15)
        pin_dc.value(1)

        # 配置 RESET 引脚 (GPIO 14)
        fpioa.set_function(14, FPIOA.GPIO14, pu=1)
        pin_rst = Pin(14, Pin.OUT, pull=Pin.PULL_UP, drive=15)

        # 配置 SPI 接口引脚 (SCL 和 MOSI)
        fpioa.set_function(15, fpioa.QSPI0_CLK)  # SCL
        fpioa.set_function(16, fpioa.QSPI0_D0)   # MOSI

        # 配置背光引脚为PWM输出
        fpioa.set_function(25, FPIOA.PWM5)
        # 初始化PWM并存储到全局变量
        pwm_backlight = PWM(5, 5000, 50, enable=True)

        # 初始化 SPI 接口
        spi1 = SPI(1, baudrate=30_000_000, polarity=1, phase=1, bits=8)

        # 创建 SPI_LCD 对象并配置屏幕参数
        lcd_screen = SPI_LCD(spi1, pin_dc, pin_cs, pin_rst)
        lcd_screen.configure(320, 240, hmirror=False, vflip=True, bgr=False)
        lcd_screen.init()

        return lcd_screen

    except Exception as e:
        print("LCD 初始化失败:", e)
        lcd_screen = None
        pwm_backlight = None
        return lcd_screen

def get_lcd():
    """
    获取已经初始化的 LCD 对象。如果尚未初始化，则先初始化。
    """
    if lcd_screen is None:
        return init_lcd()
    return lcd_screen

def set_backlight(brightness):
    """
    调整屏幕背光亮度，取值范围 0~100（0 为最暗，100 为最亮）。
    """
    global pwm_backlight
    if pwm_backlight is not None:
        # 限制亮度在 0~100
        brightness = max(0, min(100, brightness))
        # 先禁用 PWM，修改占空比后再启用，避免中间闪烁
        pwm_backlight.enable(False)
        pwm_backlight.duty(brightness)
        pwm_backlight.enable(True)
    else:
        print("背光 PWM 未初始化，无法调节亮度")
        # 尝试重新初始化LCD和PWM
        init_lcd()

# 在模块导入时自动初始化 LCD
lcd_screen = init_lcd()
