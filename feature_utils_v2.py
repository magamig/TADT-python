
import cv2
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from matplotlib.patches import Rectangle
from torchvision import transforms

import time
import os
from PIL import Image

from image_loader import default_image_loader

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

def unnormalize(tensor):
    return ((tensor.cpu().squeeze(0).numpy()+np.array([0.485,0.456,0.406]))*np.array([0.229,0.224,0.225])).transpose((1,2,0)).clip(0,1)

def get_subwindow_feature(model, image, location, input_sz, layer_name = None):
    """
    function: extracts the features of the Conv4-3 and Conv4-1 layers of VGG16 that
              will be used to calculate target and scale sensitive features
    args:
        model - deep network to extract features
        img - image to be processed
        location - the positions and sizes of the sub-windows, can contain several locations, [x1, y1, w, h]
        input_sz - the size of the image patch to be fed to model
        layer_name -
    """

    subwindow = get_subwindow(location, image, input_sz, False)
    
    subwindow = (torch.unsqueeze(subwindow, 0)).to(device)
    features = model(subwindow, layer_name)

    return features

def get_frame_features(model, image, layer_name=None):
    """
    function: extracts the deep features from the entire frame
    args:
        model - model used to extract features
        img - frame to be processed
        layer_name -
    return:
        frame - current frame processed as tensor
        features - current frame features
    """

    frame = torch.tensor(image.transpose(2,0,1), dtype=torch.float) - 128
    
    #squeeze frame to calculate features
    frame_squeezed = (torch.unsqueeze(frame, 0)).to(device)
    features = model(frame_squeezed, layer_name)

    return frame, features

def show_heatmap_over_image(location, image, input_sz, features, window):
    feature = torch.cat(features, dim = 1)
    heatmap = torch.sum(torch.squeeze(feature),dim = 0)
    heatmap = heatmap/torch.max(heatmap)
    heatmap = cv2.resize(heatmap.cpu().numpy(), (window.shape[3], window.shape[2]))
    heatmap = np.uint8(255 * heatmap)
    heatmap = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

    if (location):
        subwindow_image = cv2.cvtColor(get_cv2_subwindow(location, image, input_sz),cv2.COLOR_BGR2RGB)
    else:
        subwindow_image = cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
        cv2.imshow("Combination", cv2.addWeighted(subwindow_image, 0.6, heatmap, 0.4, 0.0))
        cv2.waitKey(0)


def get_subwindow(location, image, input_sz, visualize = True):
    """
    function: crop the subwindow from the image
    args:
        location - subwindow location [x1, y1, w, h]
        image - <class 'numpy.ndarray'>
        input_sz - the size of the input of vgg model, [width,height]
        visualize - whether to visualize the subwindow
    return:
        image: RGB image showing the portion(subwindow) cropped from image
    """
    size = np.array(location[2:4])
    position = np.array(location[0:2]) + size/2
    height, width = image.shape[0:2]


    x_index = (np.floor(position[0] + np.arange(1, size[0]+1) - np.ceil(size[0]/2))).astype(int)
    y_index = (np.floor(position[1] + np.arange(1, size[1]+1) - np.ceil(size[1]/2))).astype(int)

    #crop
    y_index = clamp(y_index, 0, height - 1)

    x_index = clamp(x_index, 0, width - 1)

    x_index, y_index = np.meshgrid(x_index, y_index)

    image = image[y_index, x_index, :]


    image = cv2.resize(image, tuple(input_sz), interpolation=cv2.INTER_LINEAR)

    if visualize:

        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        print('show_image')
        cv2.namedWindow('input_image', cv2.WINDOW_AUTOSIZE)
        cv2.imshow('input_image', image)
        cv2.waitKey(10000)
        cv2.destroyAllWindows()


    #image transforms for matconvnet vgg model
    image = torch.tensor(image.transpose(2,0,1), dtype=torch.float)- 128

    return image


def get_cv2_subwindow(location, image, input_sz):
    """
    args:
        location - subwindow location [x1, y1, w, h]
        image - <class 'numpy.ndarray'>
        input_sz - the size of the input of vgg model, [width,height]
        visualize - whether to visualize the subwindow
    """
    size = np.array(location[2:4])
    position = np.array(location[0:2]) + size/2
    height, width = image.shape[0:2]


    x_index = (np.floor(position[0] + np.arange(1, size[0]+1) - np.ceil(size[0]/2))).astype(int)
    y_index = (np.floor(position[1] + np.arange(1, size[1]+1) - np.ceil(size[1]/2))).astype(int)

    #crop
    y_index = clamp(y_index, 0, height - 1)

    x_index = clamp(x_index, 0, width - 1)

    x_index, y_index = np.meshgrid(x_index, y_index)

    image = image[y_index, x_index, :]

    image = cv2.resize(image, tuple(input_sz), interpolation=cv2.INTER_LINEAR)

    return image


def clamp(index, lower, upper):

    for idx in range(len(index)):
        if index[idx] > upper:
            index[idx] = upper
        if index[idx] < lower:
            index[idx] = lower
    return index

def generate_patch_feature(target_size, srch_window_location, features):

    patch_features = []
    patch_locations = []

    for feature in features:
        feature_size = torch.tensor(feature.shape[-2:]).numpy()

        center = round_python2(feature_size/2)-1

        patch_size = np.floor(target_size * feature_size / srch_window_location[2:4] / 2) * 2 + 1

        patch_loc = np.append(center - np.floor(patch_size/2), center + np.floor(patch_size/2)).astype(int)

        patch_feature = feature[:,:,patch_loc[0]:patch_loc[2]+1,patch_loc[1]:patch_loc[3]+1]
        patch_features.append(patch_feature)
        patch_locations.append(patch_loc)
    visualize = False
    if visualize:
        patch_feature = torch.cat(patch_features, dim = 1)
        print('patch_feature.shape:',patch_feature.shape)
        heatmap = torch.sum(torch.squeeze(patch_feature),dim = 0)
        heatmap = heatmap/torch.max(heatmap)
        print('heatmap:\n',heatmap.shape)
        tensor_show(heatmap, 100, normalize = False, feature = True)
    return patch_features, patch_locations

def round_python2(temp_array):

    re_array = []
    for i in temp_array:
        if i % 1 == 0.5:
            re_array.append(np.ceil(i))
        else:
            re_array.append(np.round(i))
    return np.array(re_array)

def features_selection(input_features, feature_weights, balance_weights, mode = 'reduction'):

    assert(mode in ['pca', 'sa', 'pca_sa', 'reduction']), "mode need to be 'pca' or 'sa' or 'pca_sa' or 'reduction'"
    target_features = []
    num_channels = 0
    if mode == 'reduction':
        for i in range(len(input_features)):
            patch_feature = input_features[i]
            feature_weight = feature_weights[i]
            target_features.append(patch_feature[:,feature_weight>0,:,:]*balance_weights[i])
            num_channels = num_channels + torch.sum(feature_weight)
        target_features = torch.cat(target_features, dim = 1)
        assert(target_features.shape[1] == num_channels), 'Something wrong happened when selecting features!'
    else:
        assert(mode == 'reduction'), "only 'reduction' is available for now!"
    return target_features

def feature_selection(input_feature, feature_weight, mode = 'reduction'):
    #TODO: pca, sa, pca_sa
    assert(mode in ['pca', 'sa', 'pca_sa', 'reduction']), "mode need to be 'pca' or 'sa' or 'pca_sa' or 'reduction'"
    return input_feature[:,feature_weight>0,:,:]



def resize_tensor(input_tensor, size, mode = 'bilinear',align_corners = False):
    """
    function: calculate the resize of torch.Tensor
    args:
        size: tuple(height,width)
    """
    return nn.functional.interpolate(input_tensor, size, mode = mode, align_corners = align_corners)


def tensor_show(tensor, time = 20,bbox = None, normalize = True, feature = False):

    fig,ax = plt.subplots(1,1)
    if normalize and not feature:
        ax.imshow(unnormalize(tensor))
    elif not normalize and not feature:
        ax.imshow(torch.squeeze(tensor).to('cpu').numpy().transpose((1,2,0)))
    elif feature:
        ax.imshow(torch.squeeze(tensor).to('cpu').numpy())
    if bbox is not None:
        ax.add_patch(Rectangle((bbox[0],bbox[1]),bbox[2],bbox[3],fill=False,color='g'))
    plt.ion()
    mngr = plt.get_current_fig_manager()
    mngr.window.setGeometry = (100,100,800,500)
    plt.pause(time)
    plt.clf()
    plt.close()
