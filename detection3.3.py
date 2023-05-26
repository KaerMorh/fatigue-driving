import os

from scipy.spatial import distance as dist
from imutils import face_utils
import time
import dlib
import numpy as np
import math
import cv2





import torch
import numpy as np

from aim.utils.general import scale_coords
from utils.general import non_max_suppression, scale_boxes, xyxy2xywh
from utils.augmentations import letterbox
from models.experimental import attempt_load

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


def infer_image(model, img, img0, augment=False, visualize=False):
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


##############################face


def get_euler_angle(rotation_vector):
    """
    通过旋转向量获得欧拉角
    :param rotation_vector: 旋转向量
    :return: 欧拉角 3个方向 pitch, yaw, roll
    """
    theta = cv2.norm(rotation_vector, cv2.NORM_L2)
    w = np.cos(theta / 2)
    x = np.sin(theta / 2) * rotation_vector[0][0] / theta
    y = np.sin(theta / 2) * rotation_vector[1][0] / theta
    z = np.sin(theta / 2) * rotation_vector[2][0] / theta
    yy = np.square(y)
    t0 = 2.0 * (w * x + y * z)
    t1 = 1.0 - 2.0 * (x * x + yy)
    pitch = math.atan2(t0, t1)
    t2 = 2.0 * (w * y - z * x)
    if t2 > 1.0:
        t2 = 1.0
    if t2 < -1.0:
        t2 = -1.0
    yaw = math.asin(t2)
    t3 = 2.0 * (w * z + x * y)
    t4 = 1.0 - 2.0 * (yy + z * z)
    roll = math.atan2(t3, t4)

    # 弧度 -> 角度
    pitch = int(np.rad2deg(pitch))
    yaw = int(np.rad2deg(yaw))
    roll = int(np.rad2deg(roll))

    return pitch, yaw, roll


def mouth_aspect_ratio(mouth):
    """
    计算嘴长宽比例
    :param mouth: 嘴部矩阵
    :return: MAR
    """
    A = dist.euclidean(mouth[13], mouth[19])
    B = dist.euclidean(mouth[14], mouth[18])
    C = dist.euclidean(mouth[15], mouth[17])
    MAR = (A + B + C) / 3.0
    return MAR


def eye_ratio(eye):
    """
    计算人眼纵横比 (EAR)
    :param eye: 眼部矩阵
    :return: ear
    """
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])
    C = dist.euclidean(eye[0], eye[3])
    ear = (A + B) / (2.0 * C)
    return ear
###面部分析函数，缺少对连续帧的预测分析。可以参考原函数，连续50贞闭眼即为瞌睡。

# 将人脸的六个关键点定义为模型点
model_points = np.array([
    (0.0, 0.0, 0.0),  # Nose tip
    (0.0, -330.0, -65.0),  # Chin
    (-225.0, 170.0, -135.0),  # Left eye left corner
    (225.0, 170.0, -135.0),  # Right eye right corner
    (-150.0, -150.0, -125.0),  # Left Mouth corner
    (150.0, -150.0, -125.0)  # Right mouth corner
])

ANGLE_THRESHOLD = 45.0  # 头部转动的阈值
EAR_THRESHOLD = 0.2  # 眼睛纵横比的阈值
SUSTAIN_FREAMS = 50  # 连续帧数阈值，如果超过这个帧数眼睛仍然闭着，那么判定为瞌睡
YAWN_THRESHOLD = 25  # 嘴部纵横比的阈值，如果超过这个阈值，那么判定为打哈欠


def face_analysis(image, detector, predictor):
    # 首先初始化闭眼，转头，打哈欠的状态为False或0
    is_eyes_closed = False
    is_turning_head = 0
    is_yawning = False

    # 将输入的图片转换为灰度图
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 使用detector检测输入图像中的面部
    rects = detector(gray, 0)

    # 如果在图像中没有检测到面部，直接返回结果
    if len(rects) == 0:
        return is_eyes_closed, is_turning_head, is_yawning

    # 如果检测到了面部，就选择第一个检测到的面部
    rect = rects[0]

    # 使用predictor预测面部的特征点
    shape = predictor(gray, rect)
    shape = face_utils.shape_to_np(shape)

    # 提取特征点中的眼睛和嘴巴的点
    (left_eye_start_point, left_eye_end_point) = face_utils.FACIAL_LANDMARKS_IDXS['left_eye']
    (right_eye_start_point, right_eye_end_point) = face_utils.FACIAL_LANDMARKS_IDXS['right_eye']
    (mouth_start_point, mouth_end_point) = face_utils.FACIAL_LANDMARKS_IDXS["mouth"]
    leftEye = shape[left_eye_start_point:left_eye_end_point]
    rightEye = shape[right_eye_start_point:right_eye_end_point]
    mouth = shape[mouth_start_point: mouth_end_point]

    # 计算眼睛和嘴巴的纵横比
    leftEAR = eye_ratio(leftEye)
    rightEAR = eye_ratio(rightEye)
    mar = mouth_aspect_ratio(mouth)

    # 平均左右眼的纵横比
    ear = (leftEAR + rightEAR) / 2.0

    # 如果眼睛的纵横比小于阈值，那么判定为闭眼
    if ear < EAR_THRESHOLD:
        is_eyes_closed = True

    # 如果嘴巴的纵横比大于阈值，那么判定为打哈欠
    if mar > YAWN_THRESHOLD:
        is_yawning = True

    # 检测头部的转动角度
    landmarks = list((p.x, p.y) for p in predictor(image, rect).parts())
    point_list = [landmarks[30], landmarks[8], landmarks[36], landmarks[45], landmarks[48], landmarks[54]]
    image_points = np.array(point_list, dtype="double")

    size = image.shape
    focal_length = size[1]
    center = (size[1] / 2, size[0] / 2)
    camera_matrix = np.array([[focal_length, 0, center[0]], [0, focal_length, center[1]], [0, 0, 1]], dtype="double")
    dist_coeffs = np.zeros((4, 1))
    _, rotation_vector, _ = cv2.solvePnP(model_points, image_points, camera_matrix, dist_coeffs,
                                         flags=cv2.SOLVEPNP_ITERATIVE)
    _, _, yaw = get_euler_angle(rotation_vector)

    # 如果头部的转动角度超过阈值，那么判定为转头
    if yaw <= -ANGLE_THRESHOLD:
        is_turning_head = 1  # 左转
    elif yaw >= ANGLE_THRESHOLD:
        is_turning_head = 2  # 右转

    return is_eyes_closed, is_turning_head, is_yawning


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
    frame = 0  # 开始处理的帧数
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))  # 待处理的总帧数

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
        # 每一帧的推理结果都保存在det中
        det = infer_image(model, img, img0, augment, visualize)

        im0 = display_results(img0, det, names)

        # write video
        vid_writer.write(im0)

    vid_writer.release()
    cap.release()
    print(f'{video_path} finish, save to {save_path}')