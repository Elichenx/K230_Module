from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from random import randint
from media.media import *
from time import *
import nncase_runtime as nn
import ulab.numpy as np
import aidemo
import random
from media.sensor import * #导入sensor模块，使用摄像头相关接口
import time, image, os, gc, sys,ujson
import nncase_runtime as nn
from machine import FPIOA, Pin, SPI, SPI_LCD
import lcd
from Aimodel import PipeLine, ScopedTiming

DETECT_WIDTH = lcd.DETECT_WIDTH
DETECT_HEIGHT = lcd.DETECT_HEIGHT

lcd_screen = lcd.init_lcd()

# -----------------------------
# 下面是 TrackCropApp 类
# -----------------------------
class TrackCropApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, ratio_src_crop,
                 center_xy_wh, rgb888p_size=[320,240], display_size=[320,240], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path
        self.model_input_size = model_input_size
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0],16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0],16), display_size[1]]
        self.debug_mode = debug_mode
        self.CONTEXT_AMOUNT = 0.5
        self.ratio_src_crop = ratio_src_crop
        self.center_xy_wh = center_xy_wh
        self.pad_crop_params = []
        self.ai2d_pad = Ai2d(debug_mode)
        self.ai2d_pad.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        self.ai2d_crop = Ai2d(debug_mode)
        self.ai2d_crop.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        self.need_pad = False

    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            self.pad_crop_params = self.get_padding_crop_param()
            if (self.pad_crop_params[0] != 0 or
                self.pad_crop_params[1] != 0 or
                self.pad_crop_params[2] != 0 or
                self.pad_crop_params[3] != 0):
                self.need_pad = True
                self.ai2d_pad.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
                self.ai2d_pad.pad([0, 0, 0, 0,
                                   self.pad_crop_params[0],
                                   self.pad_crop_params[1],
                                   self.pad_crop_params[2],
                                   self.pad_crop_params[3]],
                                  0, [114, 114, 114])
                output_size = [
                    self.rgb888p_size[0] + self.pad_crop_params[2] + self.pad_crop_params[3],
                    self.rgb888p_size[1] + self.pad_crop_params[0] + self.pad_crop_params[1]
                ]
                self.ai2d_pad.build([1,3,ai2d_input_size[1], ai2d_input_size[0]],
                                    [1,3,output_size[1], output_size[0]])

                self.ai2d_crop.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
                self.ai2d_crop.crop(int(self.pad_crop_params[4]),
                                    int(self.pad_crop_params[6]),
                                    int(self.pad_crop_params[5]-self.pad_crop_params[4]+1),
                                    int(self.pad_crop_params[7]-self.pad_crop_params[6]+1))
                self.ai2d_crop.build([1,3,output_size[1], output_size[0]],
                                     [1,3,self.model_input_size[1], self.model_input_size[0]])
            else:
                self.need_pad = False
                self.ai2d_crop.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
                self.ai2d_crop.crop(int(self.center_xy_wh[0]-self.pad_crop_params[8]/2.0),
                                    int(self.center_xy_wh[1]-self.pad_crop_params[8]/2.0),
                                    int(self.pad_crop_params[8]),
                                    int(self.pad_crop_params[8]))
                self.ai2d_crop.build([1,3,ai2d_input_size[1], ai2d_input_size[0]],
                                     [1,3,self.model_input_size[1], self.model_input_size[0]])

    def preprocess(self, input_np):
        if self.need_pad:
            pad_output = self.ai2d_pad.run(input_np).to_numpy()
            return [self.ai2d_crop.run(pad_output)]
        else:
            return [self.ai2d_crop.run(input_np)]

    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            return results[0]

    def get_padding_crop_param(self):
        s_z = round(np.sqrt((self.center_xy_wh[2] + self.CONTEXT_AMOUNT * (self.center_xy_wh[2] + self.center_xy_wh[3])) *
                            (self.center_xy_wh[3] + self.CONTEXT_AMOUNT * (self.center_xy_wh[2] + self.center_xy_wh[3]))))
        c = (s_z + 1) / 2
        context_xmin = np.floor(self.center_xy_wh[0] - c + 0.5)
        context_xmax = int(context_xmin + s_z - 1)
        context_ymin = np.floor(self.center_xy_wh[1] - c + 0.5)
        context_ymax = int(context_ymin + s_z - 1)
        left_pad   = int(max(0, -context_xmin))
        top_pad    = int(max(0, -context_ymin))
        right_pad  = int(max(0, int(context_xmax - self.rgb888p_size[0] + 1)))
        bottom_pad = int(max(0, int(context_ymax - self.rgb888p_size[1] + 1)))
        context_xmin = context_xmin + left_pad
        context_xmax = context_xmax + left_pad
        context_ymin = context_ymin + top_pad
        context_ymax = context_ymax + top_pad
        return [top_pad, bottom_pad, left_pad, right_pad,
                context_xmin, context_xmax, context_ymin, context_ymax, s_z]

    def deinit(self):
        with ScopedTiming("deinit", self.debug_mode > 0):
            del self.ai2d_pad
            del self.ai2d_crop
            super().deinit()

# -----------------------------
# 下面是 TrackSrcApp 类
# -----------------------------
class TrackSrcApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, ratio_src_crop,
                 rgb888p_size=[320,240], display_size=[320,240], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path
        self.model_input_size = model_input_size
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0],16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0],16), display_size[1]]
        self.pad_crop_params = []
        self.CONTEXT_AMOUNT = 0.5
        self.ratio_src_crop = ratio_src_crop
        self.debug_mode = debug_mode
        self.ai2d_pad = Ai2d(debug_mode)
        self.ai2d_pad.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        self.ai2d_crop = Ai2d(debug_mode)
        self.ai2d_crop.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        self.need_pad = False

    def config_preprocess(self, center_xy_wh, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            self.pad_crop_params = self.get_padding_crop_param(center_xy_wh)
            if (self.pad_crop_params[0] != 0 or
                self.pad_crop_params[1] != 0 or
                self.pad_crop_params[2] != 0 or
                self.pad_crop_params[3] != 0):
                self.need_pad = True
                self.ai2d_pad.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
                self.ai2d_pad.pad([0, 0, 0, 0,
                                   self.pad_crop_params[0],
                                   self.pad_crop_params[1],
                                   self.pad_crop_params[2],
                                   self.pad_crop_params[3]],
                                  0, [114, 114, 114])
                output_size = [
                    self.rgb888p_size[0] + self.pad_crop_params[2] + self.pad_crop_params[3],
                    self.rgb888p_size[1] + self.pad_crop_params[0] + self.pad_crop_params[1]
                ]
                self.ai2d_pad.build([1,3,ai2d_input_size[1], ai2d_input_size[0]],
                                    [1,3,output_size[1], output_size[0]])
                self.ai2d_crop.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
                self.ai2d_crop.crop(int(self.pad_crop_params[4]),
                                    int(self.pad_crop_params[6]),
                                    int(self.pad_crop_params[5]-self.pad_crop_params[4]+1),
                                    int(self.pad_crop_params[7]-self.pad_crop_params[6]+1))
                self.ai2d_crop.build([1,3,output_size[1], output_size[0]],
                                     [1,3,self.model_input_size[1], self.model_input_size[0]])
            else:
                self.need_pad = False
                self.ai2d_crop.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
                self.ai2d_crop.crop(int(center_xy_wh[0]-self.pad_crop_params[8]/2.0),
                                    int(center_xy_wh[1]-self.pad_crop_params[8]/2.0),
                                    int(self.pad_crop_params[8]),
                                    int(self.pad_crop_params[8]))
                self.ai2d_crop.build([1,3,ai2d_input_size[1], ai2d_input_size[0]],
                                     [1,3,self.model_input_size[1], self.model_input_size[0]])

    def preprocess(self, input_np):
        with ScopedTiming("preprocess", self.debug_mode > 0):
            if self.need_pad:
                pad_output = self.ai2d_pad.run(input_np).to_numpy()
                return [self.ai2d_crop.run(pad_output)]
            else:
                return [self.ai2d_crop.run(input_np)]

    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            return results[0]

    def get_padding_crop_param(self, center_xy_wh):
        s_z = round(np.sqrt((center_xy_wh[2] + self.CONTEXT_AMOUNT * (center_xy_wh[2] + center_xy_wh[3])) *
                            (center_xy_wh[3] + self.CONTEXT_AMOUNT * (center_xy_wh[2] + center_xy_wh[3])))) * self.ratio_src_crop
        c = (s_z + 1) / 2
        context_xmin = np.floor(center_xy_wh[0] - c + 0.5)
        context_xmax = int(context_xmin + s_z - 1)
        context_ymin = np.floor(center_xy_wh[1] - c + 0.5)
        context_ymax = int(context_ymin + s_z - 1)
        left_pad   = int(max(0, -context_xmin))
        top_pad    = int(max(0, -context_ymin))
        right_pad  = int(max(0, int(context_xmax - self.rgb888p_size[0] + 1)))
        bottom_pad = int(max(0, int(context_ymax - self.rgb888p_size[1] + 1)))
        context_xmin = context_xmin + left_pad
        context_xmax = context_xmax + left_pad
        context_ymin = context_ymin + top_pad
        context_ymax = context_ymax + top_pad
        return [top_pad, bottom_pad, left_pad, right_pad,
                context_xmin, context_xmax, context_ymin, context_ymax, s_z]

    def deinit(self):
        with ScopedTiming("deinit", self.debug_mode > 0):
            del self.ai2d_pad
            del self.ai2d_crop
            super().deinit()

# -----------------------------
# 下面是 TrackerApp 类
# -----------------------------
class TrackerApp(AIBase):
    def __init__(self, kmodel_path, crop_input_size, thresh,
                 rgb888p_size=[320,240], display_size=[320,240], debug_mode=0):
        super().__init__(kmodel_path, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path
        self.crop_input_size = crop_input_size
        self.thresh = thresh
        self.CONTEXT_AMOUNT = 0.5
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0],16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0],16), display_size[1]]
        self.debug_mode = debug_mode
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)

    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            pass

    def run(self, input_np_1, input_np_2, center_xy_wh):
        input_tensors = []
        input_tensors.append(nn.from_numpy(input_np_1))
        input_tensors.append(nn.from_numpy(input_np_2))
        results = self.inference(input_tensors)
        return self.postprocess(results, center_xy_wh)

    def postprocess(self, results, center_xy_wh):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            det = aidemo.nanotracker_postprocess(
                results[0],
                results[1],
                [self.rgb888p_size[1], self.rgb888p_size[0]],
                self.thresh,
                center_xy_wh,
                self.crop_input_size[0],
                self.CONTEXT_AMOUNT
            )
            return det

# -----------------------------
# 下面是 NanoTracker 类
# -----------------------------
class NanoTracker:
    def __init__(self, track_crop_kmodel, track_src_kmodel, tracker_kmodel,
                 crop_input_size, src_input_size, threshold=0.25,
                 rgb888p_size=[1280,960], display_size=[320,240], debug_mode=0):
        self.track_crop_kmodel = track_crop_kmodel
        self.track_src_kmodel = track_src_kmodel
        self.tracker_kmodel = tracker_kmodel
        self.crop_input_size = crop_input_size
        self.src_input_size  = src_input_size
        self.threshold = threshold
        self.CONTEXT_AMOUNT = 0.5
        self.ratio_src_crop  = 0.0

        # 保证给定的起始框 + 50 像素边界都在 320×240 里，这里简单给个60
        self.track_x1 = float(110)
        self.track_y1 = float(70)
        self.track_w  = float(70)
        self.track_h  = float(70)

        self.draw_mean = []
        self.center_xy_wh = []
        self.track_boxes = []
        self.center_xy_wh_tmp = []
        self.track_boxes_tmp = []
        self.crop_output = None
        self.src_output  = None

        self.countdown_ms = 8000  # 8秒 = 8000毫秒
        self.start_ticks = time.ticks_ms()
        self.enter_init = True
        self.draw_count = 0  # 添加计数器
        self.total_draws = 150 # 总共需要返回的次数
        self.count_delay =0
        self.draw_count_int = 0
        self.draw_count_frac = 0

        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0],16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0],16), display_size[1]]

        self.init_param()

        self.track_crop = TrackCropApp(
            self.track_crop_kmodel,
            model_input_size=self.crop_input_size,
            ratio_src_crop=self.ratio_src_crop,
            center_xy_wh=self.center_xy_wh,
            rgb888p_size=self.rgb888p_size,
            display_size=self.display_size,
            debug_mode=0
        )
        self.track_src = TrackSrcApp(
            self.track_src_kmodel,
            model_input_size=self.src_input_size,
            ratio_src_crop=self.ratio_src_crop,
            rgb888p_size=self.rgb888p_size,
            display_size=self.display_size,
            debug_mode=0
        )
        self.tracker = TrackerApp(
            self.tracker_kmodel,
            crop_input_size=self.crop_input_size,
            thresh=self.threshold,
            rgb888p_size=self.rgb888p_size,
            display_size=self.display_size
        )
        self.track_crop.config_preprocess()

    def run(self,input_np):
        # 使用 ticks_ms() 进行倒计时
        current_ticks = time.ticks_ms()
        time_diff = time.ticks_diff(current_ticks, self.start_ticks)

        if (self.enter_init and self.draw_count < self.total_draws):
            # 计算剩余次数
            remaining_draws = self.total_draws - self.draw_count
#            print("倒计时: 还剩 %d 次" % remaining_draws)
            self.crop_output = self.track_crop.run(input_np)
            self.draw_count += 1
#            time.sleep(0.01)

            return self.draw_mean

        else:
            self.enter_init = False  # 确保初始化阶段结束
            self.track_src.config_preprocess(self.center_xy_wh)
            self.src_output = self.track_src.run(input_np)
            det = self.tracker.run(self.crop_output,self.src_output,self.center_xy_wh)
            return det


    def get_countdown_str(self):
        nowtime = self.total_draws - self.draw_count
        if self.enter_init and nowtime <= self.total_draws:

            return f"还需学习: {nowtime} 次"
        else:
            return None

    def draw_result(self, img, box):
        if self.enter_init:

            img.draw_rectangle(box[0], box[1], box[2], box[3], color=(0, 255, 0), thickness=3)
            if self.draw_count >= self.total_draws:  # 使用计数器来判断是否结束初始化
                self.enter_init = False
        else:
            if len(box) < 2:
                return  # 确保有足够的元素进行跟踪

            self.track_boxes = box[0] if len(box[0]) >= 4 else []
            self.center_xy_wh = box[1] if len(box) > 1 and len(box[1]) >= 4 else []

            track_bool = True
            if (len(self.track_boxes) != 0):
                track_bool = (self.track_boxes[0] > 10 and
                              self.track_boxes[1] > 10 and
                              (self.track_boxes[0]+self.track_boxes[2]) < self.rgb888p_size[0]-10 and
                              (self.track_boxes[1]+self.track_boxes[3]) < self.rgb888p_size[1]-10)
            else:
                track_bool = False

            if (len(self.center_xy_wh) != 0):
                track_bool = track_bool and (self.center_xy_wh[2]*self.center_xy_wh[3] < 40000)
            else:
                track_bool = False

            if track_bool:
                self.center_xy_wh_tmp = self.center_xy_wh
                self.track_boxes_tmp  = self.track_boxes
                x1 = int(float(self.track_boxes[0]) * self.display_size[0] / self.rgb888p_size[0])
                y1 = int(float(self.track_boxes[1]) * self.display_size[1] / self.rgb888p_size[1])
                w  = int(float(self.track_boxes[2]) * self.display_size[0] / self.rgb888p_size[0])
                h  = int(float(self.track_boxes[3]) * self.display_size[1] / self.rgb888p_size[1])
                # 黄色框 (255, 255, 0)
                img.draw_rectangle(x1, y1, w, h, color=(255, 255, 0), thickness=4)
            else:
                if len(self.track_boxes_tmp) >=4 and len(self.center_xy_wh_tmp) >=4:
                    self.center_xy_wh = self.center_xy_wh_tmp
                    self.track_boxes  = self.track_boxes_tmp
                    x1 = int(float(self.track_boxes[0]) * self.display_size[0] / self.rgb888p_size[0])
                    y1 = int(float(self.track_boxes[1]) * self.display_size[1] / self.rgb888p_size[1])
                    w  = int(float(self.track_boxes[2]) * self.display_size[0] / self.rgb888p_size[0])
                    h  = int(float(self.track_boxes[3]) * self.display_size[1] / self.rgb888p_size[1])
                    img.draw_rectangle(x1, y1, w, h, color=(255, 255, 0), thickness=3)
                    img.draw_string_advanced(x1, y1 - 20, 13,
                                             "请远离摄像头，保持大小一致!",
                                             color=(255, 255, 0))
                    img.draw_string_advanced(x1, y1 - 50, 13,
                                             "请靠近中心!",
                                             color=(255, 255, 0))


    def init_param(self):
        self.ratio_src_crop = float(self.src_input_size[0]) / float(self.crop_input_size[0])
        print(self.ratio_src_crop)
        if (self.track_x1 < 50 or
            self.track_y1 < 50 or
            (self.track_x1 + self.track_w) >= (self.rgb888p_size[0] - 50) or
            (self.track_y1 + self.track_h) >= (self.rgb888p_size[1] - 50)):
            print("**剪切范围超出图像范围**")
        else:
            track_mean_x = self.track_x1 + self.track_w / 2.0
            track_mean_y = self.track_y1 + self.track_h / 2.0
            draw_mean_w  = int(self.track_w / self.rgb888p_size[0] * self.display_size[0])
            draw_mean_h  = int(self.track_h / self.rgb888p_size[1] * self.display_size[1])
            draw_mean_x  = int(track_mean_x / self.rgb888p_size[0] * self.display_size[0] - draw_mean_w / 2.0)
            draw_mean_y  = int(track_mean_y / self.rgb888p_size[1] * self.display_size[1] - draw_mean_h / 2.0)
            self.draw_mean = [draw_mean_x, draw_mean_y, draw_mean_w, draw_mean_h]
            self.center_xy_wh = [track_mean_x, track_mean_y, self.track_w, self.track_h]
            self.center_xy_wh_tmp = [track_mean_x, track_mean_y, self.track_w, self.track_h]
            self.track_boxes = [self.track_x1, self.track_y1, self.track_w, self.track_h, 1]
            self.track_boxes_tmp = np.array([self.track_x1, self.track_y1, self.track_w, self.track_h, 1])


#if __name__=="__main__":

display_mode = "lcd"
display_size = [320, 240]

track_crop_kmodel_path = "/sdcard/examples/kmodel/cropped_test127.kmodel"
track_src_kmodel_path  = "/sdcard/examples/kmodel/nanotrack_backbone_sim.kmodel"
tracker_kmodel_path    = "/sdcard/examples/kmodel/nanotracker_head_calib_k230.kmodel"

rgb888p_size = [320, 240]
track_crop_input_size = [127, 127]
track_src_input_size  = [255, 255]
threshold = 0.1

pl = PipeLine(rgb888p_size=rgb888p_size,
              display_size=display_size,
              display_mode=display_mode)
pl.create()

track = NanoTracker(
    track_crop_kmodel_path,
    track_src_kmodel_path,
    tracker_kmodel_path,
    crop_input_size=track_crop_input_size,
    src_input_size=track_src_input_size,
    threshold=threshold,
    rgb888p_size=rgb888p_size,
    display_size=display_size
)

clock = time.clock()

while True:
    clock.tick()

    # 从通道 2 获取图像做推理
    img_for_ai = pl.get_frame()

    output = track.run(img_for_ai)

    # 从通道 1 获取 RGB565 图像
    rgb565_img = pl.sensor.snapshot(chn=CAM_CHN_ID_1)

    # 在此图像上绘制跟踪结果
    track.draw_result(rgb565_img, output)
    countdown_str = track.get_countdown_str()
    #显示 FPS
    fps_str = "FPS: " + str("%.3f" % (clock.fps()))
    if countdown_str:
        rgb565_img.draw_string_advanced(200, 0, 16, countdown_str, color=(0, 0, 255))
    rgb565_img.draw_string_advanced(0, 0, 16, fps_str, color=(255, 255, 255))

    # 在屏幕上显示
    lcd_screen.show(rgb565_img)

    gc.collect()
