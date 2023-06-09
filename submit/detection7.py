from ultralytics import YOLO
from toolkits.utils import face_analysis
import cv2


import numpy as np
from datetime import datetime
import time
import json



def iou(box1, box2):
    """Calculate Intersection over Union (IoU) between two bounding boxes"""

    x1, y1, x2, y2 = box1
    x3, y3, x4, y4 = box2

    # calculate the overlap coordinates
    xx1, yy1 = max(x1, x3), max(y1, y3)
    xx2, yy2 = min(x2, x4), min(y2, y4)

    # compute the width and height of the overlap area
    overlap_width, overlap_height = max(0, xx2 - xx1), max(0, yy2 - yy1)
    overlap_area = overlap_width * overlap_height

    # compute the area of both bounding boxes
    box1_area = (x2 - x1) * (y2 - y1)
    box2_area = (x4 - x3) * (y4 - y3)

    # compute IoU
    iou = overlap_area / float(box1_area + box2_area - overlap_area)
    return iou


def run_video(video_path, save_path):
    cap = cv2.VideoCapture(video_path)

    # 初始化所有模型
    yolo_model = YOLO('best.pt')
    device = 'cpu'
    results = yolo_model(cv2.imread('bus.jpg'))


    cnt = 0  # 开始处理的帧数
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))  # 待处理的总帧数

    # 获取当前视频的帧率与宽高，设置同样的格式，以确保相同帧率与宽高的视频输出
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    ######################################################################################################
    result = {"result": {"category": 0, "duration": 6000}}


    ANGLE_THRESHOLD = 35
    EAR_THRESHOLD = 0.2
    YAWN_THRESHOLD = 0.4

    eyes_closed_frame = 0
    mouth_open_frame = 0
    use_phone_frame = 0
    max_phone = 0
    max_eyes = 0
    max_mouth = 0
    max_wandering = 0
    look_around_frame = 0
    result_list = []


    sensitivity = 0.001

    now = time.time()  # 读取视频与加载模型的时间不被计时（？）

    while cap.isOpened():

        if cnt >= frames:
            break
        phone_around_face = False
        is_eyes_closed = False
        is_turning_head = False
        is_yawning = False
        frame_result = 0

        overlap = 0
        cnt += 1
        ret, frame = cap.read()
        if cnt % 21 != 0 and cnt != 1:
            continue
        if cnt + 80 > frames:  # 最后三秒不判断了
            break



        print(f'video {cnt}/{frames} {save_path}')  # delete
        # process the image with the yolo and get the person list
        results = yolo_model(frame)





        # 创建img0的副本
        img1 = frame.copy()

        # 获取图像的宽度
        img_height = frame.shape[0]

        img_width = frame.shape[1]

        # 获取所有的边界框
        boxes = results[0].boxes

        # 获取所有类别
        classes = boxes.cls

        # 获取所有的置信度
        confidences = boxes.conf

        # 初始化最靠右的框和最靠右的手机
        rightmost_box = None
        rightmost_phone = None

        # 遍历所有的边界框
        for box, cls, conf in zip(boxes.xyxy, classes, confidences):
            # 如果类别为1（手机）且在图片的右2/3区域内
            if cls == 1 and box[0] > img_width * 1 / 3:
                # 如果还没有找到最靠右的手机或者这个手机更靠右
                if rightmost_phone is None or box[0] > rightmost_phone[0]:
                    rightmost_phone = box

            # 如果类别为0（驾驶员）且在图片的右2/3区域内
            if cls == 0 and box[0] > img_width * 1 / 3:
                # 如果还没有找到最靠右的框或者这个框更靠右
                if rightmost_box is None or box[0] > rightmost_box[0]:
                    rightmost_box = box

        # 如果没有找到有效的检测框，返回img1为img0的右3/5区域
        if rightmost_box is None:
            img1 = img1
            m1 = int(img_width * 2 / 5)
            n1 = 0
            # 右下角的坐标
            m2 = img_width
            n2 = img_height

        # 否则，返回img1仅拥有最靠右的框内的图片
        else:
            x1, y1, x2, y2 = rightmost_box
            x1 = max(0, int(x1 - 0.1 * (x2 - x1)))
            y1 = max(0, int(y1 - 0.1 * (y2 - y1)))
            x2 = min(img_width, int(x2 + 0.1 * (x2 - x1)))
            y2 = min(img_width, int(y2 + 0.1 * (y2 - y1)))
            # img1 = img1[y1:y2, x1:x2]
            m1, n1, m2, n2 = x1, y1, x2, y2

            # 计算交集的面积
            if rightmost_phone is not None and rightmost_box is not None:
                # 计算两个框的IoU
                overlap = iou(rightmost_box, rightmost_phone)

                # cv2.putText(img1, f"IoU: {overlap:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                print(overlap)
                # 如果IoU大于阈值，打印警告
                if overlap > sensitivity:
                    phone_around_face = True  ##判断手机

        # 计算边界框的宽度和高度
        w = m2 - m1
        h = n2 - n1

        # 创建 bbox
        bbox = [m1, n1, w, h]


        # frame = spig_process_frame(frame, bbox)  # TODO: 删除
        if phone_around_face == False:
            pose, mar, ear = face_analysis(frame, bbox,test=1)  # TODO: 添加功能


            is_turning_head = True if np.abs(pose[[0, 2]]).max() > ANGLE_THRESHOLD else False
            is_yawning = True if mar > YAWN_THRESHOLD else False
            is_eyes_closed = True if ear < EAR_THRESHOLD else False
            # is_eyes_closed, is_turning_head, is_yawning = face_analysis(frame, bbox) # TODO: 添加功能
        # is_eyes_closed, is_turning_head, is_yawning = False, False, False



        if is_eyes_closed: #1
            print(ear)
            frame_result = 1
            eyes_closed_frame += 1
            if eyes_closed_frame > max_eyes:
                max_eyes = eyes_closed_frame
        else:
            eyes_closed_frame = 0

        if is_turning_head: #4
            frame_result = 4
            look_around_frame += 1
            if look_around_frame > max_wandering:
                max_wandering = look_around_frame
        else:
            look_around_frame = 0

        if is_yawning: #2
            print(mar)
            frame_result = 2
            mouth_open_frame += 1
            eyes_closed_frame = 0    #有打哈欠则把闭眼和转头置零
            look_around_frame = 0
            if mouth_open_frame > max_mouth:
                max_mouth = mouth_open_frame
        else:
            mouth_open_frame = 0

        if phone_around_face: #3
            print(overlap)
            frame_result =3
            use_phone_frame += 1
            mouth_open_frame = 0
            look_around_frame = 0
            eyes_closed_frame = 0  #有手机则把其他都置零
            if use_phone_frame > max_phone:
                max_phone = use_phone_frame
        else:
            use_phone_frame = 0

            ###################################################
            # im0 = display_results(img0, det, names,is_eyes_closed, is_turning_head, is_yawning)
            # # write video
            # vid_writer.write(im0)
        result_list.append(frame_result)

        if max_phone >= 4:
            result['result']['category'] = 3
            break

        elif max_wandering >= 4:
            result['result']['category'] = 4
            break

        elif max_mouth >= 4:
            result['result']['category'] = 2
            break

        elif max_eyes >= 4:
            result['result']['category'] = 1
            break

    final_time = time.time()
    duration = int(np.round((final_time - now) * 1000))

    cap.release()


    result['result']['duration'] = duration

    return result


def main():
    video_dir = r'F:\ccp1\three'
    save_dir = r'D:\0---Program\Projects\aimbot\yolov5-master\yolov5-master\output'

    video_files = [f for f in os.listdir(video_dir) if f.lower().endswith(".mp4")]
    # video_files = [f for f in os.listdir(video_dir) if f.lower().endswith(".json")]

    # Create a new log file with the current time
    log_file = os.path.join(save_dir, datetime.now().strftime("%Y%m%d%H%M%S") + '_log.json')
    log = {}

    for video_file in video_files:
        video_path = os.path.join(video_dir, video_file)
        save_path = os.path.join(save_dir, video_file)
        print(video_file)

        result = run_video(video_path, save_path)
        json_save_path = save_path.rsplit('.', 1)[0] + '.json'

        with open(json_save_path, 'w') as json_file:
            json.dump(result, json_file)

        # Update the log and write it to the log file
        log[video_file] = result
        with open(log_file, 'w') as log_json:
            json.dump(log, log_json)


if __name__ == '__main__':
    import os

    os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
    main()