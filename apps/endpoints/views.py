
import json
from rest_framework import views, status
from rest_framework.response import Response

from logging import exception
from unittest import result
from django.shortcuts import render


import torch
import torch.nn as nn
from torchvision import transforms
import torchvision.transforms.functional as TF

from torchvision.io import read_image
from torchvision.utils import draw_bounding_boxes


from tensorflow.keras.preprocessing.image import img_to_array
from tensorflow.keras.preprocessing.image import load_img
from tensorflow.keras.models import load_model

# import matplotlib.pyplot as plt

import os
import cv2
from PIL import Image
import numpy as np
from random import random

from django.conf import settings

from django.template.response import TemplateResponse
from django.http import JsonResponse
from django.utils.datastructures import MultiValueDictKeyError
from django.core.files.storage import FileSystemStorage

from models.inceptionresnetv2 import InceptionResNetV2
from utils.main import allowed_file, createFilePath
from my_yolov6 import my_yolov6

model_predict = InceptionResNetV2()
num_inputs = model_predict.last_linear.in_features
model_predict.last_linear = nn.Sequential(
    nn.Dropout(0.1),
    nn.Linear(num_inputs, 1000),
    nn.ReLU(),
    nn.Linear(1000, 512),
    nn.ReLU(),
    nn.Linear(512,448),
    nn.ReLU(),
    nn.Linear(448, 320),
    nn.ReLU(),
    nn.Linear(320, 2)
)

model_predict.load_state_dict(torch.load("brain_tumor_inceptionresnetv2.pth", map_location=torch.device('cpu')))
model_predict.eval()


# model_bbox = load_model('bbox_regression.h5')
yolov6_model = my_yolov6("best_ckpt.pt","cpu","data/mydataset.yml", 640, True)

import imutils

MEAN = [0.23740229, 0.23729787, 0.23700129]
STD = [0.23173477, 0.23151317, 0.23122775]


class ImageEnhanced(object):
    """_summary_
    transform to enhanced image quality for prediction 
    """
    def __init__(self):
        pass
    def __call__(self, img ,add_pixels_value = 0):
        
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        # threshold the image, then perform a series of erosions +
        # dilations to remove any small regions of noise
        thresh = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.erode(thresh, None, iterations=2)
        thresh = cv2.dilate(thresh, None, iterations=2)
        # find contours in thresholded image, then grab the largest one
        cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = imutils.grab_contours(cnts)
        c = max(cnts, key=cv2.contourArea)
        # find the extreme points
        extLeft = tuple(c[c[:, :, 0].argmin()][0])
        extRight = tuple(c[c[:, :, 0].argmax()][0])
        extTop = tuple(c[c[:, :, 1].argmin()][0])
        extBot = tuple(c[c[:, :, 1].argmax()][0])
        ADD_PIXELS = add_pixels_value
        new_img = img[extTop[1]-ADD_PIXELS:extBot[1]+ADD_PIXELS, extLeft[0]-ADD_PIXELS:extRight[0]+ADD_PIXELS].copy()
        return Image.fromarray(new_img)

transforms = transforms.Compose([
    ImageEnhanced(),
    transforms.ToTensor(),
    transforms.Resize((299, 299), interpolation=transforms.InterpolationMode.BICUBIC),
    transforms.Normalize(MEAN, STD)
])


class CustomFileSystemStorage(FileSystemStorage):
    def get_available_name(self, name, max_length=None):
        self.delete(name)
        return name

class PredictView(views.APIView):
    
    def get(self, request):
        return Response("Hello World!")
    
    def post(self, request):
        message = ""
        prediction = ""
        fss = CustomFileSystemStorage()
        try:
            # Take upload file
            image = request.FILES.get('file')
            img_name = str(image)
            
            _image = ""
            path = ""
            savedFolder = ""
            bb_predict_path = ""
            # Save image upload if true type
            if(allowed_file(img_name)):
                savedFolder = createFilePath()
                # Preprocessing image name
                img_name = f"raw_img.{img_name.rsplit('.', 1)[1].lower()}"
                _image = fss.save(f"{savedFolder}/{img_name}", image)
                path = f"{savedFolder}/{img_name}"
            else:
                raise TypeError

            # Read the image
            imag=cv2.imread(path)
            img = transforms(imag)
            img = torch.unsqueeze(img, 0)
            
            outputs = model_predict(img)
            _,result = torch.max(outputs, 1)
            if (result == 0):
                prediction = "No"
            elif (result == 1):
                prediction = "Yes"
                imag, ndet = yolov6_model.infer(imag, conf_thres=0.4, iou_thres=0.45)
                
                # Bouding box predict path
                extension = img_name.rsplit('.',1)[1].lower()
                name = img_name.rsplit('.',1)[0]
                bb_predict_path = f"{savedFolder}/{name}_bbox.{extension}"
                cv2.imwrite(bb_predict_path, imag)
            else:
                prediction = "Unknown"
            return Response({
                'code':200,
                'message':message,
                'image_url':path,
                'bbox_image_url':path if prediction == "No" else bb_predict_path,
                'prediction':prediction
            })
        except MultiValueDictKeyError:
            return Response({
                "code":400,
                "message":"No image selected!"
            })
        except TypeError:
            return Response({
                "code":415,
                "message": "File type not allowed! You must upload images type: jpg, png, jpeg,..."
            })
        except:
            return Response({
                "code":500,
                "message":"Smt bad has been occured!"
            })