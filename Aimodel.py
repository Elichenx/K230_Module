import os
import ujson
from media.sensor import *
from media.display import *
from media.media import *
from time import *
import nncase_runtime as nn
import ulab.numpy as np
import time
import utime
import image
import random
import gc
import sys

# 计时类，计算进入代码块和退出代码块的时间差
class ScopedTiming:
    def __init__(self, info="", enable_profile=True):
        self.info = info
        self.enable_profile = enable_profile

    def __enter__(self):
        if self.enable_profile:
            self.start_time = time.time_ns()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.enable_profile:
            elapsed_time = time.time_ns() - self.start_time
            print(f"{self.info} took {elapsed_time / 1000000:.2f} ms")

# PipeLine类
class PipeLine:
    def __init__(self,rgb888p_size=[],display_size=[],display_mode="lcd",debug_mode=0):
        # sensor给AI的图像分辨率
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 视频输出VO图像分辨率
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        # 视频显示模式，支持："lcd"，"hdmi"
        self.display_mode=display_mode
        # sensor对象
        self.sensor=None
        # osd显示Image对象
        self.osd_img=None
        self.debug_mode=debug_mode

    # PipeLine初始化函数
    def create(self,sensor=None,hmirror=None,vflip=None,VIRT=0):
        with ScopedTiming("init PipeLine",self.debug_mode > 0):
            os.exitpoint(os.EXITPOINT_ENABLE)
            nn.shrink_memory_pool()
            # 初始化并配置sensor
            brd=os.uname()[-1]

            self.sensor = Sensor(width=320, height=240,fps=90) if sensor is None else sensor

            self.sensor.reset()
            self.sensor.set_hmirror(True)
            self.sensor.set_vflip(True)

            if hmirror is not None and (hmirror==True or hmirror==False):
                self.sensor.set_hmirror(hmirror)
            if vflip is not None and (vflip==True or vflip==False):
                self.sensor.set_vflip(vflip)
            # 通道0直接给到显示VO，格式为YUV420
            self.sensor.set_framesize(w = self.display_size[0], h = self.display_size[1],chn=CAM_CHN_ID_0)
            self.sensor.set_pixformat(PIXEL_FORMAT_YUV_SEMIPLANAR_420,chn=CAM_CHN_ID_0)

            # 通道1，格式为RGB565
            self.sensor.set_framesize(w =320, h =240,chn=CAM_CHN_ID_1)
            self.sensor.set_pixformat(Sensor.RGB565,chn=CAM_CHN_ID_1)

            # 通道2给到AI做算法处理，格式为RGB888
            self.sensor.set_framesize(w = self.rgb888p_size[0], h = self.rgb888p_size[1], chn=CAM_CHN_ID_2)
            # set chn2 output format
            self.sensor.set_pixformat(PIXEL_FORMAT_RGB_888_PLANAR, chn=CAM_CHN_ID_2)

            # OSD图像初始化
            self.osd_img = image.Image(self.display_size[0], self.display_size[1], image.RGB565)

            sensor_bind_info = self.sensor.bind_info(x = 0, y = 0, chn = CAM_CHN_ID_2)
#            if VIRT:

##               Display.bind_layer(**sensor_bind_info, layer = Display.LAYER_VIDEO1)
#               Display.init(Display.VIRT,fps=100,to_ide = False)

            # media初始化
            MediaManager.init()
            # 启动sensor
            self.sensor.run()

    # 获取一帧图像数据，返回格式为ulab的array数据
    def get_frame(self):
        with ScopedTiming("get a frame",self.debug_mode > 0):
            frame = self.sensor.snapshot(chn=CAM_CHN_ID_2)
            input_np=frame.to_numpy_ref()
            return input_np

    # PipeLine销毁函数
    def destroy(self):
        with ScopedTiming("deinit PipeLine",self.debug_mode > 0):
            os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
            # stop sensor
            self.sensor.stop()
            # deinit lcd

            time.sleep_ms(50)
            # deinit media buffer
            MediaManager.deinit()
