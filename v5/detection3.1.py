import os

import cv2
import torch
import numpy as np

from aim.utils.general import scale_coords
from utils.general import non_max_suppression, scale_boxes, xyxy2xywh
from utils.augmentations import letterbox
from v5.models.experimental import attempt_load

from models.common import DetectMultiBackend
from utils.dataloaders import IMG_FORMATS, VID_FORMATS, LoadImages, LoadScreenshots, LoadStreams
from utils.general import (LOGGER, Profile, check_file, check_img_size, check_imshow, check_requirements, colorstr, cv2,
                           increment_path, non_max_suppression, print_args, scale_boxes, strip_optimizer, xyxy2xywh)
from utils.plots import Annotator, colors, save_one_box
from utils.torch_utils import select_device, smart_inference_mode

def preprocess_video(video_path, frame_no=0, img_size=640, stride=32):
    # 读取视频对象
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)

    # 读取帧图像
    ret_val, img0 = cap.read()
    if not ret_val:
        print("Error reading video frame")
        return None

    # Padded resize
    img = letterbox(img0, img_size, stride=stride, auto=True)[0]

    # Convert
    img = img.transpose((2, 0, 1))[::-1]  # HWC to CHW, BGR to RGB
    img = np.ascontiguousarray(img)

    img = torch.from_numpy(img).float() / 255.0  # 0 - 255 to 0.0 - 1.0
    img = img[None]  # [h w c] -> [1 h w c]

    return img0, img


def infer_image(model, img, img0,augment=False, visualize=False):
    # inference
    pred = model(img, augment=augment, visualize=visualize)[0]
    pred = non_max_suppression(pred, conf_thres=0.25, iou_thres=0.45, max_det=1000)

    # process detection results
    det = pred[0]
    if len(det):
        det[:, :4] = scale_coords(img.shape[2:], det[:, :4], img0.shape).round()

    return det


def display_results(img0, det, names):
    # plot label
    annotator = Annotator(img0.copy(), line_width=3, example=str(names))
    for *xyxy, conf, cls in reversed(det):
        c = int(cls)  # integer class
        label = f'{names[c]} {conf:.2f}'
        annotator.box_label(xyxy, label, color=colors(c, True))

    return annotator.result()

# 功能：单视频推理
def run_video(video_path, save_path, img_size=640, stride=32, augment=False, visualize=False):
    weights = r'D:\0---Program\Projects\aimbot\yolov5-master\yolov5-master\aim\weights\face_phone_detection.pt'
    device = 'cpu'

    # 导入模型
    model = attempt_load(weights)
    img_size = check_img_size(img_size, s=stride)
    names = model.names

    # 读取视频对象
    cap = cv2.VideoCapture(video_path)
    frame = 0       # 开始处理的帧数
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) # 待处理的总帧数

    # 获取当前视频的帧率与宽高，设置同样的格式，以确保相同帧率与宽高的视频输出
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # save_path += os.path.basename(video_path)
    vid_writer = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))

    while frame <= frames:
        img0, img = preprocess_video(video_path, frame, img_size, stride)
        if img0 is None or img is None:
            break

        frame += 1
        print(f'video {frame}/{frames} {save_path}')
        #每一帧的推理结果都保存在det中
        det = infer_image(model, img, img0,augment, visualize)

        im0 = display_results(img0, det, names)

    
        # write video
        vid_writer.write(im0)

    vid_writer.release()
    cap.release()
    print(f'{video_path} finish, save to {save_path}')

video_path = r'D:\0---Program\Projects\aimbot\yolov5-master\yolov5-master\vedio\1.mp4'
save_path = r'D:\0---Program\Projects\aimbot\yolov5-master\yolov5-master\output\1.mp4'
run_video(video_path, save_path, img_size=640, stride=32, augment=False, visualize=False)